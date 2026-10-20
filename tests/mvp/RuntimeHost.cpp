#include <arpa/inet.h>

#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>

#include "gateway/GatewayRuntime.h"
#include "nlohmann/json.hpp"

namespace gateway::routing {
struct ModelRouterTestAccess {
  static std::int64_t eligibleAt(const ModelRouter& router, std::size_t index) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
               router.backends_.at(index).eligibleAt.time_since_epoch())
        .count();
  }
};
}  // namespace gateway::routing

namespace gateway::gateway_api {
using Json = nlohmann::json;
using Clock = SessionIo::Clock;

struct AdmissionSessionTestAccess {
  static std::int64_t ticks(Clock::time_point time) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
               time.time_since_epoch())
        .count();
  }

  static void record(const ProxySession& session, Json& trace);
};

void AdmissionSessionTestAccess::record(const ProxySession& session,
                                        Json& trace) {
  sockaddr_in peer{};
  socklen_t size = sizeof(peer);
  if (::getpeername(session.downstreamSocket_.fd(),
                    reinterpret_cast<sockaddr*>(&peer), &size) == 0)
    trace["client_port"] = ntohs(peer.sin_port);
  trace["model"] = session.requestModel_;
  trace["outcome"] = session.outcomeCode_;
  trace["stream"] = session.streamRequest_;
  trace["accepted"] = ticks(session.acceptedAt_);
  trace["enqueued"] = ticks(session.enqueuedAt_);
  trace["dispatched"] = ticks(session.dispatchedAt_);
  trace["upstream_complete"] = ticks(session.upstreamCompletedAt_);
  trace["finished"] = ticks(session.finishedAt_);
  trace["waiting"] = session.queued_;
  trace["request_active"] = session.requestLease_.active();
  trace["upstream_fd"] = session.upstreamLease_.fd();
  trace["downstream_eof"] = session.downstreamEof_;
  if (session.dispatchedAt_ != Clock::time_point{})
    trace["backend_index"] = session.requestLease_.index();
}

struct RuntimeTestAccess {
  std::map<std::uint64_t, Json> records;
  std::vector<std::size_t> peakBackend;
  std::vector<admission::QueueSnapshot> peakQueues;
  std::size_t peakInflight = 0;
  std::string path;
  std::string lastSignature;
  Clock::time_point nextSample{};

  void collect(const GatewayRuntime& runtime);
  void cleanup(GatewayRuntime& runtime);
  void install(GatewayRuntime& runtime);
  void writeSample(const GatewayRuntime& runtime, bool force = false);
  Json snapshot(const GatewayRuntime& runtime) const;

  static bool stopped(const GatewayRuntime& runtime) {
    return runtime.stopping_ && runtime.sessions_.empty();
  }
};

void RuntimeTestAccess::collect(const GatewayRuntime& runtime) {
  for (const auto& [id, session] : runtime.sessions_) {
    if (records.size() >= 128 && !records.contains(id))
      throw std::runtime_error("host trace bound");
    AdmissionSessionTestAccess::record(*session, records[id]);
    records[id]["id"] = id;
  }
  peakInflight = std::max(peakInflight, runtime.router_.activeRequests());
  peakBackend.resize(runtime.router_.size());
  for (std::size_t index = 0; index < peakBackend.size(); ++index)
    peakBackend[index] =
        std::max(peakBackend[index], runtime.router_.snapshot(index).inflight);
  peakQueues.resize(runtime.admission_->modelCount());
  for (std::size_t index = 0; index < peakQueues.size(); ++index) {
    const auto value = runtime.admission_->snapshot(index);
    peakQueues[index].count = std::max(peakQueues[index].count, value.count);
    peakQueues[index].bytes = std::max(peakQueues[index].bytes, value.bytes);
  }
}

Json RuntimeTestAccess::snapshot(const GatewayRuntime& runtime) const {
  const auto state = runtime.snapshot();
  const auto& budget = state.budget;
  Json result = {{"now", AdmissionSessionTestAccess::ticks(Clock::now())},
                 {"sessions", state.activeSessions},
                 {"reserved", budget.reserved},
                 {"capacity", budget.streamCapacity},
                 {"pending", budget.pending},
                 {"paused", budget.paused},
                 {"pauses", budget.pauses},
                 {"peak_reserved", budget.peakReserved},
                 {"peak_capacity", budget.peakStreamCapacity},
                 {"peak_pending", budget.peakPending},
                 {"timers", state.activeTimers},
                 {"upstreams", state.activeUpstreams},
                 {"leased", state.pool.leased},
                 {"idle", state.pool.idle},
                 {"pool_total", state.pool.total},
                 {"retired", state.pool.retired},
                 {"inflight", runtime.router_.activeRequests()},
                 {"queue_count", runtime.admission_->total().count},
                 {"queue_bytes", runtime.admission_->total().bytes},
                 {"peak_inflight", peakInflight},
                 {"stopping", runtime.stopping_},
                 {"records", Json::array()},
                 {"backends", Json::array()},
                 {"queues", Json::array()}};
  for (const auto& [id, trace] : records) result["records"].push_back(trace);
  for (std::size_t index = 0; index < runtime.router_.size(); ++index) {
    const auto& backend = runtime.router_.snapshot(index);
    result["backends"].push_back(
        {{"model", backend.model},
         {"id", backend.id},
         {"state", static_cast<int>(backend.state)},
         {"epoch", backend.epoch},
         {"inflight", backend.inflight},
         {"peak_inflight", peakBackend.at(index)},
         {"eligible_at",
          routing::ModelRouterTestAccess::eligibleAt(runtime.router_, index)}});
  }
  for (std::size_t index = 0; index < peakQueues.size(); ++index) {
    const auto queue = runtime.admission_->snapshot(index);
    result["queues"].push_back({{"model", runtime.config_.models[index].name},
                                {"count", queue.count},
                                {"bytes", queue.bytes},
                                {"peak_count", peakQueues[index].count},
                                {"peak_bytes", peakQueues[index].bytes}});
  }
  return result;
}

void RuntimeTestAccess::writeSample(const GatewayRuntime& runtime, bool force) {
  collect(runtime);
  const auto sample = snapshot(runtime);
  const auto signature = Json{
      {"records", sample["records"]},
      {"backends", sample["backends"]},
      {"queues",
       sample["queues"]}}.dump();
  if (!force && signature == lastSignature && Clock::now() < nextSample) return;
  lastSignature = signature;
  nextSample = Clock::now() + std::chrono::milliseconds(100);
  const auto text = sample.dump();
  {
    std::ofstream current(path + ".partial");
    current << text << '\n';
    if (!current) throw std::runtime_error("snapshot write failed");
  }
  std::filesystem::rename(path + ".partial", path);
  std::ofstream history(path + ".jsonl", std::ios::app);
  history << text << '\n';
  if (!history) throw std::runtime_error("history write failed");
  history.close();
  if (std::filesystem::file_size(path + ".jsonl") > 96 * 1024 * 1024)
    throw std::runtime_error("host history bound");
}

void RuntimeTestAccess::cleanup(GatewayRuntime& runtime) {
  collect(runtime);
  runtime.onCleanup();
  writeSample(runtime);
}

void RuntimeTestAccess::install(GatewayRuntime& runtime) {
  runtime.loop_.registerCleanupCallback([this, &runtime] { cleanup(runtime); });
}
}  // namespace gateway::gateway_api

int main(int argc, char** argv) {
  try {
    if (argc != 3)
      throw std::invalid_argument("config and trace paths required");
    gateway::gateway_api::GatewayRuntime runtime(
        gateway::app::readConfig(argv[1]));
    gateway::gateway_api::RuntimeTestAccess observer;
    observer.path = argv[2];
    observer.install(runtime);
    const auto port = runtime.startListener();
    observer.writeSample(runtime, true);
    std::cout << "{\"ready_port\":" << port << "}" << std::endl;
    while (!observer.stopped(runtime)) {
      runtime.pollOnce(20);
      observer.writeSample(runtime);
    }
    observer.writeSample(runtime, true);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
