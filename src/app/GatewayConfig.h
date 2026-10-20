#pragma once
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace gateway::app {
struct Timeouts {
  int request = 10000;
  int connect = 3000;
  int upstreamWrite = 5000;
  int response = 30000;
  int streamIdle = 10000;
  int downstreamWrite = 10000;
  int total = 60000;
  int shutdown = 3000;
};

struct PoolConfig {
  std::size_t maxConnections = 16;
  std::size_t maxIdle = 16;
  int idleTimeoutMs = 5000;
};

struct StreamBufferConfig {
  std::size_t highWaterBytes = 196608;
  std::size_t lowWaterBytes = 65536;
  std::uint64_t maxTotalBytes = 4194304;
};

enum class RoutingPolicy { kRoundRobin, kLeastInflight };

struct BackendConfig {
  std::string id;
  std::string address;
  std::uint16_t port = 0;
};

struct ModelConfig {
  std::string name;
  RoutingPolicy policy = RoutingPolicy::kRoundRobin;
  std::vector<BackendConfig> backends;
};

struct HealthConfig {
  unsigned failureThreshold = 2;
  int cooldownMs = 1000;
};

struct AdmissionConfig {
  bool enabled = false;
  std::size_t maxInflight = 16;
  std::size_t maxInflightPerBackend = 4;
  std::size_t maxQueueRequestsPerModel = 16;
  std::uint64_t maxQueueBytesPerModel = 4194304;
  int queueTimeoutMs = 1000;
};

struct GatewayConfig {
  std::string listenAddress = "127.0.0.1";
  std::uint16_t listenPort = 8080;
  std::string upstreamAddress;
  std::uint16_t upstreamPort = 0;

  std::size_t maxConnections = 16;
  std::uint64_t maxReservedBytes = 268435456;

  std::vector<ModelConfig> models;
  HealthConfig health;
  AdmissionConfig admission;

  Timeouts timeouts;
  PoolConfig upstreamPool;
  StreamBufferConfig streamBuffer;
};

void validateAdmission(const GatewayConfig& config);
GatewayConfig parseConfig(std::string_view content);
GatewayConfig readConfig(const std::string& path);
}  // namespace gateway::app
