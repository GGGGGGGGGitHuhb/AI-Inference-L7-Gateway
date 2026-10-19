#include <arpa/inet.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/eventfd.h>
#include <unistd.h>

#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <new>

#include "TestSupport.h"
#include "app/GatewayConfig.h"
#include "gateway/GatewayRuntime.h"
#include "gateway/ProxySession.h"

namespace {
bool failNextAllocation = false;
}

void* operator new(std::size_t size) {
  if (failNextAllocation) {
    failNextAllocation = false;
    throw std::bad_alloc();
  }

  if (auto* memory = std::malloc(size ? size : 1)) return memory;
  throw std::bad_alloc();
}

void operator delete(void* memory) noexcept { std::free(memory); }

void operator delete(void* memory, std::size_t) noexcept { std::free(memory); }

void* operator new[](std::size_t size) { return ::operator new(size); }

void operator delete[](void* memory) noexcept { ::operator delete(memory); }

void operator delete[](void* memory, std::size_t) noexcept {
  ::operator delete(memory);
}

namespace gateway::net {
struct EventLoopTestAccess {
  static void dispatch(EventLoop& loop, std::uint64_t token,
                       std::uint32_t events) {
    loop.dispatchChannelEvent(token, events);
  }

  static std::uint64_t exchangeToken(std::uint64_t token) {
    return EventLoop::exchangeNextTokenForTest(token);
  }
};
}  // namespace gateway::net

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

  static std::uint32_t interest(ProxySession& session) {
    return session.upstreamLease_.interest();
  }

  static std::uint32_t downstreamInterest(ProxySession& session) {
    return session.downstreamChannel_->interest();
  }

  static std::size_t uploaded(ProxySession& session) {
    return session.upstreamOffset_;
  }
};
struct StreamingSessionTestAccess {
  static void validateHeaders(ProxySession& session, std::string_view headers) {
    GATEWAY_CHECK(session.responseParser_->parseBytes(headers).status ==
                  http::ParseStatus::kNeedMore);
  }

  static bool paused(const ProxySession& session) {
    return session.upstreamPaused_;
  }

  static void pause(ProxySession& session) { session.pauseUpstream(); }

  static void resume(ProxySession& session) { session.resumeUpstream(); }

  static SessionIo::Clock::time_point idleDeadline(
      const ProxySession& session) {
    return session.idleDeadline_;
  }

  static bool started(const ProxySession& session) {
    return session.responseStarted_;
  }

  static std::size_t pending(const ProxySession& session) {
    return session.streamOutput_ ? session.streamOutput_->size() : 0;
  }

  static std::size_t decoded(const ProxySession& session) {
    return session.streamDecodedTotal_;
  }

  static std::size_t bufferedBody(const ProxySession& session) {
    return session.responseParser_
               ? session.responseParser_->message().body.size()
               : 0;
  }

  static bool uploaded(const ProxySession& session) {
    return session.requestWriteComplete_;
  }

  static void error(ProxySession& session) {
    session.prepareError(500, "internal_error");
  }
};
}  // namespace gateway::gateway_api

using namespace gateway;
using gateway_api::ProxySessionTestAccess;
namespace {
const std::string kRequest =
    "POST /v1/chat/completions HTTP/1.1\r\nHost: test\r\nContent-Type: "
    "application/json\r\nContent-Length: "
    "56\r\n\r\n{\"model\":\"m\",\"messages\":[{\"role\":\"user\",\"content\":"
    "\"x\"}]}";
const std::string kResponse = "HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc";

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

class SessionFixture {
 public:
  explicit SessionFixture(app::Timeouts timeouts = {},
                          gateway_api::BufferBudget* sharedBudget = nullptr);

  void startRequest() {
    io.clientInput = kRequest;
    ProxySessionTestAccess::downstream(*session, EPOLLIN);
  }

  void flushClient(bool closePeer = true) {
    for (int attempt = 0; attempt < 64 && !session->finished(); ++attempt)
      ProxySessionTestAccess::downstream(*session, EPOLLOUT);
    if (closePeer && !session->finished()) {
      io.clientEof = true;
      ProxySessionTestAccess::downstream(*session, EPOLLIN | EPOLLRDHUP);
    }
  }

  void checkCleanup() {
    GATEWAY_CHECK(session->finished());
    GATEWAY_CHECK(!session->hasUpstream());
    GATEWAY_CHECK(loop.timerCount() == 0);
  }

  app::GatewayConfig config;
  gateway_api::BufferBudget budget{268435456, 4194304};
  net::EventLoop loop;
  FakeIo io;
  std::unique_ptr<upstream::ConnectionPool> pool;
  net::Socket peer;
  std::unique_ptr<gateway_api::ProxySession> session;
};

SessionFixture::SessionFixture(app::Timeouts timeouts,
                               gateway_api::BufferBudget* sharedBudget)
    : config{}, loop{}, io{} {
  config.upstreamAddress = "127.0.0.1";
  config.upstreamPort = 1;
  config.timeouts = timeouts;
  int pair[2];
  GATEWAY_CHECK(socketpair(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC,
                           0, pair) == 0);
  peer.reset(pair[1]);
  io.clientFd = pair[0];
  pool =
      std::make_unique<upstream::ConnectionPool>(loop, config.upstreamPool, io);
  session = std::make_unique<gateway_api::ProxySession>(
      loop, config, io, *pool, net::Socket(pair[0]), io.now(),
      sharedBudget ? *sharedBudget : budget,
      (sharedBudget ? *sharedBudget : budget)
          .acquireCapacity(gateway_api::CapacityKind::kSession));
  session->startSession();
}

void testSessionIo() {
  SessionFixture fixture;
  fixture.io.readInterrupts = 1;
  fixture.io.connectInterrupts = 1;
  fixture.io.writeInterrupts = 1;
  fixture.startRequest();
  GATEWAY_CHECK(fixture.session->hasUpstream());
  fixture.io.blockUpstream = true;
  ProxySessionTestAccess::upstream(*fixture.session, EPOLLOUT);
  GATEWAY_CHECK(fixture.io.sentUpstream.empty());
  fixture.io.blockUpstream = false;
  for (int attempt = 0; attempt < 4; ++attempt)
    ProxySessionTestAccess::upstream(*fixture.session, EPOLLOUT);
  GATEWAY_CHECK(fixture.io.sentUpstream.ends_with(
      "{\"model\":\"m\",\"messages\":[{\"role\":\"user\",\"content\":\"x\"}]"
      "}"));
  GATEWAY_CHECK(
      !(ProxySessionTestAccess::interest(*fixture.session) & EPOLLOUT));
  fixture.io.clientEof = true;
  ProxySessionTestAccess::downstream(*fixture.session, EPOLLIN | EPOLLRDHUP);
  fixture.io.upstreamInput = kResponse;
  ProxySessionTestAccess::upstream(*fixture.session, EPOLLIN | EPOLLHUP);
  fixture.io.blockClient = true;
  fixture.flushClient();
  GATEWAY_CHECK(!fixture.session->finished());
  fixture.io.blockClient = false;
  fixture.flushClient();
  fixture.checkCleanup();
  GATEWAY_CHECK(fixture.io.sentClient.ends_with("abc"));
  GATEWAY_CHECK(fixture.io.sentClient.find("Connection: close") !=
                std::string::npos);
  SessionFixture early;
  early.io.blockUpstream = true;
  early.startRequest();
  early.io.upstreamInput = "HTTP/1.1 413 Early\r\nContent-Length: 0\r\n\r\n";
  ProxySessionTestAccess::upstream(*early.session, EPOLLIN | EPOLLOUT);
  early.flushClient();
  early.checkCleanup();
  GATEWAY_CHECK(early.io.sentUpstream.empty());
  GATEWAY_CHECK(early.io.sentClient.starts_with("HTTP/1.1 413"));
  SessionFixture cancelled;
  cancelled.startRequest();
  cancelled.io.clientReset = true;
  ProxySessionTestAccess::downstream(*cancelled.session, EPOLLIN | EPOLLERR);
  cancelled.checkCleanup();
  SessionFixture reset;
  reset.startRequest();
  reset.io.upstreamReset = true;
  ProxySessionTestAccess::upstream(*reset.session, EPOLLIN | EPOLLERR);
  reset.flushClient();
  reset.checkCleanup();
  GATEWAY_CHECK(reset.io.sentClient.starts_with("HTTP/1.1 502"));
  SessionFixture failedConnect;
  failedConnect.io.pendingConnect = true;
  failedConnect.io.connectError = ECONNREFUSED;
  failedConnect.startRequest();
  ProxySessionTestAccess::upstream(*failedConnect.session, EPOLLOUT);
  failedConnect.flushClient();
  failedConnect.checkCleanup();
  GATEWAY_CHECK(failedConnect.io.sentClient.starts_with("HTTP/1.1 502"));
}

void testDeadlines() {
  for (const std::string reason :
       {"request_timeout", "connect_timeout", "upstream_write_timeout",
        "response_timeout", "total_timeout"}) {
    app::Timeouts timeouts;
    if (reason == "request_timeout") timeouts.request = 10;
    if (reason == "connect_timeout") timeouts.connect = 10;
    if (reason == "upstream_write_timeout") timeouts.upstreamWrite = 10;
    if (reason == "response_timeout") timeouts.response = 10;
    if (reason == "total_timeout") timeouts.total = 10;
    SessionFixture fixture(timeouts);
    if (reason == "connect_timeout") fixture.io.pendingConnect = true;
    if (reason != "request_timeout") fixture.startRequest();
    fixture.io.time += std::chrono::milliseconds(11);
    ProxySessionTestAccess::deadline(*fixture.session);
    fixture.flushClient();
    fixture.checkCleanup();
    GATEWAY_CHECK(fixture.io.sentClient.find(reason) != std::string::npos);
  }
  app::Timeouts lateTimeouts;
  lateTimeouts.response = 10;
  lateTimeouts.upstreamWrite = 20;
  SessionFixture late(lateTimeouts);
  late.startRequest();
  late.io.time += std::chrono::milliseconds(100000);
  ProxySessionTestAccess::deadline(*late.session);
  late.flushClient();
  late.checkCleanup();
  GATEWAY_CHECK(late.io.sentClient.find("response_timeout") !=
                std::string::npos);
  app::Timeouts totalTimeouts;
  totalTimeouts.total = 10;
  SessionFixture beforeOutput(totalTimeouts);
  beforeOutput.startRequest();
  beforeOutput.io.upstreamInput = kResponse;
  ProxySessionTestAccess::upstream(*beforeOutput.session, EPOLLIN);
  beforeOutput.io.time += std::chrono::milliseconds(11);
  ProxySessionTestAccess::deadline(*beforeOutput.session);
  beforeOutput.flushClient();
  beforeOutput.checkCleanup();
  GATEWAY_CHECK(beforeOutput.io.sentClient.find("total_timeout") !=
                std::string::npos);
  app::Timeouts timeouts;
  timeouts.downstreamWrite = 10;
  SessionFixture slow(timeouts);
  slow.startRequest();
  slow.io.upstreamInput = kResponse;
  ProxySessionTestAccess::upstream(*slow.session, EPOLLIN);
  slow.io.blockClient = true;
  slow.io.time += std::chrono::milliseconds(11);
  ProxySessionTestAccess::deadline(*slow.session);
  slow.checkCleanup();
  GATEWAY_CHECK(slow.io.sentClient.empty());
  timeouts = {};
  timeouts.request = 10;
  timeouts.downstreamWrite = 3000;
  SessionFixture errorDrain(timeouts);
  errorDrain.io.time += std::chrono::milliseconds(11);
  ProxySessionTestAccess::deadline(*errorDrain.session);
  errorDrain.io.blockClient = true;
  errorDrain.io.time += std::chrono::milliseconds(999);
  ProxySessionTestAccess::downstream(*errorDrain.session, EPOLLOUT);
  GATEWAY_CHECK(!errorDrain.session->finished());
  errorDrain.io.time += std::chrono::milliseconds(2);
  ProxySessionTestAccess::deadline(*errorDrain.session);
  errorDrain.checkCleanup();
  SessionFixture partial(timeouts);
  partial.startRequest();
  partial.io.upstreamInput = kResponse;
  ProxySessionTestAccess::upstream(*partial.session, EPOLLIN);
  partial.io.sendLimit = 1;
  ProxySessionTestAccess::downstream(*partial.session, EPOLLOUT);
  GATEWAY_CHECK(!partial.io.sentClient.empty());
  partial.io.time += std::chrono::milliseconds(70000);
  ProxySessionTestAccess::deadline(*partial.session);
  partial.checkCleanup();
  GATEWAY_CHECK(partial.io.sentClient.find("HTTP/1.1 ", 1) ==
                std::string::npos);
  SessionFixture allocation;
  allocation.io.clientInput = "bad\r\n";
  failNextAllocation = true;
  ProxySessionTestAccess::downstream(*allocation.session, EPOLLIN);
  failNextAllocation = false;
  // 错误正文无法分配时允许直接关闭，仍须解除timer和Channel。
  if (!allocation.session->finished()) allocation.flushClient();
  allocation.checkCleanup();
}

void completeNormalOutput(SessionFixture& fixture) {
  fixture.startRequest();
  fixture.io.upstreamInput = kResponse;
  ProxySessionTestAccess::upstream(*fixture.session, EPOLLIN);
  fixture.flushClient(false);
}

void testClosing() {
  SessionFixture ordered;
  completeNormalOutput(ordered);
  GATEWAY_CHECK(!ordered.session->finished());
  GATEWAY_CHECK(ordered.io.shutdownSuccesses == 1);
  GATEWAY_CHECK(ordered.io.operations.back() == "shutdown");
  GATEWAY_CHECK(ordered.io.operations[ordered.io.operations.size() - 2] ==
                "send");
  GATEWAY_CHECK(!ordered.session->hasUpstream());
  GATEWAY_CHECK(ordered.loop.timerCount() == 1);
  GATEWAY_CHECK(!(ProxySessionTestAccess::downstreamInterest(*ordered.session) &
                  EPOLLOUT));
  const auto output = ordered.io.sentClient;
  ProxySessionTestAccess::downstream(*ordered.session, EPOLLIN);
  GATEWAY_CHECK(!ordered.session->finished());  // EAGAIN不能关闭。
  ordered.io.clientInput.assign(200000, 'x');
  ProxySessionTestAccess::downstream(*ordered.session, EPOLLIN | EPOLLOUT);
  GATEWAY_CHECK(ordered.io.clientInput.size() == 200000 - 65536);
  GATEWAY_CHECK(ordered.io.sentClient == output &&
                ordered.io.shutdownSuccesses == 1);
  ordered.io.clientInput.clear();
  ordered.io.clientEof = true;
  ProxySessionTestAccess::downstream(*ordered.session, EPOLLIN | EPOLLRDHUP);
  ordered.checkCleanup();
  GATEWAY_CHECK(fcntl(ordered.io.clientFd, F_GETFD) == -1 && errno == EBADF);
  ProxySessionTestAccess::downstream(*ordered.session, EPOLLIN | EPOLLOUT);
  ProxySessionTestAccess::deadline(*ordered.session);
  GATEWAY_CHECK(ordered.io.sentClient == output &&
                ordered.io.shutdownSuccesses == 1);

  SessionFixture interrupted;
  interrupted.startRequest();
  interrupted.io.upstreamInput = kResponse;
  ProxySessionTestAccess::upstream(*interrupted.session, EPOLLIN);
  interrupted.io.shutdownInterrupts = 70;
  interrupted.io.sendLimit = 65536;
  ProxySessionTestAccess::downstream(*interrupted.session, EPOLLOUT);
  GATEWAY_CHECK(interrupted.io.shutdownAttempts == 63 &&
                interrupted.io.shutdownSuccesses == 0);
  GATEWAY_CHECK(
      ProxySessionTestAccess::downstreamInterest(*interrupted.session) &
      EPOLLOUT);
  interrupted.io.time += std::chrono::milliseconds(900);
  ProxySessionTestAccess::downstream(*interrupted.session, EPOLLOUT);
  GATEWAY_CHECK(interrupted.io.shutdownAttempts == 71 &&
                interrupted.io.shutdownSuccesses == 1);
  interrupted.io.time += std::chrono::milliseconds(100);
  ProxySessionTestAccess::deadline(*interrupted.session);
  interrupted.checkCleanup();  // EINTR没有把完成时刻推迟900ms。

  SessionFixture failed;
  failed.io.shutdownError = ENOTCONN;
  completeNormalOutput(failed);
  failed.checkCleanup();
  GATEWAY_CHECK(failed.io.shutdownAttempts == 1 &&
                failed.io.shutdownSuccesses == 0);
  GATEWAY_CHECK(failed.io.sentClient.ends_with("abc"));

  SessionFixture eofFirst;
  eofFirst.io.clientEof = true;
  eofFirst.startRequest();
  ProxySessionTestAccess::downstream(*eofFirst.session, EPOLLIN | EPOLLRDHUP);
  GATEWAY_CHECK(!eofFirst.session->finished());
  eofFirst.io.upstreamInput = kResponse;
  ProxySessionTestAccess::upstream(*eofFirst.session, EPOLLIN);
  eofFirst.flushClient(false);
  eofFirst.checkCleanup();
  GATEWAY_CHECK(eofFirst.io.shutdownSuccesses == 1 &&
                eofFirst.io.sentClient.ends_with("abc"));

  for (bool reset : {false, true}) {
    SessionFixture exception;
    completeNormalOutput(exception);
    const auto sent = exception.io.sentClient;
    exception.io.throwRead = !reset;
    exception.io.clientReset = reset;
    ProxySessionTestAccess::downstream(*exception.session, EPOLLIN);
    exception.checkCleanup();
    GATEWAY_CHECK(exception.io.sentClient ==
                  sent);  // closing异常不生成第二响应。
  }

  for (int total : {60000, 400}) {
    app::Timeouts timeouts;
    timeouts.total = total;
    timeouts.downstreamWrite = 10;
    SessionFixture deadline(timeouts);
    completeNormalOutput(deadline);
    const int closingLimit = std::min(total, 1000);
    deadline.io.time += std::chrono::milliseconds(closingLimit - 1);
    deadline.io.clientInput.assign(100000, 'x');
    ProxySessionTestAccess::downstream(*deadline.session, EPOLLIN);
    GATEWAY_CHECK(
        !deadline.session->finished());  // downstreamWrite不再约束closing。
    deadline.io.time += std::chrono::milliseconds(1);
    ProxySessionTestAccess::downstream(*deadline.session, EPOLLIN | EPOLLOUT);
    ProxySessionTestAccess::deadline(*deadline.session);
    deadline.checkCleanup();
    GATEWAY_CHECK(deadline.io.sentClient.ends_with("abc"));
    GATEWAY_CHECK(deadline.io.sentClient.find("HTTP/1.1 ", 1) ==
                  std::string::npos);
  }

  for (bool totalExpired : {false, true}) {
    app::Timeouts timeouts;
    timeouts.request = 10;
    timeouts.total = totalExpired ? 10 : 60000;
    SessionFixture error(timeouts);
    error.io.time += std::chrono::milliseconds(11);
    ProxySessionTestAccess::deadline(*error.session);
    error.io.time += std::chrono::milliseconds(800);
    error.flushClient(false);
    GATEWAY_CHECK(!error.session->finished() &&
                  error.io.shutdownSuccesses == 1);
    GATEWAY_CHECK(error.io.sentClient.find(totalExpired ? "total_timeout"
                                                        : "request_timeout") !=
                  std::string::npos);
    error.io.time += std::chrono::milliseconds(199);
    ProxySessionTestAccess::downstream(*error.session, EPOLLIN);
    GATEWAY_CHECK(!error.session->finished());
    error.io.time += std::chrono::milliseconds(1);
    ProxySessionTestAccess::deadline(*error.session);
    error.checkCleanup();  // 输出已耗800ms，closing只剩200ms。
  }
}

void testReuseSessionBoundaries() {
  for (int scenario = 0; scenario < 11; ++scenario) {
    SessionFixture fixture;
    fixture.startRequest();
    fixture.io.sendLimit = 65536;
    ProxySessionTestAccess::upstream(*fixture.session, EPOLLOUT);
    GATEWAY_CHECK(!fixture.io.sentUpstream.empty());
    fixture.io.upstreamInput = kResponse;
    if (scenario == 1) fixture.io.upstreamInput += "junk";
    if (scenario == 2)
      fixture.io.upstreamInput =
          "HTTP/1.1 200 OK\r\nConnection: keep-alive\r\ncOnNeCtIoN: foo, "
          "ClOsE\r\nContent-Length: 3\r\n\r\nabc";
    ProxySessionTestAccess::upstream(
        *fixture.session, EPOLLIN | (scenario == 3 ? EPOLLRDHUP : 0));
    if (scenario == 0 || scenario >= 4) {
      GATEWAY_CHECK(fixture.session->hasUpstream());
      GATEWAY_CHECK(fixture.pool->snapshot().leased == 1 &&
                    fixture.pool->snapshot().idle == 0);
    }
    if (scenario == 4) {  // 已完整响应、下游仍阻塞，迟到数据不覆盖首响应。
      fixture.io.upstreamInput = "late";
      ProxySessionTestAccess::upstream(*fixture.session, EPOLLIN);
    }
    if (scenario == 5) fixture.io.peekResult = 1;
    if (scenario == 6) fixture.io.shutdownError = EIO;
    if (scenario == 7) fixture.pool->stopAcquisition();
    if (scenario == 8) {
      fixture.io.clientReset = true;
      ProxySessionTestAccess::downstream(*fixture.session, EPOLLIN | EPOLLERR);
    }
    if (scenario == 9) {
      fixture.io.blockClient = true;
      fixture.io.time += std::chrono::milliseconds(60001);
      ProxySessionTestAccess::deadline(*fixture.session);
    }
    if (scenario == 10) {
      fixture.io.shutdownInterrupts = 100;
      ProxySessionTestAccess::downstream(*fixture.session, EPOLLOUT);
      GATEWAY_CHECK(fixture.session->hasUpstream() &&
                    fixture.pool->snapshot().idle == 0);
      fixture.io.shutdownInterrupts = 0;
    }
    fixture.flushClient(false);
    const bool reused = scenario == 0 || scenario == 10;
    GATEWAY_CHECK(fixture.pool->snapshot().idle == (reused ? 1U : 0U));
    GATEWAY_CHECK(!fixture.session->hasUpstream());
    if (scenario != 8 && scenario != 9)
      GATEWAY_CHECK(fixture.io.sentClient.ends_with("abc"));
    if (reused) {
      auto next = fixture.pool->acquireConnection({});
      GATEWAY_CHECK(next.reused());
      fixture.io.clientReset = true;
      ProxySessionTestAccess::downstream(*fixture.session, EPOLLIN | EPOLLERR);
      GATEWAY_CHECK(next.valid());  // 旧closing不得失效新租约。
    }
    fixture.session->finishSession();
    fixture.pool->closeAllConnections();
    fixture.pool->cleanupRetired();
    fixture.checkCleanup();
  }
  SessionFixture noRetry;
  noRetry.startRequest();
  noRetry.io.failUpstreamWrite = true;
  ProxySessionTestAccess::upstream(*noRetry.session, EPOLLOUT);
  noRetry.flushClient();
  GATEWAY_CHECK(noRetry.io.sentClient.starts_with("HTTP/1.1 502"));
  GATEWAY_CHECK(noRetry.io.connectCalls == 1 &&
                noRetry.pool->snapshot().created == 1);
  noRetry.checkCleanup();
}

void testReusedFailureAndDeadlines() {
  for (bool expireTotal : {false, true}) {
    app::Timeouts limits;
    limits.response = expireTotal ? 100 : 10;
    limits.total = expireTotal ? 30 : 100;
    SessionFixture fixture(limits);
    auto seed = fixture.pool->acquireConnection({});
    seed.markConnected();
    seed.releaseReusable();
    fixture.io.time += std::chrono::milliseconds(20);
    fixture.startRequest();
    GATEWAY_CHECK(fixture.io.connectCalls == 0 &&
                  fixture.pool->snapshot().reused == 1);
    fixture.io.sendLimit = 65536;
    ProxySessionTestAccess::upstream(*fixture.session, EPOLLOUT);
    fixture.io.time += std::chrono::milliseconds(9);
    ProxySessionTestAccess::deadline(*fixture.session);
    GATEWAY_CHECK(fixture.session->hasUpstream() &&
                  fixture.io.sentClient.empty());
    fixture.io.time += std::chrono::milliseconds(1);
    ProxySessionTestAccess::deadline(*fixture.session);
    fixture.flushClient();
    GATEWAY_CHECK(fixture.io.sentClient.find(
                      expireTotal ? "total_timeout" : "response_timeout") !=
                  std::string::npos);
    fixture.checkCleanup();
  }
  SessionFixture failure;
  auto seed = failure.pool->acquireConnection({});
  seed.markConnected();
  seed.releaseReusable();
  failure.startRequest();
  failure.io.failUpstreamWrite = true;
  ProxySessionTestAccess::upstream(*failure.session, EPOLLOUT);
  failure.flushClient();
  GATEWAY_CHECK(failure.io.connectCalls == 0 &&
                failure.io.sentUpstream.empty());
  GATEWAY_CHECK(failure.io.sentClient.starts_with("HTTP/1.1 502") &&
                failure.pool->snapshot().created == 1);
  failure.checkCleanup();
}

const std::string kStreamHeaders =
    "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: "
    "chunked\r\n\r\n";

void startStreamRequest(SessionFixture& fixture, bool upload = true) {
  auto body = std::string(
      "{\"model\":\"m\",\"messages\":[{\"role\":\"user\",\"content\":\"x\"}],"
      "\"stream\":true}");
  fixture.io.clientInput =
      "POST /v1/chat/completions HTTP/1.1\r\nHost: h\r\nContent-Type: "
      "application/json\r\nContent-Length: " +
      std::to_string(body.size()) + "\r\n\r\n" + body;
  ProxySessionTestAccess::downstream(*fixture.session, EPOLLIN);
  fixture.io.sendLimit = 65536;
  if (upload) ProxySessionTestAccess::upstream(*fixture.session, EPOLLOUT);
}

void feedStream(SessionFixture& fixture, std::string bytes) {
  fixture.io.upstreamInput = std::move(bytes);
  ProxySessionTestAccess::upstream(*fixture.session, EPOLLIN);
}

void testStreamingCommitAndEarly() {
  using gateway_api::StreamingSessionTestAccess;
  for (int sent : {0, 1, 65536}) {
    SessionFixture fixture;
    startStreamRequest(fixture);
    feedStream(fixture, kStreamHeaders + "10\r\ndata: hel");
    GATEWAY_CHECK(StreamingSessionTestAccess::pending(*fixture.session) > 0);
    if (sent) {
      fixture.io.sendLimit = sent;
      fixture.io.clientSendBudget = sent;
      ProxySessionTestAccess::downstream(*fixture.session, EPOLLOUT);
    }
    GATEWAY_CHECK(StreamingSessionTestAccess::started(*fixture.session) ==
                  (sent != 0));
    const auto prefix = fixture.io.sentClient;
    if (sent == 1) GATEWAY_CHECK(prefix == "H");
    fixture.io.clientSendBudget = 16777216;
    fixture.io.upstreamEof = true;
    ProxySessionTestAccess::upstream(*fixture.session, EPOLLIN | EPOLLRDHUP);
    fixture.flushClient();
    fixture.checkCleanup();
    if (!sent)
      GATEWAY_CHECK(fixture.io.sentClient.starts_with("HTTP/1.1 502"));
    else {
      GATEWAY_CHECK(fixture.io.sentClient == prefix &&
                    !prefix.ends_with("0\r\n\r\n"));
      GATEWAY_CHECK(prefix.find("HTTP/1.1 ", 1) == std::string::npos);
    }
    GATEWAY_CHECK(fixture.pool->snapshot().total == 0);
  }
  SessionFixture early;
  startStreamRequest(early, false);
  feedStream(early, kStreamHeaders);
  GATEWAY_CHECK(!StreamingSessionTestAccess::uploaded(*early.session));
  ProxySessionTestAccess::upstream(*early.session, EPOLLOUT);
  GATEWAY_CHECK(early.io.sentUpstream.empty());
  ProxySessionTestAccess::downstream(*early.session, EPOLLOUT);
  GATEWAY_CHECK(!early.session->finished() && early.io.shutdownSuccesses == 0);
  GATEWAY_CHECK(StreamingSessionTestAccess::pending(*early.session) == 0);
  feedStream(early, "3\r\nabc\r\n0\r\n\r\n");
  early.flushClient();
  early.checkCleanup();
  GATEWAY_CHECK(early.io.sentClient.ends_with("3\r\nabc\r\n0\r\n\r\n"));
  GATEWAY_CHECK(early.pool->snapshot().total == 0);
  // 候选头已排队但还没send时，绝对response期限仍可替换为单个504。
  app::Timeouts timeoutLimits;
  timeoutLimits.response = 10;
  SessionFixture uncommitted(timeoutLimits);
  startStreamRequest(uncommitted);
  feedStream(uncommitted, kStreamHeaders);
  uncommitted.io.time += std::chrono::milliseconds(10);
  ProxySessionTestAccess::deadline(*uncommitted.session);
  uncommitted.flushClient();
  uncommitted.checkCleanup();
  GATEWAY_CHECK(uncommitted.io.sentClient.starts_with("HTTP/1.1 504") &&
                uncommitted.io.sentClient.find("HTTP/1.1 200") ==
                    std::string::npos);

  // 回调内分配异常被C边界捕获，parse返回后才生成500。
  SessionFixture allocation;
  startStreamRequest(allocation);
  allocation.io.upstreamInput = kStreamHeaders;
  failNextAllocation = true;
  ProxySessionTestAccess::upstream(*allocation.session, EPOLLIN);
  failNextAllocation = false;
  allocation.flushClient();
  allocation.checkCleanup();
  GATEWAY_CHECK(allocation.io.sentClient.starts_with("HTTP/1.1 500"));
}

void checkStreamCompletionDeadline(int framing, int committedBytes, int elapsed,
                                   int deadlineKind) {
  app::Timeouts limits;
  limits.response = deadlineKind == 1 ? 1000 : 10;
  limits.total = deadlineKind == 0 ? 1000 : 10;
  SessionFixture fixture(limits);
  startStreamRequest(fixture);
  const auto headers =
      std::string("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n") +
      (framing == 0   ? "Content-Length: 2\r\n"
       : framing == 1 ? "Transfer-Encoding: chunked\r\n"
                      : "") +
      "\r\n";
  if (committedBytes || framing == 2) {
    feedStream(fixture, headers + (framing == 1 ? "2\r\nx" : "x"));
    fixture.io.clientSendBudget = committedBytes;
    ProxySessionTestAccess::downstream(*fixture.session, EPOLLOUT);
    if (committedBytes == 1) GATEWAY_CHECK(fixture.io.sentClient == "H");
    fixture.io.upstreamInput = framing == 2   ? ""
                               : framing == 1 ? "y\r\n0\r\n\r\n"
                                              : "y";
  } else {
    fixture.io.upstreamInput =
        headers + (framing == 1 ? "2\r\nxy\r\n0\r\n\r\n" : "xy");
  }

  const auto prefix = fixture.io.sentClient;
  fixture.io.clientSendBudget = 16777216;
  fixture.io.upstreamEof = framing == 2;
  fixture.io.advanceUpstreamReadMs = elapsed;
  ProxySessionTestAccess::upstream(*fixture.session, EPOLLIN);
  fixture.flushClient();
  fixture.checkCleanup();
  if (elapsed < 10) {
    GATEWAY_CHECK(fixture.io.sentClient.starts_with("HTTP/1.1 200") &&
                  fixture.io.sentClient.ends_with("0\r\n\r\n"));
  } else if (committedBytes) {
    GATEWAY_CHECK(fixture.io.sentClient == prefix &&
                  !prefix.ends_with("0\r\n\r\n"));
  } else {
    GATEWAY_CHECK(fixture.io.sentClient.starts_with("HTTP/1.1 504") &&
                  fixture.io.sentClient.find("HTTP/1.1 200") ==
                      std::string::npos);
    if (deadlineKind != 0)
      GATEWAY_CHECK(fixture.io.sentClient.find("total_timeout") !=
                    std::string::npos);
  }
}

void testStreamingCompletionDeadlines() {
  // response、total及同刻total优先；三定界 × 三提交状态 × 截止前/等于/超过。
  for (int deadlineKind : {0, 1, 2})
    for (int framing : {0, 1, 2})
      for (int committedBytes : {0, 1, 65536})
        for (int elapsed : {9, 10, 11})
          checkStreamCompletionDeadline(framing, committedBytes, elapsed,
                                        deadlineKind);

  // 已排空批次之后的正常尾片，不能重新激活旧批次的写期限。
  app::Timeouts batchLimits;
  batchLimits.downstreamWrite = 10;
  SessionFixture batch(batchLimits);
  startStreamRequest(batch);
  feedStream(batch, kStreamHeaders + "2\r\nx");
  ProxySessionTestAccess::downstream(*batch.session, EPOLLOUT);
  batch.io.advanceUpstreamReadMs = 20;
  feedStream(batch, "y\r\n0\r\n\r\n");
  batch.flushClient();
  batch.checkCleanup();
  GATEWAY_CHECK(batch.io.sentClient.ends_with("0\r\n\r\n"));

  // 强制停止后的迟到完整响应不能恢复会话或补成功尾块。
  for (int committedBytes : {0, 1, 65536}) {
    SessionFixture fixture;
    startStreamRequest(fixture);
    feedStream(fixture, kStreamHeaders + "1\r\nx\r\n");
    fixture.io.clientSendBudget = committedBytes;
    ProxySessionTestAccess::downstream(*fixture.session, EPOLLOUT);
    const auto prefix = fixture.io.sentClient;
    fixture.session->finishSession();
    fixture.io.clientSendBudget = 16777216;
    feedStream(fixture, "0\r\n\r\n");
    ProxySessionTestAccess::downstream(*fixture.session, EPOLLOUT);
    GATEWAY_CHECK(fixture.io.sentClient == prefix &&
                  !prefix.ends_with("0\r\n\r\n"));
    fixture.checkCleanup();
  }
}

void testStreamBudgetAndConfig() {
  using namespace gateway_api;
  const std::string base =
      "{\"upstream_address\":\"127.0.0.1\",\"upstream_port\":9,";
  for (const auto* fields :
       {"\"stream_buffer\":{}",
        "\"stream_buffer\":{\"high_water_bytes\":32768,\"low_water_bytes\":0,"
        "\"max_total_bytes\":262144}",
        "\"stream_buffer\":{\"high_water_bytes\":229376,\"low_water_bytes\":"
        "229375,\"max_total_bytes\":67108864}",
        "\"timeouts_ms\":{\"stream_idle\":10}",
        "\"timeouts_ms\":{\"stream_idle\":300000}"})
    GATEWAY_CHECK(
        app::parseConfig(base + fields + "}").streamBuffer.maxTotalBytes >=
        262144);
  for (const auto* fields :
       {"\"stream_buffer\":null",
        "\"stream_buffer\":{\"high_water_bytes\":32767}",
        "\"stream_buffer\":{\"high_water_bytes\":229377}",
        "\"stream_buffer\":{\"high_water_bytes\":32768}",
        "\"stream_buffer\":{\"low_water_bytes\":196608}",
        "\"stream_buffer\":{\"low_water_bytes\":-1}",
        "\"stream_buffer\":{\"max_total_bytes\":262143}",
        "\"stream_buffer\":{\"max_total_bytes\":67108865}",
        "\"stream_buffer\":{\"max_total_bytes\":18446744073709551616}",
        "\"stream_buffer\":{\"max_total_bytes\":true}",
        "\"stream_buffer\":{\"max_total_bytes\":262144.0}",
        "\"stream_buffer\":{\"nope\":1}",
        "\"stream_buffer\":{\"low_water_bytes\":0,\"low_water_bytes\":1}",
        "\"timeouts_ms\":{\"stream_idle\":9}",
        "\"timeouts_ms\":{\"stream_idle\":300001}"}) {
    bool rejected = false;
    try {
      app::parseConfig(base + fields + "}");
    } catch (const std::invalid_argument&) {
      rejected = true;
    }
    GATEWAY_CHECK(rejected);
  }

  SessionFixture allocation;
  startStreamRequest(allocation);
  StreamingSessionTestAccess::validateHeaders(*allocation.session,
                                              kStreamHeaders);
  failNextAllocation = true;
  feedStream(allocation, "1\r\nx\r\n");
  failNextAllocation = false;
  allocation.flushClient();
  GATEWAY_CHECK(allocation.io.sentClient.starts_with("HTTP/1.1 500"));
  GATEWAY_CHECK(allocation.budget.snapshot().streamCapacity == 0 &&
                allocation.budget.snapshot().pending == 0);
  GATEWAY_CHECK(allocation.budget.snapshot().reserved == 16777216);
  allocation.session.reset();
  GATEWAY_CHECK(allocation.budget.snapshot().reserved == 0);

  for (std::uint64_t limit : {262144, 524288, 524289}) {
    BufferBudget shared(4 * BufferBudget::kSessionBytes, limit);
    SessionFixture first({}, &shared);
    startStreamRequest(first);
    feedStream(first, kStreamHeaders);
    first.flushClient(false);
    GATEWAY_CHECK(shared.snapshot().pending == 0 &&
                  shared.snapshot().streamCapacity == 262144);
    SessionFixture second({}, &shared);
    startStreamRequest(second);
    feedStream(second, kStreamHeaders);
    if (limit < 524288) {
      second.flushClient();
      GATEWAY_CHECK(second.io.sentClient.starts_with("HTTP/1.1 503") &&
                    second.io.sentClient.find("buffer_capacity") !=
                        std::string::npos);
    } else {
      SessionFixture third({}, &shared);
      startStreamRequest(third);
      feedStream(third, kStreamHeaders);
      third.flushClient();
      GATEWAY_CHECK(third.io.sentClient.starts_with("HTTP/1.1 503"));
    }
    first.session->finishSession();
    GATEWAY_CHECK(shared.snapshot().streamCapacity ==
                  (limit < 524288 ? 0 : 262144));
    SessionFixture recovered({}, &shared);
    startStreamRequest(recovered);
    feedStream(recovered, kStreamHeaders + "0\r\n\r\n");
    recovered.flushClient();
    GATEWAY_CHECK(recovered.io.sentClient.starts_with("HTTP/1.1 200"));
    second.session->finishSession();
    GATEWAY_CHECK(shared.snapshot().streamCapacity == 0 &&
                  shared.snapshot().pending == 0);
    first.session.reset();
    second.session.reset();
    recovered.session.reset();
    GATEWAY_CHECK(shared.snapshot().reserved == 0 &&
                  shared.snapshot().peakStreamCapacity <= limit);
  }
}

void testStreamProgressDeadlines() {
  using Access = gateway_api::StreamingSessionTestAccess;
  for (int elapsed : {9, 10, 11}) {
    app::Timeouts limits;
    limits.streamIdle = 10;
    SessionFixture fixture(limits);
    startStreamRequest(fixture);
    feedStream(fixture, kStreamHeaders + "100\r\nx");
    fixture.io.advanceUpstreamReadMs = elapsed;
    feedStream(fixture, "y");
    if (elapsed < 10)
      GATEWAY_CHECK(fixture.session->hasUpstream());
    else {
      fixture.flushClient();
      GATEWAY_CHECK(fixture.io.sentClient.starts_with("HTTP/1.1 504") &&
                    fixture.io.sentClient.find("stream_idle_timeout") !=
                        std::string::npos);
    }
  }
  for (int elapsed : {9, 10, 11}) {
    app::Timeouts limits;
    limits.downstreamWrite = 10;
    SessionFixture fixture(limits);
    startStreamRequest(fixture);
    feedStream(fixture, kStreamHeaders + "100\r\nx");
    fixture.io.clientSendBudget = 1;
    fixture.io.advanceClientSendMs = elapsed;
    ProxySessionTestAccess::downstream(*fixture.session, EPOLLOUT);
    GATEWAY_CHECK(fixture.io.sentClient == "H");
    GATEWAY_CHECK(fixture.session->finished() == (elapsed >= 10));
  }
  for (bool interrupted : {false, true}) {
    for (int elapsed : {9, 10, 11}) {
      app::Timeouts limits;
      limits.downstreamWrite = 10;
      SessionFixture fixture(limits);
      startStreamRequest(fixture);
      feedStream(fixture, kStreamHeaders);
      fixture.io.blockClient = true;
      fixture.io.writeInterrupts = interrupted ? 1 : 0;
      fixture.io.advanceClientSendMs = elapsed;
      ProxySessionTestAccess::downstream(*fixture.session, EPOLLOUT);
      GATEWAY_CHECK(fixture.io.sentClient.empty() &&
                    fixture.session->finished() == (elapsed >= 10));
      if (elapsed < 10) {
        fixture.io.time += std::chrono::milliseconds(1);
        ProxySessionTestAccess::deadline(*fixture.session);
        fixture.checkCleanup();
      }
    }
  }
  for (bool total : {false, true}) {
    app::Timeouts limits;
    limits.response = total ? 1000 : 10;
    limits.total = total ? 10 : 1000;
    SessionFixture fixture(limits);
    startStreamRequest(fixture);
    feedStream(fixture, kStreamHeaders);
    Access::pause(*fixture.session);
    fixture.io.time += std::chrono::milliseconds(10);
    Access::resume(*fixture.session);
    fixture.flushClient();
    fixture.checkCleanup();
    GATEWAY_CHECK(fixture.io.sentClient.starts_with("HTTP/1.1 504") &&
                  fixture.budget.snapshot().paused == 0);
  }
  app::Timeouts limits;
  limits.streamIdle = 10;
  SessionFixture frozen(limits);
  startStreamRequest(frozen);
  feedStream(frozen, kStreamHeaders);
  frozen.io.time += std::chrono::milliseconds(4);
  Access::pause(*frozen.session);
  for (int cycle = 0; cycle < 2; ++cycle) {
    frozen.io.time += std::chrono::milliseconds(20);
    Access::resume(*frozen.session);
    GATEWAY_CHECK(Access::idleDeadline(*frozen.session) - frozen.io.time ==
                  std::chrono::milliseconds(6));
    Access::pause(*frozen.session);
  }
  Access::resume(*frozen.session);
  frozen.io.time += std::chrono::milliseconds(5);
  feedStream(frozen, "10\r\n");
  GATEWAY_CHECK(frozen.session->hasUpstream());
  frozen.io.time += std::chrono::milliseconds(1);
  ProxySessionTestAccess::deadline(*frozen.session);
  frozen.flushClient();
  GATEWAY_CHECK(frozen.io.sentClient.find("stream_idle_timeout") !=
                std::string::npos);

  SessionFixture cancelled;
  startStreamRequest(cancelled);
  feedStream(cancelled, kStreamHeaders + "100\r\nx");
  Access::pause(*cancelled.session);
  cancelled.io.clientReset = true;
  ProxySessionTestAccess::downstream(*cancelled.session, EPOLLIN | EPOLLERR);
  cancelled.session->finishSession();
  Access::resume(*cancelled.session);
  ProxySessionTestAccess::deadline(*cancelled.session);
  cancelled.checkCleanup();
  const auto ended = cancelled.budget.snapshot();
  GATEWAY_CHECK(ended.streamCapacity == 0 && ended.pending == 0 &&
                ended.paused == 0);
  GATEWAY_CHECK(ended.finished[static_cast<std::size_t>(
                    gateway_api::FinishReason::kCancelled)] == 1);

  SessionFixture registration;
  startStreamRequest(registration);
  feedStream(registration, kStreamHeaders + "100\r\nx");
  Access::pause(*registration.session);
  const auto token = net::EventLoopTestAccess::exchangeToken(0);
  registration.io.sendLimit = 65536;
  ProxySessionTestAccess::downstream(*registration.session, EPOLLOUT);
  net::EventLoopTestAccess::exchangeToken(token);
  registration.checkCleanup();
  GATEWAY_CHECK(registration.budget.snapshot().streamCapacity == 0 &&
                registration.budget.snapshot().paused == 0 &&
                registration.budget.snapshot().pending == 0);
}

void testStreamingLimitsAndTime() {
  using gateway_api::StreamingSessionTestAccess;
  for (bool commit : {false, true}) {
    SessionFixture fixture;
    startStreamRequest(fixture);
    feedStream(fixture, kStreamHeaders + "100000\r\n");
    if (commit) ProxySessionTestAccess::downstream(*fixture.session, EPOLLOUT);
    const auto prefix = fixture.io.sentClient;
    fixture.io.blockClient = true;
    for (int index = 0; index < 20 && fixture.session->hasUpstream(); ++index)
      feedStream(fixture, std::string(16384, 'x'));
    GATEWAY_CHECK(fixture.session->hasUpstream() &&
                  StreamingSessionTestAccess::paused(*fixture.session));
    GATEWAY_CHECK(StreamingSessionTestAccess::pending(*fixture.session) <=
                  http::StreamOutput::kCapacity);
    GATEWAY_CHECK(fixture.io.sentClient == prefix);
    fixture.session->finishSession();
    fixture.checkCleanup();
  }
  for (const auto* kind : {"response", "total", "write"}) {
    app::Timeouts limits;
    limits.response = std::string(kind) == "response" ? 30 : 1000;
    limits.total = std::string(kind) == "total" ? 30 : 2000;
    limits.downstreamWrite = std::string(kind) == "write" ? 30 : 1000;
    SessionFixture fixture(limits);
    startStreamRequest(fixture);
    feedStream(fixture, kStreamHeaders + "1000\r\nx");
    fixture.io.sendLimit = std::string(kind) == "write" ? 1 : 65536;
    ProxySessionTestAccess::downstream(*fixture.session, EPOLLOUT);
    fixture.io.time += std::chrono::milliseconds(20);
    feedStream(fixture, "y");
    ProxySessionTestAccess::downstream(*fixture.session, EPOLLOUT);
    fixture.io.time += std::chrono::milliseconds(10);
    ProxySessionTestAccess::deadline(*fixture.session);
    if (std::string(kind) == "write") {
      GATEWAY_CHECK(!fixture.session->finished());
      fixture.io.time += std::chrono::milliseconds(20);
      ProxySessionTestAccess::deadline(*fixture.session);
    }
    fixture.checkCleanup();
    GATEWAY_CHECK(!fixture.io.sentClient.ends_with("0\r\n\r\n"));
  }
  app::Timeouts limits;
  limits.downstreamWrite = 10;
  SessionFixture batches(limits);
  startStreamRequest(batches);
  feedStream(batches, kStreamHeaders + "100\r\nx");
  ProxySessionTestAccess::downstream(*batches.session, EPOLLOUT);
  batches.io.time += std::chrono::milliseconds(20);
  ProxySessionTestAccess::deadline(*batches.session);
  GATEWAY_CHECK(!batches.session->finished());
  feedStream(batches, "y");
  batches.io.time += std::chrono::milliseconds(9);
  ProxySessionTestAccess::deadline(*batches.session);
  GATEWAY_CHECK(!batches.session->finished());
  batches.io.time += std::chrono::milliseconds(1);
  ProxySessionTestAccess::deadline(*batches.session);
  batches.checkCleanup();
}

class EventFixture {
 public:
  net::EventLoop loop;
  net::Socket fd{eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC)};
  std::unique_ptr<net::Channel> channel;
  net::Socket otherFd{eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC)};
  std::unique_ptr<net::Channel> otherChannel;
  std::size_t calls = 0;
  bool destroyPending = false;
  void onEvent(std::uint32_t) {
    ++calls;
    channel->removeChannel();
    if (otherChannel) otherChannel->removeChannel();
    destroyPending = true;
  }

  void onCleanup() {
    if (destroyPending) {
      channel.reset();
      otherChannel.reset();
      destroyPending = false;
    }
  }

  void onExpiry() { ++calls; }

  void run();
};

void EventFixture::run() {
  loop.registerCleanupCallback([this] { onCleanup(); });
  channel = std::make_unique<net::Channel>(loop, fd.fd());
  channel->registerEventCallback(
      [this](std::uint32_t events) { onEvent(events); });
  channel->setInterest(EPOLLIN);
  otherChannel = std::make_unique<net::Channel>(loop, otherFd.fd());
  otherChannel->registerEventCallback(
      [this](std::uint32_t events) { onEvent(events); });
  otherChannel->setInterest(EPOLLIN);
  const auto otherToken = otherChannel->token();
  auto token = channel->token();
  net::EventLoopTestAccess::dispatch(loop, token, EPOLLIN);
  GATEWAY_CHECK(calls == 1 && !channel);
  net::EventLoopTestAccess::dispatch(loop, otherToken, EPOLLIN);
  GATEWAY_CHECK(calls == 1);
  const int oldFd = fd.release();
  ::close(oldFd);
  net::Socket replacement(eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC));
  if (replacement.fd() != oldFd) {
    GATEWAY_CHECK(dup2(replacement.fd(), oldFd) == oldFd);
    fd.reset(oldFd);
  } else
    fd = std::move(replacement);
  channel = std::make_unique<net::Channel>(loop, fd.fd());
  channel->registerEventCallback(
      [this](std::uint32_t events) { onEvent(events); });
  channel->setInterest(EPOLLIN);
  GATEWAY_CHECK(channel->token() != token);
  net::EventLoopTestAccess::dispatch(loop, token, EPOLLIN);
  GATEWAY_CHECK(calls == 1 && loop.counters().stale == 2);
  auto timer =
      loop.addTimer(timer::TimerQueue::Clock::now(), [this] { onExpiry(); });
  GATEWAY_CHECK(loop.cancelTimer(timer));
  loop.pollOnce(0);
  GATEWAY_CHECK(calls == 1);
  loop.addTimer(timer::TimerQueue::Clock::now(), [this] { onExpiry(); });
  loop.pollOnce(0);
  GATEWAY_CHECK(calls == 2);
  channel->removeChannel();
  channel.reset();
  const auto next = net::EventLoopTestAccess::exchangeToken(0);
  channel = std::make_unique<net::Channel>(loop, fd.fd());
  channel->registerEventCallback(
      [this](std::uint32_t events) { onEvent(events); });
  bool rejected = false;
  try {
    channel->setInterest(EPOLLIN);
  } catch (const std::overflow_error&) {
    rejected = true;
  }

  net::EventLoopTestAccess::exchangeToken(next);
  GATEWAY_CHECK(rejected);
  channel.reset();
}

std::size_t fdCount() {
  return std::distance(std::filesystem::directory_iterator("/proc/self/fd"),
                       std::filesystem::directory_iterator());
}

void testConfig() {
  const std::string base =
      "{\"upstream_address\":\"127.0.0.1\",\"upstream_port\":9";
  for (const auto& fields :
       {",\"listen_port\":0", ",\"listen_port\":65535",
        ",\"max_connections\":1", ",\"max_connections\":256",
        ",\"max_reserved_bytes\":16777216",
        ",\"max_reserved_bytes\":4294967296",
        ",\"timeouts_ms\":{\"total\":10,\"request\":300000}"})
    GATEWAY_CHECK(app::parseConfig(base + fields + "}").upstreamPort == 9);
  for (int size : {65535, 65536, 65537}) {
    auto text = base + "}";
    text.append(size - text.size(), ' ');
    bool accepted = true;
    try {
      app::parseConfig(text);
    } catch (const std::invalid_argument&) {
      accepted = false;
    }

    GATEWAY_CHECK(accepted == (size <= 65536));
  }
}

net::Socket connectClient(std::uint16_t port) {
  net::Socket client(::socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0));
  sockaddr_in target{};
  target.sin_family = AF_INET;
  target.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  target.sin_port = htons(port);
  GATEWAY_CHECK(::connect(client.fd(),
                          reinterpret_cast<const sockaddr*>(&target),
                          sizeof(target)) == 0);
  client.setNonBlocking();
  return client;
}

void testRuntimeBudgets() {
  for (std::uint64_t slots : {1, 2}) {
    app::GatewayConfig config;
    config.listenPort = 0;
    config.upstreamAddress = "127.0.0.1";
    config.upstreamPort = 9;
    config.maxConnections = 2;
    config.maxReservedBytes =
        slots * gateway_api::ProxySession::kReservationBytes;
    gateway_api::GatewayRuntime runtime(config);
    auto port = runtime.startListener();
    auto first = connectClient(port);
    for (int attempt = 0;
         attempt < 20 && runtime.snapshot().activeSessions != 1; ++attempt)
      runtime.pollOnce(5);
    GATEWAY_CHECK(runtime.snapshot().activeSessions == 1);
    auto second = connectClient(port);
    runtime.pollOnce(10);
    GATEWAY_CHECK(runtime.snapshot().activeSessions == slots);
    auto third = connectClient(port);
    runtime.pollOnce(10);
    GATEWAY_CHECK(runtime.snapshot().activeSessions == slots);
    GATEWAY_CHECK(runtime.snapshot().reservedBytes ==
                  slots * gateway_api::ProxySession::kReservationBytes);
    linger reset{1, 0};
    setsockopt(first.fd(), SOL_SOCKET, SO_LINGER, &reset, sizeof(reset));
    setsockopt(second.fd(), SOL_SOCKET, SO_LINGER, &reset, sizeof(reset));
    first.reset();
    second.reset();
    third.reset();
    for (int count = 0; count < 8 && runtime.snapshot().activeSessions; ++count)
      runtime.pollOnce(5);
    GATEWAY_CHECK(runtime.snapshot().activeSessions == 0 &&
                  runtime.snapshot().reservedBytes == 0 &&
                  runtime.snapshot().activeTimers == 0 &&
                  runtime.snapshot().activeUpstreams == 0);
    runtime.requestShutdown();
    runtime.pollOnce(0);
  }
}

void testRuntimePoolSnapshots() {
  net::Socket backend = net::Socket::createTcp();
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  GATEWAY_CHECK(::bind(backend.fd(), reinterpret_cast<sockaddr*>(&address),
                       sizeof(address)) == 0);
  backend.listen(8);
  app::GatewayConfig config;
  config.listenPort = 0;
  config.upstreamAddress = "127.0.0.1";
  config.upstreamPort = backend.localPort();
  gateway_api::GatewayRuntime runtime(config);
  const auto port = runtime.startListener();
  net::Socket upstream;
  for (int round = 0; round < 20; ++round) {
    auto client = connectClient(port);
    GATEWAY_CHECK(
        ::send(client.fd(), kRequest.data(), kRequest.size(), MSG_NOSIGNAL) ==
        static_cast<ssize_t>(kRequest.size()));
    std::string request;
    for (int step = 0;
         step < 200 && request.find("\r\n\r\n") == std::string::npos; ++step) {
      runtime.pollOnce(1);
      if (!upstream.valid())
        upstream.reset(::accept4(backend.fd(), nullptr, nullptr,
                                 SOCK_NONBLOCK | SOCK_CLOEXEC));
      if (upstream.valid()) {
        char bytes[4096];
        const auto count = ::recv(upstream.fd(), bytes, sizeof(bytes), 0);
        if (count > 0) request.append(bytes, count);
      }
    }
    GATEWAY_CHECK(request.starts_with("POST ") &&
                  runtime.snapshot().pool.leased == 1);
    GATEWAY_CHECK(::send(upstream.fd(), kResponse.data(), kResponse.size(),
                         MSG_NOSIGNAL) ==
                  static_cast<ssize_t>(kResponse.size()));
    std::string response;
    bool eof = false;
    for (int step = 0; step < 200 && !eof; ++step) {
      runtime.pollOnce(1);
      char bytes[4096];
      const auto count = ::recv(client.fd(), bytes, sizeof(bytes), 0);
      if (count > 0) response.append(bytes, count);
      if (count == 0) eof = true;
    }
    GATEWAY_CHECK(eof && response.ends_with("abc"));
    const auto held = runtime.snapshot();
    GATEWAY_CHECK(held.activeSessions == 1 && held.reservedBytes == 16777216);
    GATEWAY_CHECK(held.pool.total == 1 && held.pool.idle == 1 &&
                  held.activeUpstreams == 0 && held.activeTimers == 2);
    client.reset();
    for (int step = 0; step < 20 && runtime.snapshot().activeSessions; ++step)
      runtime.pollOnce(1);
    const auto idle = runtime.snapshot();
    GATEWAY_CHECK(idle.activeSessions == 0 && idle.reservedBytes == 0 &&
                  idle.activeTimers == 1 && idle.pool.idle == 1);
    GATEWAY_CHECK(idle.pool.created == 1 &&
                  idle.pool.reused == static_cast<std::uint64_t>(round));
  }
  GATEWAY_CHECK(::raise(SIGTERM) == 0);
  runtime.pollOnce(0);
  const auto stopped = runtime.snapshot();
  GATEWAY_CHECK(stopped.activeSessions == 0 && stopped.reservedBytes == 0 &&
                stopped.pool.total == 0 && stopped.pool.retired == 0 &&
                stopped.activeTimers == 0);
}

void testRuntimeStreamSnapshots() {
  for (int stopMode : {0, 1, 2, 3}) {
    net::Socket backend = net::Socket::createTcp();
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    GATEWAY_CHECK(::bind(backend.fd(), reinterpret_cast<sockaddr*>(&address),
                         sizeof(address)) == 0);
    backend.listen(8);
    app::GatewayConfig config;
    config.listenPort = 0;
    config.upstreamAddress = "127.0.0.1";
    config.upstreamPort = backend.localPort();
    config.timeouts.shutdown = 30;
    gateway_api::GatewayRuntime runtime(config);
    const auto port = runtime.startListener();
    auto client = connectClient(port);
    const auto body = std::string(
        "{\"model\":\"m\",\"messages\":[{\"role\":\"user\",\"content\":\"x\"}],"
        "\"stream\":true}");
    const auto request =
        "POST /v1/chat/completions HTTP/1.1\r\nHost: h\r\nContent-Type: "
        "application/json\r\nContent-Length: " +
        std::to_string(body.size()) + "\r\n\r\n" + body;
    GATEWAY_CHECK(::send(client.fd(), request.data(), request.size(),
                         MSG_NOSIGNAL) == static_cast<ssize_t>(request.size()));
    net::Socket upstream;
    for (int step = 0; step < 50 && !upstream.valid(); ++step) {
      runtime.pollOnce(1);
      upstream.reset(::accept4(backend.fd(), nullptr, nullptr,
                               SOCK_NONBLOCK | SOCK_CLOEXEC));
    }
    GATEWAY_CHECK(upstream.valid());
    const auto prefix =
        kStreamHeaders + (stopMode == 3 ? "" : "20\r\ndata: hel");
    GATEWAY_CHECK(::send(upstream.fd(), prefix.data(), prefix.size(),
                         MSG_NOSIGNAL) == static_cast<ssize_t>(prefix.size()));
    std::string response;
    for (int step = 0;
         step < 100 &&
         response.find(stopMode == 3 ? "\r\n\r\n" : "data: hel") ==
             std::string::npos;
         ++step) {
      runtime.pollOnce(1);
      char bytes[4096];
      const auto count = ::recv(client.fd(), bytes, sizeof(bytes), 0);
      if (count > 0) response.append(bytes, count);
    }
    GATEWAY_CHECK(response.starts_with("HTTP/1.1 200"));
    const auto active = runtime.snapshot();
    GATEWAY_CHECK(active.activeSessions == 1 &&
                  active.reservedBytes == 16777216 && active.pool.leased == 1 &&
                  active.pool.idle == 0 && active.activeTimers == 1);
    if (stopMode) {
      GATEWAY_CHECK(::raise(SIGTERM) == 0);
      runtime.pollOnce(0);
      if (stopMode == 2 || stopMode == 3) {
        GATEWAY_CHECK(::raise(SIGINT) == 0);
        runtime.pollOnce(0);
      }
    } else {
      const auto tail = std::string(23, 'x') + "\r\n0\r\n\r\n";
      GATEWAY_CHECK(::send(upstream.fd(), tail.data(), tail.size(),
                           MSG_NOSIGNAL) == static_cast<ssize_t>(tail.size()));
    }
    bool eof = false;
    for (int step = 0; step < 200 && !eof; ++step) {
      runtime.pollOnce(1);
      // 事件循环停止后 pollOnce 不再等待；仍须等待内核交付 FIN/RST。
      pollfd clientEvent{client.fd(), POLLIN, 0};
      GATEWAY_CHECK(::poll(&clientEvent, 1, 5) >= 0);
      char bytes[4096];
      const auto count = ::recv(client.fd(), bytes, sizeof(bytes), 0);
      if (count > 0) response.append(bytes, count);
      if (count == 0 || (count < 0 && errno == ECONNRESET)) eof = true;
    }
    GATEWAY_CHECK(eof);
    GATEWAY_CHECK(response.ends_with("0\r\n\r\n") == (stopMode == 0));
    client.reset();
    for (int step = 0; step < 50 && runtime.snapshot().activeSessions; ++step)
      runtime.pollOnce(1);
    const auto released = runtime.snapshot();
    GATEWAY_CHECK(released.activeSessions == 0 && released.reservedBytes == 0 &&
                  released.pool.total == 0 && released.pool.retired == 0 &&
                  released.activeTimers == 0);
    if (!stopMode) {
      GATEWAY_CHECK(::raise(SIGTERM) == 0);
      runtime.pollOnce(0);
    }
  }
}

void testPoolAllocationFailures() {
  SessionFixture fixture;
  auto baseline = fdCount();
  failNextAllocation = true;
  bool rejected = false;
  try {
    auto lease = fixture.pool->acquireConnection({});
  } catch (const std::bad_alloc&) {
    rejected = true;
  }
  failNextAllocation = false;
  GATEWAY_CHECK(rejected && fixture.pool->snapshot().total == 0 &&
                fdCount() == baseline);
  auto lease = fixture.pool->acquireConnection({});
  lease.markConnected();
  const auto originalToken = net::EventLoopTestAccess::exchangeToken(0);
  rejected = false;
  try {
    lease.releaseReusable();
  } catch (const std::overflow_error&) {
    rejected = true;
  }
  net::EventLoopTestAccess::exchangeToken(originalToken);
  GATEWAY_CHECK(rejected && !lease.valid() &&
                fixture.pool->snapshot().total == 0 &&
                fixture.loop.timerCount() == 1);
  fixture.pool->cleanupRetired();
  GATEWAY_CHECK(fdCount() == baseline);
}

void testRuntimeClosingBudgets() {
  for (int stopMode : {0, 1, 2}) {
    app::GatewayConfig config;
    config.listenPort = 0;
    config.upstreamAddress = "127.0.0.1";
    config.upstreamPort = 9;
    config.maxConnections = 1;
    config.maxReservedBytes = gateway_api::ProxySession::kReservationBytes;
    config.timeouts.shutdown = 50;
    gateway_api::GatewayRuntime runtime(config);
    const auto port = runtime.startListener();
    auto client = connectClient(port);
    GATEWAY_CHECK(::send(client.fd(), "bad\r\n", 5, MSG_NOSIGNAL) == 5);
    std::string response;
    bool eof = false;
    for (int attempt = 0; attempt < 100 && !eof; ++attempt) {
      runtime.pollOnce(5);
      char bytes[4096];
      const auto count = ::recv(client.fd(), bytes, sizeof(bytes), 0);
      if (count > 0)
        response.append(bytes, count);
      else if (count == 0)
        eof = true;
      else
        GATEWAY_CHECK(errno == EAGAIN || errno == EWOULDBLOCK);
    }

    GATEWAY_CHECK(eof && response.starts_with("HTTP/1.1 400"));
    const auto held = runtime.snapshot();
    GATEWAY_CHECK(held.activeSessions == 1 && held.reservedBytes == 16777216 &&
                  held.activeTimers == 1 && held.activeUpstreams == 0);
    auto rejected = connectClient(port);
    runtime.pollOnce(10);
    char byte;
    ssize_t rejectedRead = -1;
    for (int attempt = 0; attempt < 20 && rejectedRead != 0; ++attempt) {
      runtime.pollOnce(5);
      rejectedRead = ::recv(rejected.fd(), &byte, 1, 0);
      GATEWAY_CHECK(rejectedRead == 0 || errno == EAGAIN ||
                    errno == EWOULDBLOCK);
    }

    GATEWAY_CHECK(rejectedRead == 0);
    GATEWAY_CHECK(runtime.snapshot().reservedBytes == 16777216);
    GATEWAY_CHECK(::send(client.fd(), "extra", 5, MSG_NOSIGNAL) == 5);
    runtime.pollOnce(0);
    GATEWAY_CHECK(runtime.snapshot().activeSessions == 1);
    if (stopMode == 0) {
      GATEWAY_CHECK(::shutdown(client.fd(), SHUT_WR) == 0);
    } else {
      GATEWAY_CHECK(::raise(SIGTERM) == 0);
      runtime.pollOnce(0);
      GATEWAY_CHECK(runtime.snapshot().activeSessions == 1);
      if (stopMode == 2) {
        GATEWAY_CHECK(::raise(SIGINT) == 0);
        runtime.pollOnce(0);
      }
    }
    for (int attempt = 0; attempt < 40 && runtime.snapshot().activeSessions;
         ++attempt)
      runtime.pollOnce(5);
    const auto released = runtime.snapshot();
    std::cout << "closing runtime stopMode=" << stopMode
              << " active=" << released.activeSessions
              << " reserved=" << released.reservedBytes
              << " timers=" << released.activeTimers
              << " upstreams=" << released.activeUpstreams << std::endl;
    GATEWAY_CHECK(released.activeSessions == 0 && released.reservedBytes == 0 &&
                  released.activeTimers == 0 && released.activeUpstreams == 0);
  }
}

}  // namespace

int main() {
  try {
    testConfig();
    EventFixture events;
    events.run();
    const auto descriptors = fdCount();
    testSessionIo();
    testDeadlines();
    testClosing();
    testReuseSessionBoundaries();
    testReusedFailureAndDeadlines();
    testStreamingCommitAndEarly();
    testStreamingLimitsAndTime();
    testStreamingCompletionDeadlines();
    testStreamBudgetAndConfig();
    testStreamProgressDeadlines();
    testPoolAllocationFailures();
    testRuntimePoolSnapshots();
    testRuntimeStreamSnapshots();
    testRuntimeBudgets();
    testRuntimeClosingBudgets();
    GATEWAY_CHECK(fdCount() == descriptors);
    std::cout << "Runtime checks: " << test::checks << '\n';
    return 0;
  } catch (const std::exception& error) {
    failNextAllocation = false;
    std::cerr << error.what() << '\n';
    return 1;
  }
}
