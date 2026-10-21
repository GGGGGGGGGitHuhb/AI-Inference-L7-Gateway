#include <arpa/inet.h>

#include <iostream>
#include <map>

#include "gateway/GatewayRuntime.h"
#include "nlohmann/json.hpp"

namespace gateway::gateway_api {
using Json = nlohmann::json;
using Clock = SessionIo::Clock;

struct AdmissionSessionTestAccess {
  static std::int64_t ticks(Clock::time_point value) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
               value.time_since_epoch())
        .count();
  }

  static Json readTrace(const ProxySession& session);
};

Json AdmissionSessionTestAccess::readTrace(const ProxySession& session) {
  sockaddr_in peer{};
  socklen_t size = sizeof(peer);
  Json trace = {{"accepted", ticks(session.acceptedAt_)},
                {"enqueued", ticks(session.enqueuedAt_)},
                {"dispatched", ticks(session.dispatchedAt_)},
                {"upstream_complete", ticks(session.upstreamCompletedAt_)},
                {"finished", ticks(session.finishedAt_)},
                {"outcome", session.outcomeCode_},
                {"waiting", session.queued_},
                {"active", session.requestLease_.active()}};
  if (::getpeername(session.downstreamSocket_.fd(),
                    reinterpret_cast<sockaddr*>(&peer), &size) == 0)
    trace["client_port"] = ntohs(peer.sin_port);
  if (session.dispatchedAt_ != Clock::time_point{})
    trace["backend"] = session.requestLease_.index();
  return trace;
}

struct RuntimeTestAccess {
  std::map<std::uint64_t, Json> lastTrace;
  std::map<std::uint64_t, unsigned> transitions;
  Clock::time_point nextSample{};
  std::size_t peakInflight = 0;
  std::size_t peakQueueCount = 0;
  std::size_t peakQueueBytes = 0;
  std::vector<std::size_t> backendPeaks;

  static void emitMessage(const Json& value, std::size_t limit);
  void collectTransitions(const GatewayRuntime& runtime);
  void sampleResources(const GatewayRuntime& runtime, bool force = false);
  void onCleanup(GatewayRuntime& runtime);
  void installObserver(GatewayRuntime& runtime);

  static bool isStopped(const GatewayRuntime& runtime) {
    return runtime.stopping_ && runtime.sessions_.empty();
  }
};

void RuntimeTestAccess::emitMessage(const Json& value, std::size_t limit) {
  const auto text = value.dump();
  if (text.size() + 1 > limit) throw std::runtime_error("IPC record bound");
  std::cout << text << '\n' << std::flush;
  if (!std::cout) throw std::runtime_error("IPC write failure");
}

void RuntimeTestAccess::collectTransitions(const GatewayRuntime& runtime) {
  if (transitions.size() > 256) throw std::runtime_error("cell ID bound");
  for (const auto& [id, session] : runtime.sessions_) {
    auto trace = AdmissionSessionTestAccess::readTrace(*session);
    // socket关闭后的采样仍保留本次会话的已知端口。
    if (!trace.contains("client_port") && lastTrace[id].contains("client_port"))
      trace["client_port"] = lastTrace[id]["client_port"];
    if (lastTrace[id] == trace) continue;
    if (++transitions[id] > 16) throw std::runtime_error("transition bound");
    lastTrace[id] = trace;
    trace["type"] = "transition";
    trace["id"] = id;
    emitMessage(trace, 1024);
  }
  peakInflight = std::max(peakInflight, runtime.router_.activeRequests());
  backendPeaks.resize(runtime.router_.size());
  for (std::size_t i = 0; i < backendPeaks.size(); ++i)
    backendPeaks[i] =
        std::max(backendPeaks[i], runtime.router_.snapshot(i).inflight);
  if (runtime.admission_) {
    peakQueueCount =
        std::max(peakQueueCount, runtime.admission_->total().count);
    peakQueueBytes =
        std::max(peakQueueBytes, runtime.admission_->total().bytes);
  }
}

void RuntimeTestAccess::sampleResources(const GatewayRuntime& runtime,
                                        bool force) {
  if (!force && Clock::now() < nextSample) return;
  nextSample = Clock::now() + std::chrono::milliseconds(100);
  const auto state = runtime.snapshot();
  const auto& budget = state.budget;
  Json row = {{"type", "state"},
              {"time", AdmissionSessionTestAccess::ticks(Clock::now())},
              {"sessions", state.activeSessions},
              {"reserved", budget.reserved},
              {"capacity", budget.streamCapacity},
              {"pending", budget.pending},
              {"paused", budget.paused},
              {"pauses", budget.pauses},
              {"resumes", budget.resumes},
              {"peak_reserved", budget.peakReserved},
              {"peak_capacity", budget.peakStreamCapacity},
              {"peak_pending", budget.peakPending},
              {"timers", state.activeTimers},
              {"upstreams", state.activeUpstreams},
              {"leased", state.pool.leased},
              {"idle", state.pool.idle},
              {"pool_total", state.pool.total},
              {"inflight", runtime.router_.activeRequests()},
              {"peak_inflight", peakInflight},
              {"backend_peaks", backendPeaks},
              {"queue_count", 0},
              {"queue_bytes", 0},
              {"peak_queue_count", peakQueueCount},
              {"peak_queue_bytes", peakQueueBytes}};
  if (runtime.admission_) {
    row["queue_count"] = runtime.admission_->total().count;
    row["queue_bytes"] = runtime.admission_->total().bytes;
  }
  emitMessage(row, 4096);
}

void RuntimeTestAccess::onCleanup(GatewayRuntime& runtime) {
  collectTransitions(runtime);
  runtime.onCleanup();
  sampleResources(runtime);
}

void RuntimeTestAccess::installObserver(GatewayRuntime& runtime) {
  runtime.loop_.registerCleanupCallback(
      [this, &runtime] { onCleanup(runtime); });
}
}  // namespace gateway::gateway_api

int main(int argc, char** argv) {
  try {
    if (argc != 2) throw std::invalid_argument("configuration path required");
    gateway::gateway_api::GatewayRuntime runtime(
        gateway::app::readConfig(argv[1]));
    gateway::gateway_api::RuntimeTestAccess observer;
    observer.installObserver(runtime);
    const auto port = runtime.startListener();
    observer.emitMessage({{"type", "ready"}, {"port", port}}, 1024);
    observer.sampleResources(runtime, true);
    while (!observer.isStopped(runtime)) {
      runtime.pollOnce(20);
      observer.sampleResources(runtime);
    }
    observer.sampleResources(runtime, true);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
