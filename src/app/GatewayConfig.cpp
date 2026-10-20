#include "app/GatewayConfig.h"

#include <arpa/inet.h>

#include <fstream>
#include <nlohmann/json.hpp>
#include <set>
#include <stdexcept>
#include <vector>

namespace gateway::app {
namespace {
using Json = nlohmann::json;
class DuplicateGuard {
 public:
  bool onParse(int depth, Json::parse_event_t event, Json& value);

 private:
  std::vector<std::set<std::string>> keys_;
};

bool DuplicateGuard::onParse(int depth, Json::parse_event_t event,
                             Json& value) {
  if (depth > 6) throw std::invalid_argument("config nesting");
  if (event == Json::parse_event_t::object_start) keys_.emplace_back();
  if (event == Json::parse_event_t::key &&
      !keys_.back().insert(value.get<std::string>()).second)
    throw std::invalid_argument("duplicate config key");
  if (event == Json::parse_event_t::object_end) keys_.pop_back();
  return true;
}

std::uint64_t integer(const Json& value, std::uint64_t minimum,
                      std::uint64_t maximum) {
  if (!value.is_number_integer() ||
      (value.is_number_integer() && !value.is_number_unsigned() &&
       value.get<std::int64_t>() < 0))
    throw std::invalid_argument("integer required");
  const auto number = value.get<std::uint64_t>();
  if (number < minimum || number > maximum)
    throw std::invalid_argument("integer out of range");
  return number;
}

std::string address(const Json& value) {
  if (!value.is_string()) throw std::invalid_argument("IPv4 string required");
  auto text = value.get<std::string>();
  in_addr parsed{};
  if (text.find('\0') != std::string::npos ||
      inet_pton(AF_INET, text.c_str(), &parsed) != 1)
    throw std::invalid_argument("invalid IPv4");
  return text;
}

void readTimeouts(const Json& object, Timeouts& timeouts) {
  if (!object.is_object())
    throw std::invalid_argument("timeouts object required");
  for (const auto& [key, value] : object.items()) {
    const auto milliseconds = static_cast<int>(integer(value, 10, 300000));
    if (key == "request")
      timeouts.request = milliseconds;
    else if (key == "connect")
      timeouts.connect = milliseconds;
    else if (key == "upstream_write")
      timeouts.upstreamWrite = milliseconds;
    else if (key == "response")
      timeouts.response = milliseconds;
    else if (key == "stream_idle")
      timeouts.streamIdle = milliseconds;
    else if (key == "downstream_write")
      timeouts.downstreamWrite = milliseconds;
    else if (key == "total")
      timeouts.total = milliseconds;
    else if (key == "shutdown")
      timeouts.shutdown = milliseconds;
    else
      throw std::invalid_argument("unknown timeout key");
  }
}

void readStreamBuffer(const Json& object, StreamBufferConfig& buffer) {
  if (!object.is_object())
    throw std::invalid_argument("stream_buffer object required");
  for (const auto& [key, value] : object.items()) {
    if (key == "high_water_bytes")
      buffer.highWaterBytes = integer(value, 32768, 229376);
    else if (key == "low_water_bytes")
      buffer.lowWaterBytes = integer(value, 0, 229375);
    else if (key == "max_total_bytes")
      buffer.maxTotalBytes = integer(value, 262144, 67108864);
    else
      throw std::invalid_argument("unknown stream_buffer key");
  }
  if (buffer.lowWaterBytes >= buffer.highWaterBytes)
    throw std::invalid_argument("low water must be below high water");
}

void readPool(const Json& object, PoolConfig& pool) {
  if (!object.is_object())
    throw std::invalid_argument("upstream_pool object required");
  for (const auto& [key, value] : object.items()) {
    if (key == "max_connections")
      pool.maxConnections = integer(value, 1, 256);
    else if (key == "max_idle")
      pool.maxIdle = integer(value, 0, 256);
    else if (key == "idle_timeout_ms")
      pool.idleTimeoutMs = integer(value, 10, 300000);
    else
      throw std::invalid_argument("unknown upstream_pool key");
  }
  if (pool.maxIdle > pool.maxConnections)
    throw std::invalid_argument("max_idle exceeds max_connections");
}

void requireKeys(const Json& object, const std::set<std::string>& allowed,
                 const std::set<std::string>& required) {
  if (!object.is_object()) throw std::invalid_argument("object required");
  for (const auto& key : required)
    if (!object.contains(key)) throw std::invalid_argument("missing field");
  for (const auto& [key, value] : object.items())
    if (!allowed.contains(key)) throw std::invalid_argument("unknown field");
}

std::string boundedName(const Json& value, std::size_t maximum,
                        bool identifier) {
  if (!value.is_string()) throw std::invalid_argument("name string required");
  const auto name = value.get<std::string>();
  if (name.empty() || name.size() > maximum)
    throw std::invalid_argument("name length");
  for (unsigned char character : name) {
    if (character < 32 || character == 127)
      throw std::invalid_argument("name control byte");
    if (identifier &&
        !((character >= 'a' && character <= 'z') ||
          (character >= 'A' && character <= 'Z') ||
          (character >= '0' && character <= '9') || character == '_' ||
          character == '.' || character == '-'))
      throw std::invalid_argument("backend identifier");
  }
  return name;
}

void readModels(const Json& value, GatewayConfig& config) {
  if (!value.is_array() || value.empty() || value.size() > 32)
    throw std::invalid_argument("model count");
  std::set<std::string> names;
  std::size_t total = 0;
  for (const auto& object : value) {
    requireKeys(object, {"name", "policy", "backends"}, {"name", "backends"});
    ModelConfig model;
    model.name = boundedName(object.at("name"), 256, false);
    if (!names.insert(model.name).second)
      throw std::invalid_argument("duplicate model");
    if (object.contains("policy")) {
      if (object.at("policy") == "least_inflight")
        model.policy = RoutingPolicy::kLeastInflight;
      else if (object.at("policy") != "round_robin")
        throw std::invalid_argument("routing policy");
    }
    const auto& backends = object.at("backends");
    if (!backends.is_array() || backends.empty() ||
        backends.size() > 64 - total)
      throw std::invalid_argument("backend count");
    std::set<std::string> ids;
    std::set<std::pair<std::string, unsigned>> endpoints;
    for (const auto& backend : backends) {
      requireKeys(backend, {"id", "address", "port"},
                  {"id", "address", "port"});
      BackendConfig target{
          boundedName(backend.at("id"), 64, true),
          address(backend.at("address")),
          static_cast<std::uint16_t>(integer(backend.at("port"), 1, 65535))};
      if (target.address == "0.0.0.0" || !ids.insert(target.id).second ||
          !endpoints.emplace(target.address, target.port).second)
        throw std::invalid_argument("duplicate or unspecified backend");
      model.backends.push_back(std::move(target));
      ++total;
    }
    config.models.push_back(std::move(model));
  }
}

void readHealth(const Json& object, HealthConfig& health) {
  requireKeys(object, {"failure_threshold", "cooldown_ms"}, {});
  if (object.contains("failure_threshold"))
    health.failureThreshold = integer(object.at("failure_threshold"), 1, 16);
  if (object.contains("cooldown_ms"))
    health.cooldownMs = integer(object.at("cooldown_ms"), 10, 300000);
}

}  // namespace

GatewayConfig parseConfig(std::string_view content) {
  if (content.size() > 65536) throw std::invalid_argument("config size");
  try {
    DuplicateGuard guard;
    auto document = Json::parse(
        content, [&guard](int depth, Json::parse_event_t event, Json& value) {
          return guard.onParse(depth, event, value);
        });
    if (!document.is_object() ||
        (document.contains("models") &&
         (document.contains("upstream_address") ||
          document.contains("upstream_port"))) ||
        (!document.contains("models") &&
         (!document.contains("upstream_address") ||
          !document.contains("upstream_port"))) ||
        (!document.contains("models") && document.contains("health")))
      throw std::invalid_argument("required config fields");
    GatewayConfig config;
    for (const auto& [key, value] : document.items()) {
      if (key == "models")
        readModels(value, config);
      else if (key == "health")
        readHealth(value, config.health);
      else if (key == "listen_address")
        config.listenAddress = address(value);
      else if (key == "upstream_address")
        config.upstreamAddress = address(value);
      else if (key == "listen_port")
        config.listenPort = integer(value, 0, 65535);
      else if (key == "upstream_port")
        config.upstreamPort = integer(value, 1, 65535);
      else if (key == "max_connections")
        config.maxConnections = integer(value, 1, 256);
      else if (key == "max_reserved_bytes")
        config.maxReservedBytes = integer(value, 16777216, 4294967296ULL);
      else if (key == "upstream_pool")
        readPool(value, config.upstreamPool);
      else if (key == "stream_buffer")
        readStreamBuffer(value, config.streamBuffer);
      else if (key == "timeouts_ms")
        readTimeouts(value, config.timeouts);
      else
        throw std::invalid_argument("unknown config key");
    }
    if (config.upstreamAddress == "0.0.0.0")
      throw std::invalid_argument("unspecified upstream");
    if (config.models.empty() && config.listenPort == config.upstreamPort &&
        (config.listenAddress == config.upstreamAddress ||
         config.listenAddress == "0.0.0.0"))
      throw std::invalid_argument("self upstream");
    std::size_t backendCount = 0;
    for (const auto& model : config.models) {
      backendCount += model.backends.size();
      for (const auto& backend : model.backends)
        if (config.listenPort == backend.port &&
            (config.listenAddress == backend.address ||
             config.listenAddress == "0.0.0.0"))
          throw std::invalid_argument("self upstream");
    }
    if (backendCount > 1024 / config.upstreamPool.maxConnections)
      throw std::invalid_argument("aggregate pool capacity");
    return config;
  } catch (const Json::exception&) {
    throw std::invalid_argument("invalid config JSON");
  }
}

GatewayConfig readConfig(const std::string& path) {
  std::ifstream file(path, std::ios::binary);
  if (!file) throw std::invalid_argument("cannot read config");
  std::string content;
  char block[4096];
  while (file) {
    file.read(block, sizeof(block));
    const auto count = static_cast<std::size_t>(file.gcount());
    if (count > 65536 - content.size())
      throw std::invalid_argument("config size");
    content.append(block, count);
  }

  if (!file.eof()) throw std::invalid_argument("config read failed");
  return parseConfig(content);
}
}  // namespace gateway::app
