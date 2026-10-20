#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>

#include "gateway/GatewayRuntime.h"

namespace gateway::gateway_api {
struct Trace {
  std::string model;
  std::string outcome;
  bool stream = false;
  std::int64_t accepted = 0;
  std::int64_t enqueued = 0;
  std::int64_t dispatched = 0;
  std::int64_t completed = 0;
  std::int64_t finished = 0;
};

struct AdmissionSessionTestAccess {
  static std::int64_t ticks(SessionIo::Clock::time_point time) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
               time.time_since_epoch())
        .count();
  }

  static Trace trace(const ProxySession& session) {
    return {session.requestModel_,
            session.outcomeCode_,
            session.streamRequest_,
            ticks(session.acceptedAt_),
            ticks(session.enqueuedAt_),
            ticks(session.dispatchedAt_),
            ticks(session.upstreamCompletedAt_),
            ticks(session.finishedAt_)};
  }
};

struct RuntimeTestAccess {
  std::map<std::uint64_t, Trace> records;
  std::size_t peakActive = 0;
  std::size_t peakBackend = 0;
  std::size_t peakQueue = 0;
  std::uint64_t peakBytes = 0;
  std::string tracePath;
  std::vector<admission::QueueSnapshot> modelPeaks;

  void observe(const GatewayRuntime& runtime);

  void cleanup(GatewayRuntime& runtime);

  void install(GatewayRuntime& runtime);

  static bool stopped(const GatewayRuntime& runtime) {
    return runtime.stopping_ && runtime.sessions_.empty();
  }

  void write(const GatewayRuntime& runtime, const std::string& path) const;
};

void RuntimeTestAccess::observe(const GatewayRuntime& runtime) {
  peakActive = std::max(peakActive, runtime.router_.activeRequests());
  for (std::size_t index = 0; index < runtime.router_.size(); ++index)
    peakBackend =
        std::max(peakBackend, runtime.router_.snapshot(index).inflight);
  if (runtime.admission_) {
    peakQueue = std::max(peakQueue, runtime.admission_->total().count);
    peakBytes = std::max(peakBytes, runtime.admission_->total().bytes);
    modelPeaks.resize(runtime.admission_->modelCount());
    for (std::size_t index = 0; index < modelPeaks.size(); ++index) {
      const auto counts = runtime.admission_->snapshot(index);
      modelPeaks[index].count = std::max(modelPeaks[index].count, counts.count);
      modelPeaks[index].bytes = std::max(modelPeaks[index].bytes, counts.bytes);
    }
  }
  for (const auto& [id, session] : runtime.sessions_)
    records[id] = AdmissionSessionTestAccess::trace(*session);
}

void RuntimeTestAccess::cleanup(GatewayRuntime& runtime) {
  observe(runtime);
  runtime.onCleanup();
  observe(runtime);
  write(runtime, tracePath);
}

void RuntimeTestAccess::install(GatewayRuntime& runtime) {
  runtime.loop_.registerCleanupCallback([this, &runtime] { cleanup(runtime); });
}

void RuntimeTestAccess::write(const GatewayRuntime& runtime,
                              const std::string& path) const {
  std::ofstream out(path + ".partial");
  const auto snapshot = runtime.snapshot();
  out << "{\"peak_inflight\":" << peakActive
      << ",\"peak_backend\":" << peakBackend << ",\"peak_queue\":" << peakQueue
      << ",\"peak_bytes\":" << peakBytes
      << ",\"final_queue\":" << runtime.admission_->total().count
      << ",\"final_bytes\":" << runtime.admission_->total().bytes
      << ",\"final_inflight\":" << runtime.router_.activeRequests()
      << ",\"final_sessions\":" << snapshot.activeSessions
      << ",\"final_reserved\":" << snapshot.reservedBytes
      << ",\"final_timers\":" << snapshot.activeTimers << ",\"records\":[";
  bool first = true;
  for (const auto& [id, trace] : records) {
    if (!first) out << ',';
    first = false;
    out << "{\"id\":" << id << ",\"model\":\"" << trace.model
        << "\",\"stream\":" << (trace.stream ? "true" : "false")
        << ",\"outcome\":\"" << trace.outcome
        << "\",\"accepted\":" << trace.accepted
        << ",\"enqueued\":" << trace.enqueued
        << ",\"dispatched\":" << trace.dispatched
        << ",\"upstream_complete\":" << trace.completed
        << ",\"finished\":" << trace.finished << '}';
  }
  out << "],\"model_peaks\":[";
  for (std::size_t index = 0; index < modelPeaks.size(); ++index) {
    if (index) out << ',';
    out << "{\"count\":" << modelPeaks[index].count
        << ",\"bytes\":" << modelPeaks[index].bytes << '}';
  }
  out << "]}\n";
  if (!out) throw std::runtime_error("trace write failed");
  out.close();
  std::filesystem::rename(path + ".partial", path);
}
}  // namespace gateway::gateway_api

int main(int argc, char** argv) {
  try {
    if (argc != 3)
      throw std::invalid_argument("config and trace paths required");
    gateway::gateway_api::GatewayRuntime runtime(
        gateway::app::readConfig(argv[1]));
    gateway::gateway_api::RuntimeTestAccess observer;
    observer.tracePath = argv[2];
    observer.install(runtime);
    std::cout << runtime.startListener() << std::endl;
    while (!observer.stopped(runtime)) runtime.pollOnce(20);
    observer.observe(runtime);
    observer.write(runtime, argv[2]);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
