#pragma once
#include <cstdint>
#include <string>
#include <string_view>

namespace gateway::app {
struct Timeouts {
  int request = 10000;
  int connect = 3000;
  int upstreamWrite = 5000;
  int response = 30000;
  int downstreamWrite = 10000;
  int total = 60000;
  int shutdown = 3000;
};

struct GatewayConfig {
  std::string listenAddress = "127.0.0.1";
  std::uint16_t listenPort = 8080;
  std::string upstreamAddress;
  std::uint16_t upstreamPort = 0;

  std::size_t maxConnections = 16;
  std::uint64_t maxReservedBytes = 268435456;

  Timeouts timeouts;
};

GatewayConfig parseConfig(std::string_view content);
GatewayConfig readConfig(const std::string& path);
}  // namespace gateway::app
