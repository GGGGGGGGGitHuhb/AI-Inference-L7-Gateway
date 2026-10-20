#include <filesystem>
#include <limits>

#include "TestSupport.h"
#include "routing/ModelRouter.h"

namespace gateway::routing {
struct ModelRouterTestAccess {
  static void exhaust(ModelRouter& router) {
    router.backends_[0].snapshot.epoch =
        std::numeric_limits<std::uint64_t>::max();
  }
};
}  // namespace gateway::routing

namespace {
using namespace gateway;
using namespace routing;
using Milliseconds = std::chrono::milliseconds;

app::GatewayConfig configuration(std::size_t count = 2) {
  app::GatewayConfig config;
  app::ModelConfig model;
  model.name = "m";
  for (std::size_t index = 0; index < count; ++index)
    model.backends.push_back({std::to_string(index), "127.0.0.1",
                              static_cast<std::uint16_t>(9000 + index)});
  config.models.push_back(model);
  model.name = "other";
  config.models.push_back(model);
  config.health = {2, 10};
  return config;
}

void selectionChecks() {
  auto config = configuration();
  ModelRouter router(config);
  Clock::time_point now{};
  GATEWAY_CHECK(router.selectBackend("unknown", now).status ==
                SelectionStatus::kUnknownModel);
  for (std::size_t index = 0; index < 10; ++index) {
    auto selection = router.selectBackend("m", now);
    GATEWAY_CHECK(selection.lease.index() == index % 2);
    GATEWAY_CHECK(router.snapshot(index % 2).inflight == 1);
  }
  config.models[0].policy = app::RoutingPolicy::kLeastInflight;
  ModelRouter least(config);
  auto held = least.selectBackend("m", now);
  GATEWAY_CHECK(held.lease.index() == 0);
  for (int index = 0; index < 4; ++index) {
    auto shortRequest = least.selectBackend("m", now);
    GATEWAY_CHECK(shortRequest.lease.index() == 1);
  }
  auto other = least.selectBackend("other", now);
  GATEWAY_CHECK(other.lease.index() == 2);
  held.lease.complete(Observation::kSuccess, now);
  held.lease.complete(Observation::kFailure, now);
  GATEWAY_CHECK(least.snapshot(0).inflight == 0);
  auto tie = least.selectBackend("m", now);
  GATEWAY_CHECK(tie.lease.index() == 0);
  least.stopRouting();
  GATEWAY_CHECK(least.selectBackend("m", now).status ==
                SelectionStatus::kStopping);
}

void healthChecks() {
  const auto config = configuration(1);
  ModelRouter router(config);
  auto now = Clock::time_point{};
  for (int cycle = 0; cycle < 3; ++cycle) {
    auto first = router.selectBackend("m", now);
    first.lease.complete(Observation::kFailure, now);
    GATEWAY_CHECK(router.snapshot(0).failureCount == 1);
    auto neutral = router.selectBackend("m", now);
    neutral.lease.complete(Observation::kNeutral, now);
    GATEWAY_CHECK(router.snapshot(0).failureCount == 1);
    auto oldSuccess = router.selectBackend("m", now);
    auto oldFailure = router.selectBackend("m", now);
    auto second = router.selectBackend("m", now);
    const auto oldEpoch = second.lease.epoch();
    second.lease.complete(Observation::kFailure, now);
    GATEWAY_CHECK(router.snapshot(0).state == HealthState::kEjected);
    GATEWAY_CHECK(!router.reusable(0, oldEpoch));
    now += Milliseconds(10);
    GATEWAY_CHECK(router.selectBackend("m", now).status ==
                  SelectionStatus::kUnavailable);
    oldSuccess.lease.complete(Observation::kSuccess, now);
    oldFailure.lease.complete(Observation::kFailure, now);
    GATEWAY_CHECK(router.snapshot(0).state == HealthState::kEjected);
    GATEWAY_CHECK(router.snapshot(0).failureCount == 2);
    auto trial = router.selectBackend("m", now);
    GATEWAY_CHECK(router.snapshot(0).state == HealthState::kTrial);
    GATEWAY_CHECK(router.selectBackend("m", now).status ==
                  SelectionStatus::kUnavailable);
    trial.lease.complete(Observation::kNeutral, now);
    GATEWAY_CHECK(router.selectBackend("m", now + Milliseconds(9)).status ==
                  SelectionStatus::kUnavailable);
    now += Milliseconds(10);
    auto failedTrial = router.selectBackend("m", now);
    failedTrial.lease.complete(Observation::kFailure, now);
    now += Milliseconds(10);
    auto recovery = router.selectBackend("m", now);
    recovery.lease.complete(Observation::kSuccess, now);
    GATEWAY_CHECK(router.snapshot(0).failureCount == 0);
    GATEWAY_CHECK(router.snapshot(0).state == HealthState::kAvailable);
    GATEWAY_CHECK(router.snapshot(0).inflight == 0);
    GATEWAY_CHECK(router.snapshot(1).failureCount == 0);
  }
  auto first = router.selectBackend("m", now);
  first.lease.complete(Observation::kFailure, now);
  auto reset = router.selectBackend("m", now);
  reset.lease.complete(Observation::kSuccess, now);
  GATEWAY_CHECK(router.snapshot(0).failureCount == 0);
  ModelRouterTestAccess::exhaust(router);
  auto one = router.selectBackend("m", now);
  one.lease.complete(Observation::kFailure, now);
  auto two = router.selectBackend("m", now);
  two.lease.complete(Observation::kFailure, now);
  GATEWAY_CHECK(router.snapshot(0).state == HealthState::kExhausted);
  GATEWAY_CHECK(router.selectBackend("m", now + Milliseconds(999)).status ==
                SelectionStatus::kUnavailable);
  for (unsigned status : {200, 201, 204, 299})
    GATEWAY_CHECK(ModelRouter::classifyStatus(status) == Observation::kSuccess);
  for (unsigned status : {300, 302, 399, 401, 403, 404, 500, 503, 599})
    GATEWAY_CHECK(ModelRouter::classifyStatus(status) == Observation::kFailure);
  for (unsigned status : {400, 408, 409, 422, 429, 499})
    GATEWAY_CHECK(ModelRouter::classifyStatus(status) == Observation::kNeutral);
}
}  // namespace

void routingLifecycleChecks();

int main() {
  try {
    selectionChecks();
    healthChecks();
    const auto before =
        std::distance(std::filesystem::directory_iterator("/proc/self/fd"),
                      std::filesystem::directory_iterator());
    routingLifecycleChecks();
    const auto after =
        std::distance(std::filesystem::directory_iterator("/proc/self/fd"),
                      std::filesystem::directory_iterator());
    GATEWAY_CHECK(before == after);
    std::cout << "Routing checks=" << test::checks << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
