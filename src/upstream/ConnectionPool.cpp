#include "upstream/ConnectionPool.h"

#include <algorithm>
#include <cerrno>
#include <limits>
#include <stdexcept>
#include <utility>

namespace gateway::upstream {
namespace {
void incrementCounter(std::uint64_t& count) {
  if (count != std::numeric_limits<std::uint64_t>::max()) ++count;
}
}  // namespace

ConnectionLease::ConnectionLease(ConnectionPool& pool, std::uint64_t id,
                                 std::uint64_t generation, bool reused)
    : pool_(&pool), id_(id), generation_(generation), reused_(reused) {}

ConnectionLease::~ConnectionLease() { invalidate(); }

ConnectionLease::ConnectionLease(ConnectionLease&& other) noexcept
    : pool_(std::exchange(other.pool_, nullptr)),
      id_(other.id_),
      generation_(other.generation_),
      reused_(other.reused_) {}

ConnectionLease& ConnectionLease::operator=(ConnectionLease&& other) noexcept {
  if (this != &other) {
    invalidate();
    pool_ = std::exchange(other.pool_, nullptr);
    id_ = other.id_;
    generation_ = other.generation_;
    reused_ = other.reused_;
  }
  return *this;
}

int ConnectionLease::fd() const noexcept {
  auto* entry = pool_ ? pool_->findLease(id_, generation_) : nullptr;
  return entry ? entry->socket.fd() : -1;
}

std::uint32_t ConnectionLease::interest() const noexcept {
  auto* entry = pool_ ? pool_->findLease(id_, generation_) : nullptr;
  return entry ? entry->channel.interest() : 0;
}

void ConnectionLease::suspendEvents() noexcept {
  if (pool_) {
    if (auto* entry = pool_->findLease(id_, generation_))
      entry->channel.removeChannel();
  }
}

void ConnectionLease::setInterest(std::uint32_t events) {
  auto* entry = pool_ ? pool_->findLease(id_, generation_) : nullptr;
  if (entry) entry->channel.setInterest(events);
}

void ConnectionLease::markConnected() {
  auto* entry = pool_ ? pool_->findLease(id_, generation_) : nullptr;
  if (entry) entry->state = ConnectionPool::State::kLeased;
}

void ConnectionLease::invalidate() noexcept {
  auto* owner = std::exchange(pool_, nullptr);
  if (owner && owner->findLease(id_, generation_)) owner->retireConnection(id_);
}

void ConnectionLease::releaseReusable() {
  auto* owner = std::exchange(pool_, nullptr);
  if (owner) owner->returnConnection(id_, generation_);
}

ConnectionPool::Entry::Entry(net::EventLoop& loop, net::Socket connectionSocket)
    : socket(std::move(connectionSocket)), channel(loop, socket.fd()) {}

ConnectionPool::ConnectionPool(net::EventLoop& loop,
                               const app::PoolConfig& config,
                               gateway_api::SessionIo& io)
    : loop_(loop), config_(config), io_(io) {
  if (!config_.maxConnections || config_.maxConnections > 256 ||
      config_.maxIdle > config_.maxConnections)
    throw std::invalid_argument("pool capacity");
  // 一个业务回调最多淘汰原有N项再新建1项；最多2N个对象同时存活。
  retired_.reserve(config_.maxConnections * 2);
}

ConnectionPool::~ConnectionPool() {
  closeAllConnections();
  cleanupRetired();
}

ConnectionPool::Entry* ConnectionPool::findLease(
    std::uint64_t id, std::uint64_t generation) const noexcept {
  const auto found = connections_.find(id);
  if (found == connections_.end()) return nullptr;
  auto* entry = found->second.get();
  return entry->generation == generation &&
                 (entry->state == State::kConnecting ||
                  entry->state == State::kLeased)
             ? entry
             : nullptr;
}

PoolSnapshot ConnectionPool::snapshot() const noexcept {
  auto result = counters_;
  result.total = connections_.size();
  result.retired = retired_.size();
  for (const auto& [id, entry] : connections_) {
    if (entry->state == State::kIdle)
      ++result.idle;
    else
      ++result.leased;
  }
  return result;
}

bool ConnectionPool::isClean(int fd) {
  if (io_.socketError(fd)) return false;
  for (int attempt = 0; attempt < 32; ++attempt) {
    const auto count = io_.peekByte(fd);
    if (count < 0 && errno == EINTR) continue;
    return count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK);
  }
  return false;
}

void ConnectionPool::retireConnection(std::uint64_t id) noexcept {
  const auto found = connections_.find(id);
  if (found == connections_.end()) return;
  auto& entry = *found->second;
  entry.channel.removeChannel();
  if (entry.idleTimer) loop_.cancelTimer(entry.idleTimer);
  entry.idleTimer = 0;
  entry.state = State::kRetiring;
  entry.socket.reset();
  entry.leaseEventCallback = {};
  // 容量预先预约；acquire禁止超过退休存储上界，无回收期内分配。
  retired_.push_back(std::move(found->second));
  connections_.erase(found);
  incrementCounter(counters_.discarded);
}

void ConnectionPool::cleanupRetired() noexcept { retired_.clear(); }

ConnectionLease ConnectionPool::acquireConnection(
    LeaseEventCallback leaseEventCallback) {
  if (stopping_) return {};
  if (retired_.size() + connections_.size() >= config_.maxConnections * 2)
    throw std::runtime_error("pool cleanup required");
  for (auto iterator = connections_.begin(); iterator != connections_.end();) {
    const auto id = iterator->first;
    auto& entry = *iterator->second;
    ++iterator;
    if (entry.state != State::kIdle) continue;
    if (io_.now() >= entry.idleDeadline || !isClean(entry.socket.fd()) ||
        entry.generation == std::numeric_limits<std::uint64_t>::max()) {
      retireConnection(id);
      continue;
    }
    entry.channel.removeChannel();
    loop_.cancelTimer(entry.idleTimer);
    entry.idleTimer = 0;
    ++entry.generation;
    entry.state = State::kLeased;
    entry.leaseEventCallback = std::move(leaseEventCallback);
    incrementCounter(counters_.reused);
    return ConnectionLease(*this, id, entry.generation, true);
  }
  if (connections_.size() == config_.maxConnections) {
    incrementCounter(counters_.capacityRejected);
    return {};
  }
  if (!nextId_) throw std::overflow_error("connection ID exhausted");
  const auto id = nextId_++;
  auto entry = std::make_unique<Entry>(loop_, net::Socket::createTcp());
  entry->channel.registerEventCallback(
      [this, id](std::uint32_t events) { onConnectionEvent(id, events); });
  entry->leaseEventCallback = std::move(leaseEventCallback);
  connections_.emplace(id, std::move(entry));
  counters_.peakTotal = std::max(counters_.peakTotal, connections_.size());
  incrementCounter(counters_.created);
  return ConnectionLease(*this, id, 1, false);
}

void ConnectionPool::returnConnection(std::uint64_t id,
                                      std::uint64_t generation) {
  auto* entry = findLease(id, generation);
  if (!entry) return;
  try {
    if (stopping_ || entry->state != State::kLeased ||
        snapshot().idle >= config_.maxIdle || !isClean(entry->socket.fd())) {
      retireConnection(id);
      return;
    }
    entry->channel.removeChannel();
    entry->leaseEventCallback = {};
    entry->state = State::kIdle;
    entry->idleDeadline =
        io_.now() + std::chrono::milliseconds(config_.idleTimeoutMs);
    entry->idleTimer = loop_.addTimer(
        entry->idleDeadline,
        [this, id, generation] { onIdleDeadline(id, generation); });
    entry->channel.setInterest(EPOLLIN | EPOLLRDHUP);
  } catch (...) {
    retireConnection(id);
    throw;
  }
}

void ConnectionPool::onConnectionEvent(std::uint64_t id, std::uint32_t events) {
  const auto found = connections_.find(id);
  if (found == connections_.end()) return;
  auto& entry = *found->second;
  if (entry.state == State::kIdle) {
    retireConnection(id);
    return;
  }
  // 独立调用副本允许回调内清除租约目标；条目自身由cleanup延后销毁。
  const auto generation = entry.generation;
  auto leaseEventCallback = entry.leaseEventCallback;
  if (findLease(id, generation) && leaseEventCallback)
    leaseEventCallback(events);
}

void ConnectionPool::onIdleDeadline(std::uint64_t id,
                                    std::uint64_t generation) {
  const auto found = connections_.find(id);
  if (found == connections_.end() || found->second->state != State::kIdle ||
      found->second->generation != generation)
    return;
  found->second->idleTimer = 0;
  retireConnection(id);
}

void ConnectionPool::stopAcquisition() noexcept {
  stopping_ = true;
  clearIdle();
}

void ConnectionPool::clearIdle() noexcept {
  for (auto iterator = connections_.begin(); iterator != connections_.end();) {
    auto current = iterator++;
    if (current->second->state == State::kIdle)
      retireConnection(current->first);
  }
}

void ConnectionPool::closeAllConnections() noexcept {
  stopping_ = true;
  while (!connections_.empty()) retireConnection(connections_.begin()->first);
}
}  // namespace gateway::upstream
