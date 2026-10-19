#include <cerrno>
#include <limits>
#include <type_traits>

#include "TestSupport.h"
#include "upstream/ConnectionPool.h"

namespace gateway::net {
struct EventLoopTestAccess {
  static void dispatch(EventLoop& loop, std::uint64_t token,
                       std::uint32_t events) {
    loop.dispatchChannelEvent(token, events);
  }
};
}  // namespace gateway::net

namespace gateway::upstream {
struct ConnectionPoolTestAccess {
  static std::uint64_t token(ConnectionPool& pool, std::uint64_t id) {
    return pool.connections_.at(id)->channel.token();
  }

  static void expiry(ConnectionPool& pool, std::uint64_t id,
                     std::uint64_t generation) {
    pool.onIdleDeadline(id, generation);
  }

  static void exhaustGeneration(ConnectionPool& pool, std::uint64_t id) {
    pool.connections_.at(id)->generation =
        std::numeric_limits<std::uint64_t>::max();
  }
};
}  // namespace gateway::upstream

namespace {
using namespace gateway;
using upstream::ConnectionPoolTestAccess;
class ProbeIo : public gateway_api::SessionIo {
 public:
  Clock::time_point now() const override { return time; }

  int socketError(int) override { return socketFailure; }

  ssize_t peekByte(int) override {
    ++peeks;
    if (interrupts-- > 0) {
      errno = EINTR;
      return -1;
    }
    errno = peekError;
    return peekResult;
  }

  Clock::time_point time = Clock::now();
  ssize_t peekResult = -1;
  int peekError = EAGAIN;
  int interrupts = 0;
  int peeks = 0;
  int socketFailure = 0;
};

class PoolFixture {
 public:
  PoolFixture() : pool(loop, app::PoolConfig{2, 1, 10}, io) {
    loop.registerCleanupCallback([this] { onCleanup(); });
  }

  void onCleanup() { pool.cleanupRetired(); }

  void onLeaseEvent(std::uint32_t) {
    ++events;
    lease.invalidate();
    GATEWAY_CHECK(pool.snapshot().retired == 1);
  }

  upstream::ConnectionLease acquire() {
    return pool.acquireConnection(
        [this](std::uint32_t events) { onLeaseEvent(events); });
  }

  net::EventLoop loop;
  ProbeIo io;
  upstream::ConnectionPool pool;
  upstream::ConnectionLease lease;
  int events = 0;
};

void testOwnershipAndTokens() {
  static_assert(!std::is_copy_constructible_v<upstream::ConnectionLease>);
  PoolFixture fixture;
  fixture.lease = fixture.acquire();
  const auto id = fixture.lease.id();
  const auto generation = fixture.lease.generation();
  fixture.lease.markConnected();
  fixture.lease.setInterest(EPOLLOUT);
  const auto leasedToken = ConnectionPoolTestAccess::token(fixture.pool, id);
  fixture.lease.releaseReusable();
  GATEWAY_CHECK(!fixture.lease.valid());
  const auto idleToken = ConnectionPoolTestAccess::token(fixture.pool, id);
  GATEWAY_CHECK(leasedToken != idleToken && fixture.loop.timerCount() == 1);
  fixture.lease = fixture.acquire();
  fixture.lease.setInterest(EPOLLIN);
  GATEWAY_CHECK(fixture.lease.reused() &&
                fixture.lease.generation() > generation);
  GATEWAY_CHECK(fixture.loop.timerCount() == 0);
  net::EventLoopTestAccess::dispatch(fixture.loop, leasedToken, EPOLLIN);
  net::EventLoopTestAccess::dispatch(fixture.loop, idleToken, EPOLLIN);
  ConnectionPoolTestAccess::expiry(fixture.pool, id, generation);
  GATEWAY_CHECK(fixture.events == 0 && fixture.lease.valid());
  auto moved = std::move(fixture.lease);
  GATEWAY_CHECK(!fixture.lease.valid() && moved.valid());
  fixture.lease = std::move(moved);
  const auto current = ConnectionPoolTestAccess::token(fixture.pool, id);
  net::EventLoopTestAccess::dispatch(fixture.loop, current, EPOLLIN);
  GATEWAY_CHECK(fixture.events == 1 && fixture.pool.snapshot().total == 0);
  GATEWAY_CHECK(fixture.pool.snapshot().retired == 0);
  fixture.lease.invalidate();
  fixture.lease.releaseReusable();
  GATEWAY_CHECK(fixture.pool.snapshot().discarded == 1);
  // 新FD即使复用了数字，也不能接收旧token。
  fixture.lease = fixture.acquire();
  net::EventLoopTestAccess::dispatch(fixture.loop, current, EPOLLIN);
  GATEWAY_CHECK(fixture.events == 1 && fixture.lease.id() != id);
}

void testCapacityAndExpiry() {
  PoolFixture fixture;
  auto first = fixture.acquire();
  GATEWAY_CHECK(fixture.pool.snapshot().leased == 1);
  auto second = fixture.acquire();
  GATEWAY_CHECK(fixture.pool.snapshot().total == 2);
  auto rejected = fixture.acquire();
  GATEWAY_CHECK(!rejected.valid() &&
                fixture.pool.snapshot().capacityRejected == 1);
  first.markConnected();
  second.markConnected();
  first.releaseReusable();
  second.releaseReusable();
  GATEWAY_CHECK(fixture.pool.snapshot().idle == 1 &&
                fixture.pool.snapshot().total == 1);
  fixture.pool.cleanupRetired();
  fixture.io.time += std::chrono::milliseconds(10);
  auto fresh = fixture.acquire();
  GATEWAY_CHECK(!fresh.reused() && fixture.loop.timerCount() == 0);
  fresh.markConnected();
  fresh.releaseReusable();
  fixture.pool.stopAcquisition();
  GATEWAY_CHECK(fixture.pool.snapshot().total == 0 &&
                fixture.loop.timerCount() == 0);
  GATEWAY_CHECK(!fixture.acquire().valid());
  fixture.pool.cleanupRetired();
  GATEWAY_CHECK(fixture.pool.snapshot().retired == 0);
}

void testDirtyCandidates() {
  for (int scenario = 0; scenario < 6; ++scenario) {
    PoolFixture fixture;
    auto lease = fixture.acquire();
    lease.markConnected();
    lease.releaseReusable();
    const auto old = fixture.pool.snapshot().created;
    if (scenario == 0) fixture.io.peekResult = 1;
    if (scenario == 1) fixture.io.peekResult = 0;
    if (scenario == 2) fixture.io.peekError = ECONNRESET;
    if (scenario == 3) fixture.io.socketFailure = ECONNRESET;
    if (scenario == 4) fixture.io.interrupts = 32;
    if (scenario == 5) fixture.io.interrupts = 2;
    auto next = fixture.acquire();
    GATEWAY_CHECK(next.valid() && next.reused() == (scenario == 5));
    GATEWAY_CHECK(fixture.pool.snapshot().created == old + (scenario != 5));
    GATEWAY_CHECK(fixture.io.peeks <= 33);
  }
  for (int scenario = 0; scenario < 5; ++scenario) {
    PoolFixture fixture;
    auto lease = fixture.acquire();
    lease.markConnected();
    if (scenario == 0) fixture.io.peekResult = 1;
    if (scenario == 1) fixture.io.peekResult = 0;
    if (scenario == 2) fixture.io.socketFailure = EIO;
    if (scenario == 3) fixture.io.interrupts = 32;
    if (scenario == 4) fixture.pool.stopAcquisition();
    lease.releaseReusable();
    GATEWAY_CHECK(fixture.pool.snapshot().total == 0);
  }
  PoolFixture fixture;
  for (int round = 0; round < 100; ++round) {
    auto lease = fixture.acquire();
    lease.markConnected();
    lease.releaseReusable();
    const auto snapshot = fixture.pool.snapshot();
    GATEWAY_CHECK(snapshot.total == 1 && snapshot.idle == 1 &&
                  fixture.loop.timerCount() == 1);
  }
  auto active = fixture.acquire();
  active.markConnected();
  auto second = fixture.acquire();
  fixture.pool.stopAcquisition();
  GATEWAY_CHECK(active.valid() && second.valid());
  fixture.pool.closeAllConnections();
  GATEWAY_CHECK(!active.valid() && !second.valid());
  fixture.pool.cleanupRetired();
  GATEWAY_CHECK(fixture.pool.snapshot().total == 0 &&
                fixture.loop.timerCount() == 0);
}

void testConfig() {
  const std::string base =
      "{\"upstream_address\":\"127.0.0.1\",\"upstream_port\":9";
  const auto original = app::parseConfig(base + "}");
  GATEWAY_CHECK(original.upstreamPool.maxConnections == 16 &&
                original.upstreamPool.maxIdle == 16);
  for (const auto* value :
       {"{}", "{\"max_idle\":0}",
        "{\"max_connections\":256,\"max_idle\":256,\"idle_timeout_ms\":300000}",
        "{\"max_connections\":1,\"max_idle\":1,\"idle_timeout_ms\":10}"}) {
    app::parseConfig(base + ",\"upstream_pool\":" + value + "}");
    GATEWAY_CHECK(true);
  }
  for (const auto* value :
       {"[]", "null", "true", "1", "{\"unknown\":1}", "{\"max_connections\":0}",
        "{\"max_connections\":257}", "{\"max_connections\":2}",
        "{\"max_idle\":17}", "{\"max_idle\":-1}", "{\"max_idle\":1.0}",
        "{\"max_idle\":true}", "{\"max_idle\":18446744073709551616}",
        "{\"idle_timeout_ms\":9}", "{\"idle_timeout_ms\":300001}",
        "{\"max_idle\":1,\"max_idle\":2}"}) {
    bool rejected = false;
    try {
      app::parseConfig(base + ",\"upstream_pool\":" + value + "}");
    } catch (const std::invalid_argument&) {
      rejected = true;
    }
    GATEWAY_CHECK(rejected);
  }
}
}  // namespace

int main() {
  try {
    testConfig();
    testOwnershipAndTokens();
    testCapacityAndExpiry();
    testDirtyCandidates();
    std::cout << "Pool state/identity/config checks: " << gateway::test::checks
              << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
