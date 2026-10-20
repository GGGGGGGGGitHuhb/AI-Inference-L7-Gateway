#include <sys/socket.h>

#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <limits>
#include <new>

#include "TestSupport.h"
#include "gateway/GatewayRuntime.h"

namespace {
bool failAllocation = false;
}

void* operator new(std::size_t size) {
  if (failAllocation) throw std::bad_alloc();
  if (void* memory = std::malloc(size ? size : 1)) return memory;
  throw std::bad_alloc();
}

void operator delete(void* memory) noexcept { std::free(memory); }

void operator delete(void* memory, std::size_t) noexcept { std::free(memory); }

namespace gateway::gateway_api {
struct AdmissionSessionTestAccess {
  static void read(ProxySession& session) {
    session.onDownstreamEvent(EPOLLIN);
  }

  static bool dispatch(ProxySession& session) {
    return session.dispatchWaiting();
  }

  static bool waiting(const ProxySession& session) { return session.queued_; }

  static bool leases(const ProxySession& session) {
    return session.requestLease_.active() || session.upstreamLease_.valid() ||
           session.streamCapacity_.valid();
  }

  static std::string error(const ProxySession& session) {
    return session.outcomeCode_;
  }

  static auto deadline(const ProxySession& session) {
    return session.nextDeadline();
  }

  static void expire(ProxySession& session) { session.checkDeadline(); }
};
}  // namespace gateway::gateway_api

namespace {
using namespace gateway;
using gateway_api::AdmissionSessionTestAccess;
using Milliseconds = std::chrono::milliseconds;

app::GatewayConfig configuration() {
  app::GatewayConfig config;
  config.models = {{"a",
                    app::RoutingPolicy::kRoundRobin,
                    {{"one", "127.0.0.1", 9001}, {"two", "127.0.0.1", 9002}}},
                   {"b",
                    app::RoutingPolicy::kRoundRobin,
                    {{"one", "127.0.0.1", 9003}, {"two", "127.0.0.1", 9004}}}};
  config.admission.enabled = true;
  config.admission.maxInflight = 2;
  config.admission.maxInflightPerBackend = 1;
  config.health = {1, 10};
  return config;
}

void configChecks() {
  const std::string prefix =
      R"({"listen_address":"127.0.0.1","listen_port":8080,"models":[{"name":"a","policy":"round_robin","backends":[{"id":"one","address":"127.0.0.1","port":9001}]}])";
  const auto parse = [&](const std::string& admission) {
    return app::parseConfig(prefix + ",\"admission\":" + admission + "}");
  };
  for (const auto* key : {"max_inflight", "max_inflight_per_backend",
                          "max_queue_requests_per_model",
                          "max_queue_bytes_per_model", "queue_timeout_ms"}) {
    for (const auto* value : {"true", "1.5", "-1", "18446744073709551616"}) {
      bool rejected = false;
      try {
        parse(std::string("{\"") + key + "\":" + value + "}");
      } catch (...) {
        rejected = true;
      }
      GATEWAY_CHECK(rejected);
    }
  }
  const auto defaults = parse("{}");
  GATEWAY_CHECK(defaults.admission.enabled);
  GATEWAY_CHECK(defaults.admission.maxInflight == 16);
  GATEWAY_CHECK(defaults.admission.maxInflightPerBackend == 4);
  GATEWAY_CHECK(defaults.admission.maxQueueRequestsPerModel == 16);
  GATEWAY_CHECK(defaults.admission.maxQueueBytesPerModel == 4194304);
  GATEWAY_CHECK(defaults.admission.queueTimeoutMs == 1000);
  GATEWAY_CHECK(!app::parseConfig(prefix + "}").admission.enabled);
  for (const auto& value :
       {"true", "1.5", "-1", "0", "257", "18446744073709551616"}) {
    bool rejected = false;
    try {
      parse(std::string("{\"max_inflight\":") + value + "}");
    } catch (...) {
      rejected = true;
    }
    GATEWAY_CHECK(rejected);
  }
  for (const auto& value :
       {"{\"x\":1}", "{\"max_inflight\":4,\"max_inflight\":4}",
        "{\"queue_timeout_ms\":9}", "{\"queue_timeout_ms\":300001}",
        "{\"max_queue_requests_per_model\":257}",
        "{\"max_queue_bytes_per_model\":268435457}",
        "{\"max_inflight_per_backend\":17}", "[]"}) {
    bool rejected = false;
    try {
      parse(value);
    } catch (...) {
      rejected = true;
    }
    GATEWAY_CHECK(rejected);
  }
  GATEWAY_CHECK(
      parse(
          R"({"max_inflight":256,"max_inflight_per_backend":256,"max_queue_requests_per_model":256,"max_queue_bytes_per_model":268435456,"queue_timeout_ms":300000})")
          .admission.maxInflight == 256);
  GATEWAY_CHECK(
      parse(
          R"({"max_inflight":1,"max_inflight_per_backend":1,"max_queue_requests_per_model":0,"max_queue_bytes_per_model":0,"queue_timeout_ms":10})")
          .admission.maxQueueBytesPerModel == 0);
  bool rejected = false;
  try {
    app::parseConfig(
        R"({"upstream_address":"127.0.0.1","upstream_port":9000,"admission":{}})");
  } catch (...) {
    rejected = true;
  }
  GATEWAY_CHECK(rejected);
  auto config = configuration();
  config.admission.maxInflight = 0;
  rejected = false;
  try {
    gateway_api::GatewayRuntime runtime(config);
  } catch (...) {
    rejected = true;
  }
  GATEWAY_CHECK(rejected);
}

void queueChecks() {
  auto config = configuration();
  config.admission.maxQueueRequestsPerModel = 2;
  config.admission.maxQueueBytesPerModel = 200;
  admission::AdmissionController queue(config);
  using admission::EnqueueStatus;
  GATEWAY_CHECK(queue.enqueueRequest(0, 1, 100) == EnqueueStatus::kQueued);
  GATEWAY_CHECK(queue.enqueueRequest(0, 2, 100) == EnqueueStatus::kQueued);
  GATEWAY_CHECK(queue.snapshot(0).bytes == 200);
  GATEWAY_CHECK(queue.enqueueRequest(0, 3, 1) == EnqueueStatus::kCountLimit);
  GATEWAY_CHECK(queue.removeRequest(1));
  GATEWAY_CHECK(queue.head(0) == 2);
  GATEWAY_CHECK(queue.enqueueRequest(0, 3, 101) == EnqueueStatus::kByteLimit);
  GATEWAY_CHECK(queue.enqueueRequest(0, 3, 100) == EnqueueStatus::kQueued);
  GATEWAY_CHECK(queue.removeRequest(3));
  GATEWAY_CHECK(queue.head(0) == 2);
  GATEWAY_CHECK(!queue.removeRequest(3));
  GATEWAY_CHECK(queue.removeRequest(2));
  GATEWAY_CHECK(queue.total().bytes == 0 && queue.empty());
  GATEWAY_CHECK(queue.enqueueRequest(1, 4, 201) == EnqueueStatus::kByteLimit);
  queue.stopAdmission();
  GATEWAY_CHECK(queue.enqueueRequest(0, 5, 1) == EnqueueStatus::kStopping);
  config.admission.maxQueueRequestsPerModel = 0;
  admission::AdmissionController disabledCount(config);
  GATEWAY_CHECK(disabledCount.enqueueRequest(0, 1, 0) ==
                EnqueueStatus::kCountLimit);
  config.admission.maxQueueRequestsPerModel = 2;
  config.admission.maxQueueBytesPerModel = 0;
  admission::AdmissionController disabledBytes(config);
  GATEWAY_CHECK(disabledBytes.enqueueRequest(0, 1, 0) ==
                EnqueueStatus::kByteLimit);
  http::HttpMessage message;
  message.method = "POST";
  message.target = "/x";
  message.body = "abc";
  message.headers.push_back({"Host", "test"});
  GATEWAY_CHECK(admission::AdmissionController::requestCharge(message) == 1045);
}

void middleCancellationChecks() {
  auto config = configuration();
  admission::AdmissionController queue(config);
  for (std::uint64_t id = 1; id <= 3; ++id)
    GATEWAY_CHECK(queue.enqueueRequest(0, id, 100) ==
                  admission::EnqueueStatus::kQueued);
  GATEWAY_CHECK(queue.removeRequest(2));
  GATEWAY_CHECK(queue.head(0) == 1 && queue.total().bytes == 200);
  GATEWAY_CHECK(queue.removeRequest(1));
  GATEWAY_CHECK(queue.head(0) == 3 && queue.total().bytes == 100);
  GATEWAY_CHECK(queue.removeRequest(3));
  GATEWAY_CHECK(queue.empty() && queue.total().bytes == 0);
}

void allocationChecks() {
  auto config = configuration();
  config.maxConnections = 256;
  config.admission.maxQueueRequestsPerModel = 256;
  admission::AdmissionController queue(config);
  bool failed = false;
  for (std::uint64_t id = 1; id <= 256 && !failed; ++id) {
    const auto before = queue.total();
    failAllocation = true;
    try {
      queue.enqueueRequest(0, id, 1);
    } catch (const std::bad_alloc&) {
      failed = true;
    }
    failAllocation = false;
    if (failed) {
      GATEWAY_CHECK(queue.total().count == before.count);
      GATEWAY_CHECK(queue.total().bytes == before.bytes);
      GATEWAY_CHECK(queue.snapshot(0).count == before.count);
    }
  }
  GATEWAY_CHECK(failed);
}

void limitChecks() {
  auto config = configuration();
  routing::ModelRouter router(config);
  const auto now = routing::Clock::now();
  auto first = router.selectBackend("a", now, 2, 1);
  auto second = router.selectBackend("b", now, 2, 1);
  GATEWAY_CHECK(first.lease.index() == 0 && second.lease.index() == 2);
  GATEWAY_CHECK(router.activeRequests() == 2);
  for (int attempt = 0; attempt < 10; ++attempt)
    GATEWAY_CHECK(router.selectBackend("a", now, 2, 1).status ==
                  routing::SelectionStatus::kCapacity);
  first.lease.complete(routing::Observation::kSuccess, now);
  auto next = router.selectBackend("a", now, 2, 1);
  GATEWAY_CHECK(next.lease.index() == 1);
  for (std::size_t index = 0; index < router.size(); ++index)
    GATEWAY_CHECK(router.snapshot(index).inflight <= 1);
  next.lease.complete(routing::Observation::kFailure, now);
  auto available = router.selectBackend("a", now, 2, 1);
  GATEWAY_CHECK(available.lease.index() == 0);
  available.lease.complete(routing::Observation::kFailure, now);
  GATEWAY_CHECK(router.inspectModel("a", now, 1, 1) ==
                routing::SelectionStatus::kUnavailable);
  GATEWAY_CHECK(
      router.selectBackend("a", now + Milliseconds(10), 1, 1).status ==
      routing::SelectionStatus::kCapacity);
  GATEWAY_CHECK(router.snapshot(0).state == routing::HealthState::kEjected);
  second.lease.complete(routing::Observation::kSuccess, now);
  auto trial = router.selectBackend("a", now + Milliseconds(10), 1, 1);
  GATEWAY_CHECK(trial.status == routing::SelectionStatus::kSelected);
  trial.lease.complete(routing::Observation::kNeutral, now + Milliseconds(10));
  GATEWAY_CHECK(router.activeRequests() == 0);
}

struct FakeIo final : public gateway_api::SessionIo {
 public:
  Clock::time_point now() const override { return time; }

  int connectSocket(int, const sockaddr*, socklen_t) override {
    ++connections;
    errno = EINPROGRESS;
    return -1;
  }

  ssize_t receiveBytes(int, void* data, std::size_t size) override;

  ssize_t sendBytes(int, const void*, std::size_t) override {
    errno = EAGAIN;
    return -1;
  }

  Clock::time_point time = Clock::now();
  std::string input;
  int connections = 0;
  bool eof = false;
  bool reset = false;
};

ssize_t FakeIo::receiveBytes(int, void* data, std::size_t size) {
  if (reset) {
    errno = ECONNRESET;
    return -1;
  }
  if (!input.empty()) {
    const auto count = std::min(input.size(), size);
    std::memcpy(data, input.data(), count);
    input.erase(0, count);
    return count;
  }
  if (eof) return 0;
  errno = EAGAIN;
  return -1;
}

struct Fixture {
 public:
  explicit Fixture(int total = 10000, int queueTimeout = 1000,
                   app::RoutingPolicy policy = app::RoutingPolicy::kRoundRobin);
  ~Fixture();
  void begin();

  app::GatewayConfig config = configuration();
  gateway_api::BufferBudget budget{268435456, 4194304};
  net::EventLoop loop;
  FakeIo io;
  std::unique_ptr<routing::ModelRouter> router;
  std::unique_ptr<admission::AdmissionController> queue;
  std::vector<std::unique_ptr<upstream::ConnectionPool>> pools;
  routing::RequestLease blocker;
  net::Socket peer;
  std::unique_ptr<gateway_api::ProxySession> session;
};

Fixture::Fixture(int total, int queueTimeout, app::RoutingPolicy policy) {
  config.models[0].policy = policy;
  config.admission.maxInflight = 1;
  config.admission.queueTimeoutMs = queueTimeout;
  config.timeouts.total = total;
  router = std::make_unique<routing::ModelRouter>(config);
  queue = std::make_unique<admission::AdmissionController>(config);
  for (std::size_t index = 0; index < router->size(); ++index)
    pools.push_back(std::make_unique<upstream::ConnectionPool>(
        loop, config.upstreamPool, io));
  blocker = std::move(router->selectBackend("b", io.now(), 1, 1).lease);
  int pair[2];
  GATEWAY_CHECK(socketpair(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC,
                           0, pair) == 0);
  peer.reset(pair[1]);
  session = std::make_unique<gateway_api::ProxySession>(
      loop, config, io, *pools[0], net::Socket(pair[0]), io.now(), budget,
      budget.acquireCapacity(gateway_api::CapacityKind::kSession), router.get(),
      &pools, queue.get(), 1);
  session->startSession();
}

Fixture::~Fixture() {
  session->finishSession();
  session.reset();
}

void Fixture::begin() {
  const std::string body =
      R"({"model":"a","messages":[{"role":"user","content":"x"}]})";
  io.input =
      "POST /v1/chat/completions HTTP/1.1\r\nHost: test\r\nContent-Type: "
      "application/json\r\nContent-Length: " +
      std::to_string(body.size()) + "\r\n\r\n" + body;
  AdmissionSessionTestAccess::read(*session);
}

void lifecycleChecks() {
  {
    Fixture fixture(10000, 1000, app::RoutingPolicy::kLeastInflight);
    fixture.begin();
    auto loaded = fixture.router->selectBackend("a", fixture.io.now());
    auto temporary = fixture.router->selectBackend("a", fixture.io.now());
    temporary.lease.complete(routing::Observation::kSuccess, fixture.io.now());
    fixture.config.admission.maxInflight = 4;
    fixture.config.admission.maxInflightPerBackend = 3;
    GATEWAY_CHECK(AdmissionSessionTestAccess::dispatch(*fixture.session));
    GATEWAY_CHECK(fixture.router->snapshot(1).inflight == 1);
    GATEWAY_CHECK(fixture.router->snapshot(0).inflight == 1);
  }
  {
    Fixture fixture;
    fixture.begin();
    auto first = fixture.router->selectBackend("a", fixture.io.now());
    auto second = fixture.router->selectBackend("a", fixture.io.now());
    first.lease.complete(routing::Observation::kFailure, fixture.io.now());
    second.lease.complete(routing::Observation::kFailure, fixture.io.now());
    fixture.io.time += Milliseconds(10);
    fixture.blocker.complete(routing::Observation::kSuccess, fixture.io.now());
    GATEWAY_CHECK(AdmissionSessionTestAccess::dispatch(*fixture.session));
    GATEWAY_CHECK(fixture.router->snapshot(0).state ==
                  routing::HealthState::kTrial);
    fixture.session->finishSession(gateway_api::FinishReason::kCancelled);
    GATEWAY_CHECK(fixture.router->snapshot(0).state ==
                  routing::HealthState::kEjected);
    GATEWAY_CHECK(fixture.router->activeRequests() == 0 &&
                  fixture.queue->empty());
  }

  {
    Fixture fixture(1000, 1000);
    const auto accepted = fixture.io.now();
    fixture.io.time += Milliseconds(500);
    fixture.begin();
    GATEWAY_CHECK(AdmissionSessionTestAccess::deadline(*fixture.session) ==
                  accepted + Milliseconds(1000));
  }
  {
    Fixture fixture;
    fixture.begin();
    auto failed = fixture.router->selectBackend("a", fixture.io.now());
    failed.lease.complete(routing::Observation::kFailure, fixture.io.now());
    fixture.blocker.complete(routing::Observation::kSuccess, fixture.io.now());
    GATEWAY_CHECK(AdmissionSessionTestAccess::dispatch(*fixture.session));
    GATEWAY_CHECK(fixture.router->snapshot(1).inflight == 1);
    GATEWAY_CHECK(fixture.router->snapshot(0).inflight == 0);
  }
  {
    Fixture fixture;
    std::vector<upstream::ConnectionLease> held;
    for (std::size_t index = 0;
         index < fixture.config.upstreamPool.maxConnections; ++index)
      held.push_back(fixture.pools[0]->acquireConnection([](std::uint32_t) {}));
    fixture.begin();
    fixture.blocker.complete(routing::Observation::kSuccess, fixture.io.now());
    GATEWAY_CHECK(AdmissionSessionTestAccess::dispatch(*fixture.session));
    GATEWAY_CHECK(AdmissionSessionTestAccess::error(*fixture.session) ==
                  "upstream_capacity");
    GATEWAY_CHECK(fixture.queue->empty() &&
                  fixture.router->activeRequests() == 0);
    GATEWAY_CHECK(fixture.router->snapshot(0).failureCount == 0);
    GATEWAY_CHECK(fixture.io.connections == 0);
  }

  {
    Fixture fixture;
    fixture.begin();
    GATEWAY_CHECK(AdmissionSessionTestAccess::waiting(*fixture.session));
    GATEWAY_CHECK(!AdmissionSessionTestAccess::leases(*fixture.session));
    GATEWAY_CHECK(fixture.budget.snapshot().reserved == 16777216);
    GATEWAY_CHECK(fixture.budget.snapshot().streamCapacity == 0);
    fixture.io.eof = true;
    AdmissionSessionTestAccess::read(*fixture.session);
    GATEWAY_CHECK(AdmissionSessionTestAccess::waiting(*fixture.session));
    GATEWAY_CHECK(!AdmissionSessionTestAccess::dispatch(*fixture.session));
    fixture.blocker.complete(routing::Observation::kSuccess, fixture.io.now());
    GATEWAY_CHECK(AdmissionSessionTestAccess::dispatch(*fixture.session));
    GATEWAY_CHECK(fixture.queue->empty() && fixture.queue->total().bytes == 0);
    GATEWAY_CHECK(fixture.io.connections == 1);
    fixture.session->finishSession();
    fixture.session->finishSession();
    GATEWAY_CHECK(fixture.router->activeRequests() == 0);
    GATEWAY_CHECK(fixture.loop.timerCount() == 0);
  }
  for (bool reset : {true, false}) {
    Fixture fixture;
    fixture.begin();
    if (reset) {
      fixture.io.reset = true;
      AdmissionSessionTestAccess::read(*fixture.session);
    } else
      fixture.session->finishSession(gateway_api::FinishReason::kStopped);
    GATEWAY_CHECK(fixture.queue->empty() && fixture.queue->total().bytes == 0);
    GATEWAY_CHECK(fixture.io.connections == 0);
  }
  for (const int total : {500, 1000, 2000}) {
    Fixture fixture(total, 1000);
    fixture.begin();
    const auto deadline =
        AdmissionSessionTestAccess::deadline(*fixture.session);
    fixture.io.time = deadline - Milliseconds(1);
    GATEWAY_CHECK(!AdmissionSessionTestAccess::dispatch(*fixture.session));
    fixture.io.time = deadline;
    fixture.blocker.complete(routing::Observation::kSuccess, fixture.io.now());
    GATEWAY_CHECK(AdmissionSessionTestAccess::dispatch(*fixture.session));
    GATEWAY_CHECK(fixture.io.connections == 0);
    GATEWAY_CHECK(fixture.queue->empty());
    GATEWAY_CHECK(AdmissionSessionTestAccess::error(*fixture.session) ==
                  (total <= 1000 ? "total_timeout" : "queue_timeout"));
  }
  {
    Fixture fixture;
    fixture.io.time += Milliseconds(500);
    fixture.begin();
    GATEWAY_CHECK(AdmissionSessionTestAccess::deadline(*fixture.session) ==
                  fixture.io.now() + Milliseconds(1000));
    auto first = fixture.router->selectBackend("a", fixture.io.now());
    auto second = fixture.router->selectBackend("a", fixture.io.now());
    first.lease.complete(routing::Observation::kFailure, fixture.io.now());
    second.lease.complete(routing::Observation::kFailure, fixture.io.now());
    GATEWAY_CHECK(AdmissionSessionTestAccess::dispatch(*fixture.session));
    GATEWAY_CHECK(AdmissionSessionTestAccess::error(*fixture.session) ==
                  "no_available_backend");
    GATEWAY_CHECK(fixture.queue->empty());
    GATEWAY_CHECK(fixture.io.connections == 0);
  }
}
}  // namespace

namespace gateway::gateway_api {
struct RuntimeTestAccess {
  static void add(GatewayRuntime& runtime, FakeIo& io, std::uint64_t id,
                  std::vector<net::Socket>& peers,
                  const std::string& model = "a");

  static void budgetChecks(bool stopPending);

  static void fairnessChecks();
};

void RuntimeTestAccess::add(GatewayRuntime& runtime, FakeIo& io,
                            std::uint64_t id, std::vector<net::Socket>& peers,
                            const std::string& model) {
  int pair[2];
  GATEWAY_CHECK(socketpair(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC,
                           0, pair) == 0);
  peers.emplace_back(pair[1]);
  auto session = std::make_unique<ProxySession>(
      runtime.loop_, runtime.config_, io, runtime.pool_, net::Socket(pair[0]),
      io.now(), runtime.budget_,
      runtime.budget_.acquireCapacity(CapacityKind::kSession), &runtime.router_,
      &runtime.pools_, runtime.admission_.get(), id);
  const std::string body =
      "{\"model\":\"" + model +
      "\",\"messages\":[{\"role\":\"user\",\"content\":\"x\"}]}";
  io.input =
      "POST /v1/chat/completions HTTP/1.1\r\nHost: test\r\nContent-Type: "
      "application/json\r\nContent-Length: " +
      std::to_string(body.size()) + "\r\n\r\n" + body;
  session->startSession();
  AdmissionSessionTestAccess::read(*session);
  runtime.sessions_.emplace(id, std::move(session));
}

void RuntimeTestAccess::budgetChecks(bool stopPending) {
  auto config = configuration();
  // 此用例只测预算续轮；冷却长于120秒测试护栏，排除真实/冻结时钟差异。
  config.health.cooldownMs = 300000;
  config.maxConnections = 64;
  config.maxReservedBytes = 1073741824;
  config.admission.maxQueueRequestsPerModel = 64;
  config.admission.maxInflight = 1;
  std::vector<FakeIo> clients(40);
  std::vector<net::Socket> peers;
  GatewayRuntime runtime(config);
  auto blocker = runtime.router_.selectBackend("b", clients[0].now(), 1, 1);
  for (std::size_t index = 0; index < clients.size(); ++index)
    add(runtime, clients[index], index + 1, peers);
  GATEWAY_CHECK(runtime.admission_->total().count == 40);
  runtime.onCleanup();
  GATEWAY_CHECK(runtime.admission_->total().count == 40);
  GATEWAY_CHECK(!runtime.admissionTaskPending_);
  auto a1 = runtime.router_.selectBackend("a", clients[0].now());
  auto a2 = runtime.router_.selectBackend("a", clients[0].now());
  a1.lease.complete(routing::Observation::kFailure, clients[0].now());
  a2.lease.complete(routing::Observation::kFailure, clients[0].now());
  runtime.admission_->markDirty();
  runtime.onCleanup();
  GATEWAY_CHECK(runtime.admission_->total().count == 8);
  GATEWAY_CHECK(runtime.admissionTaskPending_);
  if (stopPending) runtime.requestShutdown();
  runtime.pollOnce(0);
  GATEWAY_CHECK(runtime.admission_->total().count == 0);
  GATEWAY_CHECK(runtime.admission_->total().bytes == 0);
  GATEWAY_CHECK(!runtime.admissionTaskPending_);
  for (const auto& io : clients) GATEWAY_CHECK(io.connections == 0);
  blocker.lease.complete(routing::Observation::kNeutral, clients[0].now());
  runtime.forceShutdown();
  runtime.onCleanup();
  GATEWAY_CHECK(runtime.sessions_.empty());
  GATEWAY_CHECK(runtime.router_.activeRequests() == 0);
  GATEWAY_CHECK(runtime.budget_.snapshot().reserved == 0);
  GATEWAY_CHECK(runtime.loop_.timerCount() == 0);
}

void RuntimeTestAccess::fairnessChecks() {
  auto config = configuration();
  config.admission.maxInflight = 3;
  std::vector<FakeIo> clients(3);
  std::vector<net::Socket> peers;
  GatewayRuntime runtime(config);
  auto first = runtime.router_.selectBackend("a", clients[0].now());
  auto second = runtime.router_.selectBackend("a", clients[0].now());
  add(runtime, clients[0], 1, peers);
  add(runtime, clients[1], 2, peers);
  add(runtime, clients[2], 3, peers, "b");
  GATEWAY_CHECK(runtime.admission_->total().count == 3);
  runtime.onCleanup();
  GATEWAY_CHECK(runtime.admission_->total().count == 2);
  GATEWAY_CHECK(clients[2].connections == 1);
  GATEWAY_CHECK(clients[0].connections == 0 && clients[1].connections == 0);
  runtime.sessions_.at(1)->finishSession(FinishReason::kCancelled);
  GATEWAY_CHECK(runtime.admission_->head(0) == 2);
  first.lease.complete(routing::Observation::kSuccess, clients[0].now());
  runtime.onCleanup();
  GATEWAY_CHECK(clients[1].connections == 1);
  GATEWAY_CHECK(runtime.admission_->empty());
  GATEWAY_CHECK(runtime.router_.activeRequests() == 3);
  second.lease.complete(routing::Observation::kNeutral, clients[0].now());
  runtime.forceShutdown();
  runtime.onCleanup();
  GATEWAY_CHECK(runtime.router_.activeRequests() == 0);
}
}  // namespace gateway::gateway_api

std::size_t openDescriptors() {
  return std::distance(std::filesystem::directory_iterator("/proc/self/fd"),
                       std::filesystem::directory_iterator{});
}

int main() {
  try {
    const auto descriptorsBefore = openDescriptors();
    configChecks();
    queueChecks();
    middleCancellationChecks();
    allocationChecks();
    limitChecks();
    lifecycleChecks();
    gateway_api::RuntimeTestAccess::budgetChecks(false);
    gateway_api::RuntimeTestAccess::budgetChecks(true);
    gateway_api::RuntimeTestAccess::fairnessChecks();
    GATEWAY_CHECK(openDescriptors() == descriptorsBefore);
    std::cout << "Admission checks: " << gateway::test::checks << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
