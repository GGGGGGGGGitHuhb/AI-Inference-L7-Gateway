#pragma once
#include <map>

#include "app/GatewayConfig.h"
#include "app/SignalSource.h"
#include "gateway/ProxySession.h"
namespace gateway::gateway_api {
struct InstanceSnapshot {
  routing::BackendSnapshot routing;
  upstream::PoolSnapshot pool;
};

struct RuntimeSnapshot {
  std::size_t activeSessions;
  std::uint64_t reservedBytes;
  std::size_t activeUpstreams;
  std::size_t activeTimers;
  std::size_t peakSessions;
  upstream::PoolSnapshot pool;
  BudgetSnapshot budget;
  std::vector<InstanceSnapshot> instances;
};

class GatewayRuntime {
 public:
  explicit GatewayRuntime(app::GatewayConfig config);
  ~GatewayRuntime();

  std::uint16_t startListener();
  void runGateway();

  RuntimeSnapshot snapshot() const;
  void pollOnce(int timeoutMs) { loop_.pollOnce(timeoutMs); }
  void requestShutdown();

 private:
  friend struct RuntimeTestAccess;

  void onListenerEvent(std::uint32_t events);
  void onSignalEvent(std::uint32_t events);
  void onCleanup();

  void onShutdownDeadline();
  void forceShutdown();

  app::GatewayConfig config_;
  BufferBudget budget_;
  SessionIo io_;
  net::EventLoop loop_;
  app::SignalSource signals_;
  upstream::ConnectionPool pool_;
  routing::ModelRouter router_;
  std::vector<std::unique_ptr<upstream::ConnectionPool>> pools_;

  net::Socket listener_;
  std::unique_ptr<net::Channel> listenerChannel_;
  std::unique_ptr<net::Channel> signalChannel_;

  std::map<std::uint64_t, std::unique_ptr<ProxySession>> sessions_;
  std::uint64_t nextSessionId_ = 1;
  std::size_t peakSessions_ = 0;

  net::EventLoop::TimerId shutdownTimer_ = 0;
  bool stopping_ = false;
};
}  // namespace gateway::gateway_api
