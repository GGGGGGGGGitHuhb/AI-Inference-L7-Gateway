#include <sys/socket.h>

#include <algorithm>
#include <cstring>

#include "TestSupport.h"
#include "gateway/GatewayRuntime.h"
namespace gateway::gateway_api {
struct ProxySessionTestAccess {
  static void downstream(ProxySession& session, std::uint32_t events) {
    session.onDownstreamEvent(events);
  }

  static void upstream(ProxySession& session, std::uint32_t events) {
    session.onUpstreamEvent(events);
  }

  static void deadline(ProxySession& session) {
    if (session.timerId_) session.loop_.cancelTimer(session.timerId_);
    session.onDeadline();
  }

  static void pause(ProxySession& session) { session.pauseUpstream(); }

  static void localError(ProxySession& session) {
    session.prepareError(502, "stream_buffer_limit");
  }
};
struct RuntimeTestAccess {
  static upstream::ConnectionPool& pool(GatewayRuntime& runtime,
                                        std::size_t index) {
    return *runtime.pools_.at(index);
  }

  static routing::ModelRouter& router(GatewayRuntime& runtime) {
    return runtime.router_;
  }
};
}  // namespace gateway::gateway_api
namespace {
using namespace gateway;
using gateway_api::ProxySessionTestAccess;
class FakeIo final : public gateway_api::SessionIo {
 public:
  Clock::time_point now() const override { return time; }

  int connectSocket(int, const sockaddr*, socklen_t) override;
  int socketError(int) override { return connectError; }

  ssize_t peekByte(int) override {
    errno = peekError;
    return peekResult;
  }

  int shutdownWrite(int) override;

  ssize_t receiveBytes(int fd, void* data, std::size_t size) override;
  ssize_t sendBytes(int fd, const void* data, std::size_t size) override;

  std::vector<std::string> operations;
  int peekError = EAGAIN;
  ssize_t peekResult = -1;
  int connectCalls = 0;
  bool failUpstreamWrite = false;
  int shutdownAttempts = 0;
  int shutdownSuccesses = 0;
  int shutdownInterrupts = 0;
  int shutdownError = 0;
  bool throwRead = false;

  int clientFd = -1;
  Clock::time_point time = Clock::now();
  std::string clientInput;
  std::string upstreamInput;
  std::string sentClient;
  std::string sentUpstream;

  bool pendingConnect = false;
  int connectError = 0;
  int connectInterrupts = 0;
  int readInterrupts = 0;
  int advanceUpstreamReadMs = 0;
  int advanceClientSendMs = 0;
  int writeInterrupts = 0;

  bool blockUpstream = false;
  bool blockClient = false;
  bool clientEof = false;
  bool clientReset = false;
  bool upstreamReset = false;
  bool upstreamEof = false;
  std::size_t sendLimit = 7;
  std::size_t clientSendBudget = 16777216;
};

int FakeIo::shutdownWrite(int) {
  ++shutdownAttempts;
  if (shutdownInterrupts-- > 0) {
    errno = EINTR;
    return -1;
  }
  if (shutdownError) {
    errno = shutdownError;
    return -1;
  }
  ++shutdownSuccesses;
  operations.push_back("shutdown");
  return 0;
}

int FakeIo::connectSocket(int, const sockaddr*, socklen_t) {
  ++connectCalls;
  if (connectInterrupts-- > 0) {
    errno = EINTR;
    return -1;
  }

  if (pendingConnect) {
    errno = EINPROGRESS;
    return -1;
  }
  return 0;
}

ssize_t FakeIo::receiveBytes(int fd, void* data, std::size_t size) {
  if (readInterrupts-- > 0) {
    errno = EINTR;
    return -1;
  }
  const bool client = fd == clientFd;
  if (!client && advanceUpstreamReadMs) {
    time += std::chrono::milliseconds(advanceUpstreamReadMs);
    advanceUpstreamReadMs = 0;
  }

  if (client) {
    if (throwRead) throw std::bad_alloc();
    operations.push_back("read");
  }

  if (client ? clientReset : upstreamReset) {
    errno = ECONNRESET;
    return -1;
  }
  auto& input = client ? clientInput : upstreamInput;
  if (input.empty()) {
    if (client ? clientEof : upstreamEof) return 0;
    errno = EAGAIN;
    return -1;
  }

  const auto count = std::min(size, input.size());
  std::memcpy(data, input.data(), count);
  input.erase(0, count);
  return count;
}

ssize_t FakeIo::sendBytes(int fd, const void* data, std::size_t size) {
  if (fd == clientFd) {
    time += std::chrono::milliseconds(advanceClientSendMs);
    advanceClientSendMs = 0;
  }
  if (writeInterrupts-- > 0) {
    errno = EINTR;
    return -1;
  }
  const bool client = fd == clientFd;
  if (!client && failUpstreamWrite) {
    errno = EPIPE;
    return -1;
  }
  if ((client && clientSendBudget == 0) ||
      (client ? blockClient : blockUpstream)) {
    errno = EAGAIN;
    return -1;
  }

  if (client) operations.push_back("send");
  const auto count =
      std::min({size, sendLimit, client ? clientSendBudget : size});
  if (client) clientSendBudget -= count;
  (client ? sentClient : sentUpstream)
      .append(static_cast<const char*>(data), count);
  return count;
}

class RoutingFixture {
 public:
  RoutingFixture();
  void begin(bool stream = false);
  void response(std::string input);
  void finish();

  app::GatewayConfig config;
  gateway_api::BufferBudget budget{268435456, 4194304};
  net::EventLoop loop;
  FakeIo io;
  std::unique_ptr<routing::ModelRouter> router;
  std::vector<std::unique_ptr<upstream::ConnectionPool>> pools;
  net::Socket peer;
  std::unique_ptr<gateway_api::ProxySession> session;
};

RoutingFixture::RoutingFixture() {
  config.models.push_back(
      {"m", app::RoutingPolicy::kRoundRobin, {{"one", "127.0.0.1", 1}}});
  config.health = {1, 10};
  router = std::make_unique<routing::ModelRouter>(config);
  pools.push_back(std::make_unique<upstream::ConnectionPool>(
      loop, config.upstreamPool, io));
  int pair[2];
  GATEWAY_CHECK(socketpair(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC,
                           0, pair) == 0);
  peer.reset(pair[1]);
  io.clientFd = pair[0];
  io.sendLimit = 65536;
  session = std::make_unique<gateway_api::ProxySession>(
      loop, config, io, *pools[0], net::Socket(pair[0]), io.now(), budget,
      budget.acquireCapacity(gateway_api::CapacityKind::kSession), router.get(),
      &pools);
  session->startSession();
}

void RoutingFixture::begin(bool stream) {
  const std::string body = std::string(
                               "{\"model\":\"m\",\"messages\":[{\"role\":"
                               "\"user\",\"content\":\"x\"}],\"stream\":") +
                           (stream ? "true}" : "false}");
  io.clientInput =
      "POST /v1/chat/completions HTTP/1.1\r\nHost: client\r\nContent-Type: "
      "application/json\r\nContent-Length: " +
      std::to_string(body.size()) + "\r\n\r\n" + body;
  ProxySessionTestAccess::downstream(*session, EPOLLIN);
  if (!io.pendingConnect) ProxySessionTestAccess::upstream(*session, EPOLLOUT);
}

void RoutingFixture::response(std::string input) {
  io.upstreamInput = std::move(input);
  ProxySessionTestAccess::upstream(*session, EPOLLIN);
}

void RoutingFixture::finish() {
  session->finishSession(gateway_api::FinishReason::kStopped);
  session->finishSession();
  session.reset();
  pools[0]->closeAllConnections();
  pools[0]->cleanupRetired();
  GATEWAY_CHECK(router->snapshot(0).inflight == 0);
  GATEWAY_CHECK(loop.timerCount() == 0);
  GATEWAY_CHECK(pools[0]->snapshot().total == 0);
  GATEWAY_CHECK(budget.snapshot().reserved == 0);
}

void completionChecks() {
  for (bool stream : {false, true}) {
    RoutingFixture fixture;
    fixture.begin(stream);
    GATEWAY_CHECK(fixture.router->snapshot(0).inflight == 1);
    fixture.io.blockClient = true;
    fixture.response(
        stream ? "HTTP/1.1 200 OK\r\nContent-Type: "
                 "text/event-stream\r\nContent-Length: 9\r\n\r\ndata: x\n\n"
               : "HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc");
    GATEWAY_CHECK(!fixture.session->finished());
    GATEWAY_CHECK(fixture.router->snapshot(0).inflight == 0);
    GATEWAY_CHECK(fixture.router->snapshot(0).state ==
                  routing::HealthState::kAvailable);
    // 下游尚未排空时新epoch摘除，旧ConnectionLease不得回idle。
    auto other = fixture.router->selectBackend("m", fixture.io.now());
    other.lease.complete(routing::Observation::kFailure, fixture.io.now());
    fixture.io.blockClient = false;
    ProxySessionTestAccess::downstream(*fixture.session, EPOLLOUT);
    GATEWAY_CHECK(fixture.pools[0]->snapshot().idle == 0);
    fixture.finish();
  }
}

void terminalChecks() {
  for (int scenario = 0; scenario < 14; ++scenario) {
    RoutingFixture fixture;
    fixture.config.timeouts.total = 1000;
    fixture.config.timeouts.response = 100;
    fixture.config.timeouts.streamIdle = 50;
    if (scenario == 1) fixture.io.connectError = ECONNREFUSED;
    if (scenario == 4 || scenario == 10) fixture.io.pendingConnect = true;
    if (scenario == 10) fixture.config.timeouts.connect = 10;
    if (scenario == 11) {
      fixture.config.timeouts.upstreamWrite = 10;
      fixture.io.blockUpstream = true;
    }
    fixture.begin(scenario == 7 || scenario == 8);
    if (scenario == 0) {
      fixture.io.clientReset = true;
      ProxySessionTestAccess::downstream(*fixture.session, EPOLLIN);
    } else if (scenario == 2)
      fixture.response("not HTTP\r\n\r\n");
    else if (scenario == 3) {
      fixture.io.upstreamReset = true;
      ProxySessionTestAccess::upstream(*fixture.session, EPOLLIN);
    } else if (scenario == 4) {
      fixture.io.time += std::chrono::milliseconds(1000);
      ProxySessionTestAccess::deadline(*fixture.session);  // total更早，中立。
    } else if (scenario == 5) {
      fixture.io.time += std::chrono::milliseconds(100);
      ProxySessionTestAccess::deadline(*fixture.session);
    } else if (scenario == 6)
      ProxySessionTestAccess::localError(*fixture.session);
    else if (scenario == 7 || scenario == 8) {
      fixture.response(
          "HTTP/1.1 200 OK\r\nContent-Type: "
          "text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n9\r\ndata: "
          "x\n\n\r\n");
      if (scenario == 7) ProxySessionTestAccess::pause(*fixture.session);
      fixture.io.time += std::chrono::milliseconds(scenario == 7 ? 100 : 50);
      ProxySessionTestAccess::deadline(*fixture.session);
    } else if (scenario == 9)
      fixture.session->finishSession(gateway_api::FinishReason::kStopped);
    else if (scenario == 10 || scenario == 11) {
      fixture.io.time += std::chrono::milliseconds(10);
      ProxySessionTestAccess::deadline(*fixture.session);
    } else if (scenario == 12)
      fixture.response("HTTP/1.1 200 OK\r\nContent-Length: 5000000\r\n\r\n");
    else if (scenario == 13) {
      fixture.response(
          "HTTP/1.1 503 unavailable\r\nContent-Length: 10\r\n\r\nx");
      GATEWAY_CHECK(fixture.router->snapshot(0).failureCount == 0);
      fixture.io.upstreamEof = true;
      ProxySessionTestAccess::upstream(*fixture.session, EPOLLIN);
    }
    const bool failure = scenario == 1 || scenario == 2 || scenario == 3 ||
                         scenario == 5 || scenario == 8 || scenario == 10 ||
                         scenario == 11 || scenario == 13;
    GATEWAY_CHECK(fixture.router->snapshot(0).inflight == 0);
    std::cout << "terminal scenario=" << scenario
              << " failures=" << fixture.router->snapshot(0).failureCount
              << "\n";
    GATEWAY_CHECK(fixture.router->snapshot(0).failureCount ==
                  (failure ? 1U : 0U));
    fixture.finish();
  }
}

void idleAndTrialChecks() {
  RoutingFixture fixture;
  std::vector<upstream::ConnectionLease> idleLeases;
  for (int index = 0; index < 3; ++index) {
    idleLeases.push_back(fixture.pools[0]->acquireConnection({}));
    idleLeases.back().markConnected();
  }
  for (auto& idle : idleLeases) idle.releaseReusable();
  GATEWAY_CHECK(fixture.pools[0]->snapshot().idle == 3);
  fixture.begin();
  GATEWAY_CHECK(fixture.pools[0]->snapshot().idle == 2);
  fixture.response("HTTP/1.1 503 unavailable\r\nContent-Length: 0\r\n\r\n");
  GATEWAY_CHECK(fixture.router->snapshot(0).state ==
                routing::HealthState::kEjected);
  GATEWAY_CHECK(fixture.pools[0]->snapshot().idle == 0);
  fixture.io.time += std::chrono::milliseconds(10);
  {
    auto trial = fixture.router->selectBackend("m", fixture.io.now());
    GATEWAY_CHECK(trial.lease.active());
    auto moved = std::move(trial.lease);
    moved.complete(routing::Observation::kNeutral, fixture.io.now());
  }
  GATEWAY_CHECK(fixture.router->snapshot(0).state ==
                routing::HealthState::kEjected);
  fixture.finish();
}

void trialAndCapacityChecks() {
  for (int scenario = 0; scenario < 4; ++scenario) {
    RoutingFixture fixture;
    auto failure = fixture.router->selectBackend("m", fixture.io.now());
    failure.lease.complete(routing::Observation::kFailure, fixture.io.now());
    fixture.io.time += std::chrono::milliseconds(10);
    std::vector<upstream::ConnectionLease> occupied;
    std::vector<gateway_api::CapacityLease> capacity;
    if (scenario == 2)
      for (int index = 0; index < 16; ++index)
        occupied.push_back(fixture.pools[0]->acquireConnection({}));
    if (scenario == 3)
      for (int index = 0; index < 16; ++index)
        capacity.push_back(
            fixture.budget.acquireCapacity(gateway_api::CapacityKind::kStream));
    fixture.begin(scenario == 3);
    if (scenario == 0) {
      fixture.io.clientReset = true;
      ProxySessionTestAccess::downstream(*fixture.session, EPOLLIN);
    } else if (scenario == 1)
      fixture.session->finishSession(gateway_api::FinishReason::kStopped);
    else if (scenario == 3)
      fixture.response(
          "HTTP/1.1 200 OK\r\nContent-Type: "
          "text/event-stream\r\nContent-Length: 9\r\n\r\ndata: x\n\n");
    GATEWAY_CHECK(fixture.router->snapshot(0).state ==
                  routing::HealthState::kEjected);
    GATEWAY_CHECK(fixture.router->snapshot(0).inflight == 0);
    GATEWAY_CHECK(fixture.router->snapshot(0).failureCount == 1);
    GATEWAY_CHECK(fixture.router->selectBackend("m", fixture.io.now()).status ==
                  routing::SelectionStatus::kUnavailable);
    occupied.clear();
    capacity.clear();
    fixture.finish();
  }
}

void leastInflightIdleChecks() {
  app::GatewayConfig config;
  config.models = {{"m",
                    app::RoutingPolicy::kLeastInflight,
                    {{"one", "127.0.0.1", 1}, {"two", "127.0.0.1", 2}}}};
  routing::ModelRouter router(config);
  net::EventLoop loop;
  FakeIo io;
  upstream::ConnectionPool first(loop, config.upstreamPool, io);
  upstream::ConnectionPool second(loop, config.upstreamPool, io);
  std::vector<upstream::ConnectionLease> idleLeases;
  for (int index = 0; index < 3; ++index) {
    idleLeases.push_back(first.acquireConnection({}));
    idleLeases.back().markConnected();
  }
  for (auto& idle : idleLeases) idle.releaseReusable();
  GATEWAY_CHECK(first.snapshot().idle == 3);
  auto held = router.selectBackend("m", io.now());
  GATEWAY_CHECK(held.lease.index() == 0);  // total=3不影响请求inflight平局。
  auto transmission = first.acquireConnection({});
  GATEWAY_CHECK(first.snapshot().idle == 2);
  auto shorter = router.selectBackend("m", io.now());
  GATEWAY_CHECK(shorter.lease.index() == 1);
  held.lease.complete(routing::Observation::kSuccess, io.now());
  GATEWAY_CHECK(transmission.valid());
  auto afterCompletion = router.selectBackend("m", io.now());
  GATEWAY_CHECK(afterCompletion.lease.index() == 0);
  afterCompletion.lease.complete(routing::Observation::kNeutral, io.now());
  shorter.lease.complete(routing::Observation::kNeutral, io.now());
  transmission.invalidate();
  first.closeAllConnections();
  second.closeAllConnections();
  GATEWAY_CHECK(loop.timerCount() == 0);
}

void runtimeIsolationChecks() {
  app::GatewayConfig config;
  config.models = {
      {"a", app::RoutingPolicy::kLeastInflight, {{"one", "127.0.0.1", 1}}},
      {"b", app::RoutingPolicy::kRoundRobin, {{"one", "127.0.0.1", 1}}}};
  config.health.failureThreshold = 1;
  gateway_api::GatewayRuntime runtime(config);
  auto& router = gateway_api::RuntimeTestAccess::router(runtime);
  auto& first = gateway_api::RuntimeTestAccess::pool(runtime, 0);
  auto& second = gateway_api::RuntimeTestAccess::pool(runtime, 1);
  auto one = first.acquireConnection({});
  auto two = second.acquireConnection({});
  GATEWAY_CHECK(&first != &second);
  GATEWAY_CHECK(runtime.snapshot().instances.size() == 2);
  GATEWAY_CHECK(runtime.snapshot().instances[0].pool.leased == 1);
  GATEWAY_CHECK(runtime.snapshot().instances[1].pool.leased == 1);
  auto request =
      router.selectBackend("a", gateway_api::SessionIo::Clock::now());
  request.lease.complete(routing::Observation::kFailure,
                         gateway_api::SessionIo::Clock::now());
  GATEWAY_CHECK(router.snapshot(1).state == routing::HealthState::kAvailable);
  GATEWAY_CHECK(router.snapshot(1).inflight == 0);
  GATEWAY_CHECK(router.snapshot(1).failureCount == 0);
  one.invalidate();
  two.invalidate();
  runtime.requestShutdown();
  runtime.pollOnce(0);
  GATEWAY_CHECK(runtime.snapshot().pool.total == 0);
  GATEWAY_CHECK(runtime.snapshot().activeTimers == 0);
}

}  // namespace

void routingLifecycleChecks() {
  completionChecks();
  terminalChecks();
  idleAndTrialChecks();
  trialAndCapacityChecks();
  runtimeIsolationChecks();
  leastInflightIdleChecks();
}
