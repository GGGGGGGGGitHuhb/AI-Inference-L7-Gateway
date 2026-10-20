#include "routing/ModelRouter.h"

#include <limits>
#include <utility>

namespace gateway::routing {
RequestLease::RequestLease(ModelRouter& router, std::size_t index,
                           std::uint64_t epoch)
    : router_(&router), index_(index), epoch_(epoch), active_(true) {}

RequestLease::~RequestLease() { complete(Observation::kNeutral, Clock::now()); }

RequestLease::RequestLease(RequestLease&& other) noexcept
    : router_(other.router_),
      index_(other.index_),
      epoch_(other.epoch_),
      active_(std::exchange(other.active_, false)) {}

RequestLease& RequestLease::operator=(RequestLease&& other) noexcept {
  if (this != &other) {
    complete(Observation::kNeutral, Clock::now());
    router_ = other.router_;
    index_ = other.index_;
    epoch_ = other.epoch_;
    active_ = std::exchange(other.active_, false);
  }
  return *this;
}

void RequestLease::complete(Observation observation,
                            Clock::time_point now) noexcept {
  if (!active_) return;
  active_ = false;
  router_->completeRequest(index_, epoch_, observation, now);
}

ModelRouter::ModelRouter(const app::GatewayConfig& config)
    : health_(config.health) {
  for (const auto& model : config.models) {
    models_.push_back(
        {model.name, model.policy, backends_.size(), model.backends.size(), 0});
    for (const auto& backend : model.backends)
      backends_.push_back(
          {backend,
           {model.name, backend.id, 0, HealthState::kAvailable, 0, 1},
           {}});
  }
}

const app::BackendConfig& ModelRouter::backend(std::size_t index) const {
  return backends_.at(index).config;
}

const BackendSnapshot& ModelRouter::snapshot(std::size_t index) const {
  return backends_.at(index).snapshot;
}

bool ModelRouter::reusable(std::size_t index, std::uint64_t epoch) const {
  const auto& state = snapshot(index);
  return !stopping_ && state.epoch == epoch &&
         state.state == HealthState::kAvailable;
}

bool ModelRouter::eligible(const Backend& backend,
                           Clock::time_point now) const {
  const auto& state = backend.snapshot;
  return state.state == HealthState::kAvailable ||
         (state.state == HealthState::kEjected && !state.inflight &&
          now >= backend.eligibleAt);
}

Selection ModelRouter::selectBackend(std::string_view name,
                                     Clock::time_point now) {
  if (stopping_) return {SelectionStatus::kStopping, {}};
  for (auto& model : models_) {
    if (model.name != name) continue;
    std::size_t selected = model.count;
    std::size_t minimum = std::numeric_limits<std::size_t>::max();
    for (std::size_t offset = 0; offset < model.count; ++offset) {
      const auto candidate = (model.cursor + offset) % model.count;
      const auto& backend = backends_[model.begin + candidate];
      if (!eligible(backend, now)) continue;
      if (selected == model.count || backend.snapshot.inflight < minimum) {
        selected = candidate;
        minimum = backend.snapshot.inflight;
        if (model.policy == app::RoutingPolicy::kRoundRobin) break;
      }
    }
    if (selected == model.count) return {SelectionStatus::kUnavailable, {}};
    auto& state = backends_[model.begin + selected].snapshot;
    if (state.state == HealthState::kEjected) state.state = HealthState::kTrial;
    ++state.inflight;
    model.cursor = (selected + 1) % model.count;
    return {SelectionStatus::kSelected,
            RequestLease(*this, model.begin + selected, state.epoch)};
  }
  return {SelectionStatus::kUnknownModel, {}};
}

Observation ModelRouter::classifyStatus(unsigned status) {
  if (status >= 200 && status < 300) return Observation::kSuccess;
  if (status >= 400 && status < 500 && status != 401 && status != 403 &&
      status != 404)
    return Observation::kNeutral;
  return Observation::kFailure;
}

void ModelRouter::ejectBackend(Backend& backend,
                               Clock::time_point now) noexcept {
  auto& state = backend.snapshot;
  if (state.epoch == std::numeric_limits<std::uint64_t>::max()) {
    state.state = HealthState::kExhausted;
    return;
  }
  ++state.epoch;
  state.state = HealthState::kEjected;
  backend.eligibleAt = now + std::chrono::milliseconds(health_.cooldownMs);
}

void ModelRouter::completeRequest(std::size_t index, std::uint64_t epoch,
                                  Observation observation,
                                  Clock::time_point now) noexcept {
  auto& backend = backends_[index];
  auto& state = backend.snapshot;
  --state.inflight;
  if (epoch != state.epoch || state.state == HealthState::kExhausted) return;
  if (observation == Observation::kSuccess) {
    state.failureCount = 0;
    state.state = HealthState::kAvailable;
  } else {
    if (observation == Observation::kFailure &&
        state.failureCount < health_.failureThreshold)
      ++state.failureCount;
    if (state.state == HealthState::kTrial ||
        state.failureCount >= health_.failureThreshold)
      ejectBackend(backend, now);
  }
}
}  // namespace gateway::routing
