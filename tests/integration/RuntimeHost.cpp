#include <chrono>
#include <iostream>
#include <stdexcept>

#include "app/GatewayConfig.h"
#include "gateway/GatewayRuntime.h"

namespace gateway::gateway_api {
struct RuntimeTestAccess {
  static bool stopped(const GatewayRuntime& runtime) {
    return runtime.stopping_ && runtime.sessions_.empty();
  }
};
}  // namespace gateway::gateway_api

namespace {
using Clock = std::chrono::steady_clock;

void writeSnapshot(const gateway::gateway_api::GatewayRuntime& runtime) {
  const auto snapshot = runtime.snapshot();
  const auto& budget = snapshot.budget;
  const auto& pool = snapshot.pool;
  const auto now =
      std::chrono::duration<double>(Clock::now().time_since_epoch());
  std::cout << "{\"monotonic\":" << now.count()
            << ",\"sessions\":" << snapshot.activeSessions
            << ",\"reserved\":" << budget.reserved
            << ",\"capacity\":" << budget.streamCapacity
            << ",\"pending\":" << budget.pending
            << ",\"paused\":" << budget.paused
            << ",\"pauses\":" << budget.pauses
            << ",\"resumes\":" << budget.resumes
            << ",\"peak_reserved\":" << budget.peakReserved
            << ",\"peak_capacity\":" << budget.peakStreamCapacity
            << ",\"peak_pending\":" << budget.peakPending
            << ",\"timers\":" << snapshot.activeTimers
            << ",\"upstreams\":" << snapshot.activeUpstreams
            << ",\"leased\":" << pool.leased << ",\"idle\":" << pool.idle
            << ",\"pool_total\":" << pool.total
            << ",\"retired\":" << pool.retired << "}" << std::endl;
}

void runHost(const gateway::app::GatewayConfig& config) {
  gateway::gateway_api::GatewayRuntime runtime(config);
  const auto port = runtime.startListener();
  std::cout.precision(16);
  std::cout << "{\"ready_port\":" << port << "}" << std::endl;
  auto nextSample = Clock::now();
  writeSnapshot(runtime);
  while (!gateway::gateway_api::RuntimeTestAccess::stopped(runtime)) {
    runtime.pollOnce(20);
    if (Clock::now() >= nextSample) {
      writeSnapshot(runtime);
      nextSample = Clock::now() + std::chrono::milliseconds(100);
    }
  }
  writeSnapshot(runtime);
}
}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 2) throw std::invalid_argument("config path required");
    runHost(gateway::app::readConfig(argv[1]));
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
