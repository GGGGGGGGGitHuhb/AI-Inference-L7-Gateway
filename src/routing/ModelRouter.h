#pragma once
#include <chrono>
#include <cstdint>
#include <string_view>
#include <vector>

#include "app/GatewayConfig.h"

namespace gateway::routing {
using Clock = std::chrono::steady_clock;
enum class HealthState { kAvailable, kEjected, kTrial, kExhausted };
enum class Observation { kSuccess, kFailure, kNeutral };
enum class SelectionStatus {
  kSelected,
  kUnknownModel,
  kUnavailable,
  kStopping,
  kCapacity
};

struct BackendSnapshot {
  std::string model;
  std::string id;
  std::size_t inflight = 0;
  HealthState state = HealthState::kAvailable;
  unsigned failureCount = 0;
  std::uint64_t epoch = 1;
};

class ModelRouter;
class RequestLease {
 public:
  RequestLease() = default;
  ~RequestLease();
  RequestLease(const RequestLease&) = delete;
  RequestLease& operator=(const RequestLease&) = delete;
  RequestLease(RequestLease&& other) noexcept;
  RequestLease& operator=(RequestLease&& other) noexcept;

  bool active() const { return active_; }
  std::size_t index() const { return index_; }
  std::uint64_t epoch() const { return epoch_; }

  void complete(Observation observation, Clock::time_point now) noexcept;

 private:
  friend class ModelRouter;
  RequestLease(ModelRouter& router, std::size_t index, std::uint64_t epoch);

  ModelRouter* router_ = nullptr;
  std::size_t index_ = 0;
  std::uint64_t epoch_ = 0;
  bool active_ = false;
};

struct Selection {
  SelectionStatus status;
  RequestLease lease;
};

class ModelRouter {
 public:
  explicit ModelRouter(const app::GatewayConfig& config);
  ModelRouter(const ModelRouter&) = delete;
  ModelRouter& operator=(const ModelRouter&) = delete;

  Selection selectBackend(std::string_view model, Clock::time_point now,
                          std::size_t globalLimit = 0,
                          std::size_t backendLimit = 0);
  SelectionStatus inspectModel(std::string_view model, Clock::time_point now,
                               std::size_t globalLimit = 0,
                               std::size_t backendLimit = 0) const;
  std::size_t activeRequests() const noexcept;
  void stopRouting() { stopping_ = true; }

  const app::BackendConfig& backend(std::size_t index) const;
  const BackendSnapshot& snapshot(std::size_t index) const;
  std::size_t size() const { return backends_.size(); }
  bool reusable(std::size_t index, std::uint64_t epoch) const;
  static Observation classifyStatus(unsigned status);

 private:
  friend class RequestLease;
  friend struct ModelRouterTestAccess;

  struct Backend {
    app::BackendConfig config;
    BackendSnapshot snapshot;
    Clock::time_point eligibleAt{};
  };

  struct Model {
    std::string name;
    app::RoutingPolicy policy;
    std::size_t begin;
    std::size_t count;
    std::size_t cursor = 0;
  };

  void completeRequest(std::size_t index, std::uint64_t epoch,
                       Observation observation, Clock::time_point now) noexcept;
  void ejectBackend(Backend& backend, Clock::time_point now) noexcept;
  bool eligible(const Backend& backend, Clock::time_point now) const;

  app::HealthConfig health_;
  std::vector<Model> models_;
  std::vector<Backend> backends_;
  bool stopping_ = false;
};
}  // namespace gateway::routing
