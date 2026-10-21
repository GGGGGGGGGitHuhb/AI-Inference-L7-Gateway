#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <string>

#include "TestSupport.h"
#include "gateway/GatewayRuntime.h"

namespace gateway::net {
struct EventLoopTestAccess {
  static void dispatch(EventLoop& loop, std::uint64_t token) {
    loop.dispatchChannelEvent(token, EPOLLIN | EPOLLHUP | EPOLLERR);
  }
};
}  // namespace gateway::net

namespace gateway::upstream {
struct ConnectionPoolTestAccess {
  static std::uint64_t token(ConnectionPool& pool,
                             const ConnectionLease& lease) {
    auto* entry = pool.findLease(lease.id(), lease.generation());
    return entry ? entry->channel.token() : 0;
  }
};
}  // namespace gateway::upstream

namespace gateway::gateway_api {
struct StreamingSessionTestAccess {
  static void readUpstream(ProxySession& session) {
    session.onUpstreamEvent(EPOLLIN);
  }

  static bool paused(const ProxySession& session) {
    return session.upstreamPaused_;
  }

  static std::uint64_t reads(const ProxySession& session) {
    return session.upstreamReadCalls_;
  }

  static std::uint64_t bytes(const ProxySession& session) {
    return session.upstreamReadBytes_;
  }

  static std::size_t pending(const ProxySession& session) {
    return session.streamOutput_ ? session.streamOutput_->size() : 0;
  }

  static std::uint64_t token(ProxySession& session) {
    return upstream::ConnectionPoolTestAccess::token(session.pool_,
                                                     session.upstreamLease_);
  }

  static int clientFd(const ProxySession& session) {
    return session.downstreamSocket_.fd();
  }
};

struct RuntimeTestAccess {
  static void staleEvent(GatewayRuntime& runtime, std::uint64_t token) {
    net::EventLoopTestAccess::dispatch(runtime.loop_, token);
  }

  static ProxySession* first(GatewayRuntime& runtime) {
    return runtime.sessions_.empty() ? nullptr
                                     : runtime.sessions_.begin()->second.get();
  }
};
}  // namespace gateway::gateway_api

namespace {
using namespace gateway;
using Access = gateway_api::StreamingSessionTestAccess;
using Clock = std::chrono::steady_clock;

std::size_t descriptorCount() {
  return std::distance(std::filesystem::directory_iterator("/proc/self/fd"),
                       std::filesystem::directory_iterator());
}

void printStorageDiagnostics() {
  std::ifstream statm("/proc/self/statm");
  std::uint64_t pages = 0, resident = 0;
  statm >> pages >> resident;
  std::cout << "diagnostic resident_pages=" << resident
            << " page_bytes=" << ::sysconf(_SC_PAGESIZE)
            << " StreamOutput_sizeof=" << sizeof(http::StreamOutput)
            << " array_capacity=" << http::StreamOutput::kCapacity
            << " ProxySession_sizeof=" << sizeof(gateway_api::ProxySession)
            << " CapacityLease_sizeof=" << sizeof(gateway_api::CapacityLease)
            << " BufferBudget_sizeof=" << sizeof(gateway_api::BufferBudget)
            << '\n';
}

std::string request(bool stream = true) {
  const auto body = std::string(
                        "{\"model\":\"m\",\"messages\":[{\"role\":\"user\","
                        "\"content\":\"x\"}],\"stream\":") +
                    (stream ? "true}" : "false}");
  return "POST /v1/chat/completions HTTP/1.1\r\nHost: h\r\nContent-Type: "
         "application/json\r\nContent-Length: " +
         std::to_string(body.size()) + "\r\n\r\n" + body;
}

net::Socket listener() {
  auto socket = net::Socket::createTcp();
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  GATEWAY_CHECK(::bind(socket.fd(), reinterpret_cast<sockaddr*>(&address),
                       sizeof(address)) == 0);
  socket.listen(8);
  return socket;
}

net::Socket client(std::uint16_t port) {
  net::Socket socket(::socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0));
  int buffer = 4096;
  GATEWAY_CHECK(::setsockopt(socket.fd(), SOL_SOCKET, SO_RCVBUF, &buffer,
                             sizeof(buffer)) == 0);
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  address.sin_port = htons(port);
  GATEWAY_CHECK(::connect(socket.fd(), reinterpret_cast<sockaddr*>(&address),
                          sizeof(address)) == 0);
  socket.setNonBlocking();
  return socket;
}

int socketBuffer(int fd, int option) {
  int value = 0;
  socklen_t size = sizeof(value);
  GATEWAY_CHECK(::getsockopt(fd, SOL_SOCKET, option, &value, &size) == 0);
  return value;
}

void sendAvailable(int fd, const std::string& wire, std::size_t& offset) {
  if (offset == wire.size()) return;
  const auto count =
      ::send(fd, wire.data() + offset, wire.size() - offset, MSG_NOSIGNAL);
  if (count > 0)
    offset += static_cast<std::size_t>(count);
  else
    GATEWAY_CHECK(count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK));
}

bool readAvailable(int fd, std::string& output) {
  char bytes[8192];
  const auto count = ::recv(fd, bytes, sizeof(bytes), 0);
  if (count > 0)
    output.append(bytes, static_cast<std::size_t>(count));
  else if (count < 0)
    GATEWAY_CHECK(errno == EAGAIN || errno == EWOULDBLOCK);
  return count == 0;
}

std::string decodeChunks(const std::string& wire) {
  const auto headerEnd = wire.find("\r\n\r\n");
  GATEWAY_CHECK(headerEnd != std::string::npos);
  GATEWAY_CHECK(wire.starts_with("HTTP/1.1 200"));
  std::size_t offset = headerEnd + 4;
  std::string body;
  for (;;) {
    const auto lineEnd = wire.find("\r\n", offset);
    GATEWAY_CHECK(lineEnd != std::string::npos);
    const auto size =
        std::stoul(wire.substr(offset, lineEnd - offset), nullptr, 16);
    offset = lineEnd + 2;
    GATEWAY_CHECK(offset + size + 2 <= wire.size());
    body.append(wire, offset, size);
    offset += size;
    GATEWAY_CHECK(wire.substr(offset, 2) == "\r\n");
    offset += 2;
    if (!size) {
      GATEWAY_CHECK(offset == wire.size());
      return body;
    }
  }
}

void checkFastRequest(gateway_api::GatewayRuntime& runtime, int backendFd,
                      std::uint16_t port) {
  auto stalled = client(port);
  auto fast = client(port);
  const auto input = request(false);
  GATEWAY_CHECK(::send(fast.fd(), input.data(), input.size(), MSG_NOSIGNAL) ==
                static_cast<ssize_t>(input.size()));
  net::Socket upstream;
  std::string received;
  const auto deadline = Clock::now() + std::chrono::seconds(3);
  while (received.find("\r\n\r\n") == std::string::npos &&
         Clock::now() < deadline) {
    runtime.pollOnce(1);
    if (!upstream.valid())
      upstream.reset(
          ::accept4(backendFd, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC));
    if (upstream.valid()) readAvailable(upstream.fd(), received);
  }
  GATEWAY_CHECK(!received.empty());
  const std::string response =
      "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok";
  GATEWAY_CHECK(::send(upstream.fd(), response.data(), response.size(),
                       MSG_NOSIGNAL) == static_cast<ssize_t>(response.size()));
  received.clear();
  bool eof = false;
  while (!eof && Clock::now() < deadline) {
    runtime.pollOnce(1);
    eof = readAvailable(fast.fd(), received);
  }
  GATEWAY_CHECK(eof && received.ends_with("ok"));
  received.clear();
  eof = false;
  while (!eof && Clock::now() < deadline) {
    runtime.pollOnce(1);
    eof = readAvailable(stalled.fd(), received);
  }
  GATEWAY_CHECK(eof && received.starts_with("HTTP/1.1 408"));
}

void testSlowReader(int framing, bool resetUpstream = false, int stopMode = 0) {
  auto backend = listener();
  app::GatewayConfig config;
  config.listenPort = 0;
  config.upstreamAddress = "127.0.0.1";
  config.upstreamPort = backend.localPort();
  config.timeouts.request = 50;
  if (stopMode == 3) config.timeouts.shutdown = 20;
  config.streamBuffer.highWaterBytes = 32768;
  config.streamBuffer.lowWaterBytes = 8192;
  gateway_api::GatewayRuntime runtime(config);
  const auto port = runtime.startListener();
  auto downstream = client(port);
  const auto input = request();
  GATEWAY_CHECK(::send(downstream.fd(), input.data(), input.size(),
                       MSG_NOSIGNAL) == static_cast<ssize_t>(input.size()));
  net::Socket upstream;
  std::string receivedRequest;
  const auto deadline = Clock::now() + std::chrono::seconds(10);
  while (receivedRequest.find("\r\n\r\n") == std::string::npos &&
         Clock::now() < deadline) {
    runtime.pollOnce(1);
    if (!upstream.valid())
      upstream.reset(::accept4(backend.fd(), nullptr, nullptr,
                               SOCK_NONBLOCK | SOCK_CLOEXEC));
    if (upstream.valid()) readAvailable(upstream.fd(), receivedRequest);
  }
  auto* session = gateway_api::RuntimeTestAccess::first(runtime);
  GATEWAY_CHECK(session && upstream.valid());
  int backendBuffer = 524288;
  GATEWAY_CHECK(::setsockopt(upstream.fd(), SOL_SOCKET, SO_SNDBUF,
                             &backendBuffer, sizeof(backendBuffer)) == 0);
  std::cout << "backend_send=" << socketBuffer(upstream.fd(), SO_SNDBUF)
            << '\n';
  int buffer = 4096;
  GATEWAY_CHECK(::setsockopt(Access::clientFd(*session), SOL_SOCKET, SO_SNDBUF,
                             &buffer, sizeof(buffer)) == 0);
  std::cout << "socket framing=" << framing
            << " send=" << socketBuffer(Access::clientFd(*session), SO_SNDBUF)
            << " receive=" << socketBuffer(downstream.fd(), SO_RCVBUF) << '\n';
  std::string body = "data: hel";
  for (int index = 0; index < 262144; ++index)
    body += static_cast<char>('a' + index % 26);
  const auto headers =
      std::string("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n") +
      (framing == 0 ? "Content-Length: " + std::to_string(body.size()) + "\r\n"
       : framing == 1 ? "Transfer-Encoding: chunked\r\n"
                      : "") +
      "\r\n";
  std::string wire = headers;
  if (framing == 1) {
    char size[32];
    std::snprintf(size, sizeof(size), "%zx", body.size());
    wire += std::string(size) + "\r\n";
  }
  wire += body;
  if (framing == 1) wire += "\r\n0\r\n\r\n";
  std::size_t sent = 0;
  std::string response;
  std::uint64_t previousToken = Access::token(*session);
  bool upstreamClosed = false;
  for (int cycle = 0; cycle < (resetUpstream ? 1 : 2); ++cycle) {
    const auto beforePause = runtime.snapshot().budget.pauses;
    std::size_t triggerPending = 0;
    std::uint64_t triggerToken = 0;
    while (!Access::paused(*session) && Clock::now() < deadline) {
      sendAvailable(upstream.fd(), wire, sent);
      // 在真实上游处理返回、同轮下游写之前取证，不能用历史全局峰代替。
      Access::readUpstream(*session);
      if (Access::paused(*session)) {
        triggerPending = Access::pending(*session);
        triggerToken = Access::token(*session);
        runtime.pollOnce(1);
      }
    }
    printStorageDiagnostics();
    const auto calls = Access::reads(*session);
    const auto bytes = Access::bytes(*session);
    const auto observed = runtime.snapshot().budget;
    std::cout << "pause framing=" << framing << " reset=" << resetUpstream
              << " stopMode=" << stopMode << " cycle=" << cycle
              << " paused=" << Access::paused(*session)
              << " token=" << Access::token(*session)
              << " pending=" << Access::pending(*session)
              << " high=" << config.streamBuffer.highWaterBytes
              << " low=" << config.streamBuffer.lowWaterBytes
              << " triggerPending=" << triggerPending
              << " triggerToken=" << triggerToken
              << " pauses=" << observed.pauses
              << " resumes=" << observed.resumes << " reads=" << calls
              << " bytes=" << bytes << std::endl;
    GATEWAY_CHECK(triggerPending >= config.streamBuffer.highWaterBytes);
    GATEWAY_CHECK(triggerToken == 0);
    GATEWAY_CHECK(observed.pauses == beforePause + 1);
    GATEWAY_CHECK(Access::paused(*session));
    GATEWAY_CHECK(Access::token(*session) == 0);
    // 下游可能已在同一poll消费部分数据；迟滞只要求尚未降至low。
    GATEWAY_CHECK(Access::pending(*session) >
                  config.streamBuffer.lowWaterBytes);
    GATEWAY_CHECK(Access::pending(*session) <= http::StreamOutput::kCapacity);
    gateway_api::RuntimeTestAccess::staleEvent(runtime, previousToken);
    if (resetUpstream) {
      linger reset{1, 0};
      GATEWAY_CHECK(::setsockopt(upstream.fd(), SOL_SOCKET, SO_LINGER, &reset,
                                 sizeof(reset)) == 0);
      upstream.reset();
    } else if (!cycle && framing == 2) {
      GATEWAY_CHECK(sent == wire.size());
      GATEWAY_CHECK(::shutdown(upstream.fd(), SHUT_WR) == 0);
      upstreamClosed = true;
    }
    for (int step = 0; step < 8; ++step) runtime.pollOnce(1);
    GATEWAY_CHECK(Access::reads(*session) == calls &&
                  Access::bytes(*session) == bytes);
    if (!cycle) {
      checkFastRequest(runtime, backend.fd(), port);
      GATEWAY_CHECK(Access::paused(*session) &&
                    Access::reads(*session) == calls);
    }
    if (!cycle && stopMode) {
      GATEWAY_CHECK(::raise(SIGTERM) == 0);
      runtime.pollOnce(0);
      if (stopMode == 2) {
        GATEWAY_CHECK(::raise(SIGINT) == 0);
        runtime.pollOnce(0);
      }
      if (stopMode >= 2) {
        while (runtime.snapshot().activeSessions && Clock::now() < deadline)
          runtime.pollOnce(1);
        const auto stopped = runtime.snapshot();
        GATEWAY_CHECK(
            stopped.activeSessions == 0 && stopped.budget.reserved == 0 &&
            stopped.budget.streamCapacity == 0 && stopped.budget.pending == 0 &&
            stopped.budget.paused == 0 && stopped.pool.total == 0 &&
            stopped.activeTimers == 0);
        std::cout << "paused stopMode=" << stopMode << " all_resources_zero\n";
        return;
      }
    }
    while (Access::paused(*session) && Clock::now() < deadline) {
      readAvailable(downstream.fd(), response);
      runtime.pollOnce(1);
    }
    GATEWAY_CHECK(!Access::paused(*session));
    const auto token = Access::token(*session);
    GATEWAY_CHECK(token && token != previousToken);
    const auto resumedReads = Access::reads(*session);
    gateway_api::RuntimeTestAccess::staleEvent(runtime, previousToken);
    GATEWAY_CHECK(Access::reads(*session) == resumedReads);
    previousToken = token;
    std::cout << "cycle framing=" << framing << " cycle=" << cycle
              << " stopped_reads=" << calls << " bytes=" << bytes
              << " resume_token=" << token
              << " pending=" << Access::pending(*session) << '\n';
  }
  bool eof = false;
  while (!eof && Clock::now() < deadline) {
    if (upstream.valid()) sendAvailable(upstream.fd(), wire, sent);
    if (!resetUpstream && sent == wire.size() && framing == 2 &&
        !upstreamClosed) {
      GATEWAY_CHECK(::shutdown(upstream.fd(), SHUT_WR) == 0);
      upstreamClosed = true;
    }
    runtime.pollOnce(1);
    eof = readAvailable(downstream.fd(), response);
  }
  GATEWAY_CHECK(eof);
  if (resetUpstream)
    GATEWAY_CHECK(!response.ends_with("0\r\n\r\n"));
  else
    GATEWAY_CHECK(decodeChunks(response) == body);
  downstream.reset();
  for (int step = 0; step < 30 && runtime.snapshot().activeSessions; ++step)
    runtime.pollOnce(1);
  const auto snapshot = runtime.snapshot();
  GATEWAY_CHECK(snapshot.activeSessions == 0 && snapshot.budget.reserved == 0 &&
                snapshot.budget.streamCapacity == 0 &&
                snapshot.budget.pending == 0 && snapshot.budget.paused == 0 &&
                snapshot.pool.total == 0 && snapshot.activeTimers == 0);
  GATEWAY_CHECK(snapshot.budget.pauses >= (resetUpstream ? 1u : 2u) &&
                snapshot.budget.resumes >= (resetUpstream ? 1u : 2u) &&
                snapshot.budget.peakStreamCapacity == 262144);
  if (!stopMode) {
    GATEWAY_CHECK(::raise(SIGTERM) == 0);
    runtime.pollOnce(0);
  }
}
}  // namespace

int main() {
  try {
    const auto descriptors = descriptorCount();
    for (int framing : {0, 1, 2}) testSlowReader(framing);
    for (int framing : {0, 1, 2}) testSlowReader(framing, true);
    for (int stopMode : {1, 2, 3}) testSlowReader(1, false, stopMode);
    GATEWAY_CHECK(descriptorCount() == descriptors);
    std::cout << "Backpressure checks " << gateway::test::checks << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
