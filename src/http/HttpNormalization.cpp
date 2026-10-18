#include "http/HttpNormalization.h"

#include <set>
#include <stdexcept>

namespace gateway::http {
namespace {
void requireSafeHeader(std::string_view value) {
  for (unsigned char byte : value) {
    if ((byte < 32 && byte != '\t') || byte == 127)
      throw std::invalid_argument("unsafe header");
  }
}

std::set<std::string> hopHeaders(const HttpMessage& message) {
  std::set<std::string> removed{"connection",
                                "keep-alive",
                                "proxy-connection",
                                "te",
                                "trailer",
                                "transfer-encoding",
                                "upgrade",
                                "proxy-authenticate",
                                "proxy-authorization",
                                "content-length"};
  for (const auto& header : message.headers) {
    if (header.name != "connection") continue;
    std::string_view remaining(header.value);
    do {
      const auto comma = remaining.find(',');
      removed.insert(lowerAscii(trimWhitespace(remaining.substr(0, comma))));
      if (comma == std::string_view::npos) break;
      remaining.remove_prefix(comma + 1);
    } while (true);
  }
  return removed;
}
}  // namespace

std::string normalizeMessage(const HttpMessage& message, MessageKind kind,
                             std::string_view upstreamAuthority) {
  auto removed = hopHeaders(message);
  std::string output;
  if (kind == MessageKind::kRequest) {
    if (upstreamAuthority.empty() ||
        upstreamAuthority.find_first_of(" /\\\t") != std::string_view::npos)
      throw std::invalid_argument("invalid authority");
    requireSafeHeader(upstreamAuthority);
    requireSafeHeader(message.method);
    requireSafeHeader(message.target);
    output = message.method + " " + message.target +
             " HTTP/1.1\r\nHost: " + std::string(upstreamAuthority) + "\r\n";
    removed.insert("host");
    removed.insert("authorization");
  } else
    output = "HTTP/1.1 " + std::to_string(message.statusCode) +
             " Gateway Response\r\n";
  for (const auto& header : message.headers) {
    requireSafeHeader(header.name);
    requireSafeHeader(header.value);
    if (!removed.contains(lowerAscii(header.name)))
      output += header.name + ": " + header.value + "\r\n";
  }
  if (kind == MessageKind::kRequest ||
      (message.statusCode != 204 && message.statusCode != 304))
    output += "Content-Length: " + std::to_string(message.body.size()) + "\r\n";
  output += "Via: 1.1 ai-inference-gateway\r\n\r\n";
  output += message.body;
  return output;
}

std::string serializeError(unsigned status, std::string_view body) {
  std::string output = "HTTP/1.1 " + std::to_string(status) +
                       " Request Rejected\r\nContent-Type: "
                       "application/json\r\nContent-Length: " +
                       std::to_string(body.size()) + "\r\n";
  if (status == 405) output += "Allow: POST\r\n";
  output += "\r\n";
  output += body;
  return output;
}
}  // namespace gateway::http
