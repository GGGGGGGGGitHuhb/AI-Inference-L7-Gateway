#pragma once
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <vector>

#include "app/GatewayConfig.h"
#include "gateway/SessionIo.h"
#include "net/Channel.h"
#include "net/EventLoop.h"
#include "net/Socket.h"

namespace gateway::upstream {
class ConnectionPool;
struct ConnectionPoolTestAccess;

// 池唯一拥有传输对象；租约只代表一次可撤销的使用权。
class ConnectionLease {
 public:
  ConnectionLease() = default;
  ~ConnectionLease();
  ConnectionLease(const ConnectionLease&) = delete;
  ConnectionLease& operator=(const ConnectionLease&) = delete;
  ConnectionLease(ConnectionLease&& other) noexcept;
  ConnectionLease& operator=(ConnectionLease&& other) noexcept;

  int fd() const noexcept;
  bool valid() const noexcept { return fd() >= 0; }
  bool reused() const noexcept { return reused_; }
  std::uint64_t id() const noexcept { return id_; }
  std::uint64_t generation() const noexcept { return generation_; }
  std::uint32_t interest() const noexcept;

  void setInterest(std::uint32_t events);
  void suspendEvents() noexcept;
  void markConnected();
  void releaseReusable();
  void invalidate() noexcept;

 private:
  friend class ConnectionPool;
  ConnectionLease(ConnectionPool& pool, std::uint64_t id,
                  std::uint64_t generation, bool reused);

  ConnectionPool* pool_ = nullptr;
  std::uint64_t id_ = 0;
  std::uint64_t generation_ = 0;
  bool reused_ = false;
};

struct PoolSnapshot {
  std::size_t total = 0;
  std::size_t leased = 0;
  std::size_t idle = 0;
  std::size_t retired = 0;
  std::size_t peakTotal = 0;
  std::uint64_t created = 0;
  std::uint64_t reused = 0;
  std::uint64_t discarded = 0;
  std::uint64_t capacityRejected = 0;
};

class ConnectionPool {
 public:
  using LeaseEventCallback = std::function<void(std::uint32_t)>;

  ConnectionPool(net::EventLoop& loop, const app::PoolConfig& config,
                 gateway_api::SessionIo& io);
  ~ConnectionPool();

  ConnectionLease acquireConnection(LeaseEventCallback leaseEventCallback);
  void stopAcquisition() noexcept;
  void closeAllConnections() noexcept;
  void cleanupRetired() noexcept;
  bool stopping() const noexcept { return stopping_; }
  PoolSnapshot snapshot() const noexcept;

 private:
  friend class ConnectionLease;
  friend struct ConnectionPoolTestAccess;
  enum class State { kConnecting, kLeased, kIdle, kRetiring };
  struct Entry {
    Entry(net::EventLoop& loop, net::Socket connectionSocket);

    net::Socket socket;
    net::Channel channel;
    LeaseEventCallback leaseEventCallback;

    std::uint64_t generation = 1;
    State state = State::kConnecting;
    net::EventLoop::TimerId idleTimer = 0;
    gateway_api::SessionIo::Clock::time_point idleDeadline;
  };

  Entry* findLease(std::uint64_t id, std::uint64_t generation) const noexcept;
  bool isClean(int fd);
  void retireConnection(std::uint64_t id) noexcept;
  void returnConnection(std::uint64_t id, std::uint64_t generation);
  void onConnectionEvent(std::uint64_t id, std::uint32_t events);
  void onIdleDeadline(std::uint64_t id, std::uint64_t generation);

  net::EventLoop& loop_;
  const app::PoolConfig config_;
  gateway_api::SessionIo& io_;

  std::map<std::uint64_t, std::unique_ptr<Entry>> connections_;
  std::vector<std::unique_ptr<Entry>> retired_;

  std::uint64_t nextId_ = 1;
  PoolSnapshot counters_;
  bool stopping_ = false;
};
}  // namespace gateway::upstream
