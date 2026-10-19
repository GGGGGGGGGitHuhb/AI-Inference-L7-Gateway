#pragma once
#include <memory>
#include <string>

#include "app/GatewayConfig.h"
#include "gateway/SessionIo.h"
#include "http/HttpParser.h"
#include "net/Channel.h"
#include "net/EventLoop.h"
#include "net/Socket.h"

namespace gateway::gateway_api {
struct ProxySessionTestAccess;
class ProxySession {
 public:
  static constexpr std::uint64_t kReservationBytes = 16777216;

  ProxySession(net::EventLoop& loop, const app::GatewayConfig& config,
               SessionIo& io, net::Socket client,
               SessionIo::Clock::time_point acceptedAt);
  ~ProxySession();

  void startSession();
  void finishSession() noexcept;

  bool finished() const { return phase_ == Phase::kFinished; }
  bool hasUpstream() const { return upstreamSocket_.valid(); }
  bool hasTimer() const { return timerId_ != 0; }

 private:
  friend struct ProxySessionTestAccess;

  enum class Phase {
    kReceiving,
    kConnecting,
    kUpstream,
    kDownstream,
    kClosing,
    kFinished
  };
  using TimePoint = SessionIo::Clock::time_point;

  // 事件入口与会话IO。
  void onDownstreamEvent(std::uint32_t events) noexcept;
  void onUpstreamEvent(std::uint32_t events) noexcept;
  void onDeadline() noexcept;
  void handleDownstreamEvent(std::uint32_t events);
  void handleUpstreamEvent(std::uint32_t events);
  void readDownstream();
  void readUpstream();
  void writeUpstream();
  void writeDownstream();

  // 请求、响应及分阶段关闭。
  void beginUpstream();
  void confirmConnected();
  void completeResponse();
  void beginClosing(int remainingCalls);
  void shutdownWrite(int remainingCalls = 64);
  void prepareError(unsigned status, const char* code) noexcept;

  // 资源和绝对deadline。
  void updateInterests();
  void closeUpstream() noexcept;
  void armDeadline();
  TimePoint nextDeadline() const;
  bool checkDeadline();

  void checkOutputBudget(const http::HttpMessage& message,
                         std::size_t limit) const;

  net::EventLoop& loop_;
  const app::GatewayConfig& config_;
  SessionIo& io_;

  net::Socket downstreamSocket_;
  net::Socket upstreamSocket_;
  std::unique_ptr<net::Channel> downstreamChannel_;
  std::unique_ptr<net::Channel> upstreamChannel_;

  std::unique_ptr<http::HttpParser> requestParser_;
  std::unique_ptr<http::HttpParser> responseParser_;
  std::string upstreamOutput_;
  std::string downstreamOutput_;
  std::size_t upstreamOffset_ = 0;
  std::size_t downstreamOffset_ = 0;

  net::EventLoop::TimerId timerId_ = 0;
  TimePoint acceptedAt_;
  TimePoint stageStarted_;
  TimePoint connectedAt_;
  TimePoint outputStarted_;
  TimePoint errorDeadline_;
  TimePoint outputCompletedAt_;

  Phase phase_ = Phase::kReceiving;
  bool downstreamEof_ = false;
  bool errorDraining_ = false;
  bool writeShutdown_ = false;
};
}  // namespace gateway::gateway_api
