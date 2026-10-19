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
  if (depth > 2) throw std::invalid_argument("config nesting");
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
}  // namespace

GatewayConfig parseConfig(std::string_view content) {
  if (content.size() > 65536) throw std::invalid_argument("config size");
  try {
    DuplicateGuard guard;
    auto document = Json::parse(
        content, [&guard](int depth, Json::parse_event_t event, Json& value) {
          return guard.onParse(depth, event, value);
        });
    if (!document.is_object() || !document.contains("upstream_address") ||
        !document.contains("upstream_port"))
      throw std::invalid_argument("required config fields");
    GatewayConfig config;
    for (const auto& [key, value] : document.items()) {
      if (key == "listen_address")
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
      else if (key == "timeouts_ms")
        readTimeouts(value, config.timeouts);
      else
        throw std::invalid_argument("unknown config key");
    }
    if (config.upstreamAddress == "0.0.0.0")
      throw std::invalid_argument("unspecified upstream");
    if (config.listenPort == config.upstreamPort &&
        (config.listenAddress == config.upstreamAddress ||
         config.listenAddress == "0.0.0.0"))
      throw std::invalid_argument("self upstream");
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
