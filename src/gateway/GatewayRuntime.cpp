#include "gateway/GatewayRuntime.h"

#include <arpa/inet.h>
#include <sys/signalfd.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <limits>
#include <stdexcept>
#include <system_error>

namespace gateway::gateway_api {
GatewayRuntime::GatewayRuntime(app::GatewayConfig config)
    : config_(std::move(config)),
      budget_(config_.maxReservedBytes, config_.streamBuffer.maxTotalBytes),
      pool_(loop_, config_.upstreamPool, io_) {
  loop_.registerCleanupCallback([this] { onCleanup(); });
}

GatewayRuntime::~GatewayRuntime() {
  for (auto& [id, session] : sessions_)
    session->finishSession(FinishReason::kStopped);
  sessions_.clear();
  if (shutdownTimer_) loop_.cancelTimer(shutdownTimer_);
  if (listenerChannel_) listenerChannel_->removeChannel();
  if (signalChannel_) signalChannel_->removeChannel();
}

std::uint16_t GatewayRuntime::startListener() {
  listener_ = net::Socket::createTcp();
  listener_.setReuseAddress(true);
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_port = htons(config_.listenPort);
  inet_pton(AF_INET, config_.listenAddress.c_str(), &address.sin_addr);
  if (::bind(listener_.fd(), reinterpret_cast<const sockaddr*>(&address),
             sizeof(address)) < 0)
    throw std::system_error(errno, std::generic_category(), "bind");
  const auto actualPort = listener_.localPort();
  if (actualPort == config_.upstreamPort &&
      (config_.listenAddress == config_.upstreamAddress ||
       config_.listenAddress == "0.0.0.0"))
    throw std::runtime_error("self upstream");
  listener_.listen(128);
  listenerChannel_ = std::make_unique<net::Channel>(loop_, listener_.fd());
  signalChannel_ = std::make_unique<net::Channel>(loop_, signals_.fd());
  listenerChannel_->registerEventCallback(
      [this](std::uint32_t events) { onListenerEvent(events); });
  signalChannel_->registerEventCallback(
      [this](std::uint32_t events) { onSignalEvent(events); });
  signalChannel_->setInterest(EPOLLIN);
  listenerChannel_->setInterest(EPOLLIN);
  return actualPort;
}

void GatewayRuntime::runGateway() { loop_.runEventLoop(); }

RuntimeSnapshot GatewayRuntime::snapshot() const {
  std::size_t upstreams = 0;
  for (const auto& [id, session] : sessions_)
    if (session->hasUpstream()) ++upstreams;
  return {sessions_.size(),  budget_.snapshot().reserved,
          upstreams,         loop_.timerCount(),
          peakSessions_,     pool_.snapshot(),
          budget_.snapshot()};
}

void GatewayRuntime::onListenerEvent(std::uint32_t events) {
  if (stopping_) return;
  if (events & (EPOLLERR | EPOLLHUP))
    throw std::runtime_error("listener failed");
  for (int attempt = 0; attempt < 32; ++attempt) {
    const int fd = ::accept4(listener_.fd(), nullptr, nullptr,
                             SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (fd < 0) {
      if (errno == EINTR) continue;
      if (errno == EAGAIN || errno == EWOULDBLOCK) return;
      if (errno == ECONNABORTED) continue;
      // 描述符/系统资源耗尽属于启动后致命资源问题，交 main 关闭全部对象。
      throw std::system_error(errno, std::generic_category(), "accept");
    }

    const auto acceptedAt = io_.now();
    net::Socket client(fd);
    if (sessions_.size() >= config_.maxConnections) continue;
    auto reservation = budget_.acquireCapacity(CapacityKind::kSession);
    if (!reservation.valid()) continue;
    if (!nextSessionId_) throw std::overflow_error("session ID exhausted");
    const auto id = nextSessionId_++;
    try {
      auto session = std::make_unique<ProxySession>(
          loop_, config_, io_, pool_, std::move(client), acceptedAt, budget_,
          std::move(reservation));
      session->startSession();
      sessions_.emplace(id, std::move(session));
      peakSessions_ = std::max(peakSessions_, sessions_.size());
    } catch (const std::bad_alloc&) {
      // 新会话尚未发布；局部 RAII 回收，不损害其他会话。
    } catch (...) {
      throw;
    }
  }
}

void GatewayRuntime::onCleanup() {
  for (auto iterator = sessions_.begin(); iterator != sessions_.end();) {
    if (iterator->second->finished()) {
      iterator = sessions_.erase(iterator);
    } else
      ++iterator;
  }

  pool_.cleanupRetired();
  if (stopping_ && sessions_.empty()) {
    if (shutdownTimer_) {
      loop_.cancelTimer(shutdownTimer_);
      shutdownTimer_ = 0;
    }

    loop_.requestLoopStop();
  }
}

void GatewayRuntime::onSignalEvent(std::uint32_t) {
  signalfd_siginfo signal{};
  for (int attempt = 0; attempt < 32; ++attempt) {
    const auto count = ::read(signals_.fd(), &signal, sizeof(signal));
    if (count == sizeof(signal)) {
      requestShutdown();
      continue;
    }
    if (count < 0 && errno == EINTR) continue;
    if (count < 0 && errno == EAGAIN) return;
    throw std::runtime_error("signalfd read");
  }
}

void GatewayRuntime::requestShutdown() {
  if (stopping_) {
    forceShutdown();
    return;
  }
  stopping_ = true;
  pool_.stopAcquisition();
  if (listenerChannel_) listenerChannel_->removeChannel();
  listener_.reset();
  shutdownTimer_ = loop_.addTimer(
      io_.now() + std::chrono::milliseconds(config_.timeouts.shutdown),
      [this] { onShutdownDeadline(); });
  // 不在此删除会话；由 EventLoop 回调后清理点收口。
  if (sessions_.empty()) loop_.requestLoopStop();
}

void GatewayRuntime::onShutdownDeadline() {
  shutdownTimer_ = 0;
  forceShutdown();
}

void GatewayRuntime::forceShutdown() {
  for (auto& [id, session] : sessions_)
    session->finishSession(FinishReason::kStopped);
  pool_.closeAllConnections();
  loop_.requestLoopStop();
}
}  // namespace gateway::gateway_api
