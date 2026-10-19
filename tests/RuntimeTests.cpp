#include <arpa/inet.h>
#include <fcntl.h>
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
    return session.upstreamChannel_ ? session.upstreamChannel_->interest() : 0;
  }

  static std::uint32_t downstreamInterest(ProxySession& session) {
    return session.downstreamChannel_->interest();
  }

  static std::size_t uploaded(ProxySession& session) {
    return session.upstreamOffset_;
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

  int shutdownWrite(int) override;

  ssize_t receiveBytes(int fd, void* data, std::size_t size) override;
  ssize_t sendBytes(int fd, const void* data, std::size_t size) override;

  std::vector<std::string> operations;
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
  int writeInterrupts = 0;

  bool blockUpstream = false;
  bool blockClient = false;
  bool clientEof = false;
  bool clientReset = false;
  bool upstreamReset = false;
  bool upstreamEof = false;
  std::size_t sendLimit = 7;
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
  if (writeInterrupts-- > 0) {
    errno = EINTR;
    return -1;
  }
  const bool client = fd == clientFd;
  if (client ? blockClient : blockUpstream) {
    errno = EAGAIN;
    return -1;
  }

  if (client) operations.push_back("send");
  const auto count = std::min(size, sendLimit);
  (client ? sentClient : sentUpstream)
      .append(static_cast<const char*>(data), count);
  return count;
}

class SessionFixture {
 public:
  explicit SessionFixture(app::Timeouts timeouts = {});

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
  net::EventLoop loop;
  FakeIo io;
  net::Socket peer;
  std::unique_ptr<gateway_api::ProxySession> session;
};

SessionFixture::SessionFixture(app::Timeouts timeouts)
    : config{}, loop{}, io{} {
  config.upstreamAddress = "127.0.0.1";
  config.upstreamPort = 1;
  config.timeouts = timeouts;
  int pair[2];
  GATEWAY_CHECK(socketpair(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC,
                           0, pair) == 0);
  peer.reset(pair[1]);
  io.clientFd = pair[0];
  session = std::make_unique<gateway_api::ProxySession>(
      loop, config, io, net::Socket(pair[0]), io.now());
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
