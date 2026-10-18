#pragma once

#include <cstddef>
#include <string>
#include <string_view>

#include "http/HttpParser.h"

namespace gateway::gateway_api {
struct JsonLimits {
  std::size_t depth = 32;
  std::size_t items = 8192;
};
struct TextRequestMetadata {
  std::string model;
  std::size_t messageCount = 0;
  bool stream = false;
};
struct ValidationResult {
  bool accepted;
  unsigned errorStatus;
  const char* errorCode;
  TextRequestMetadata metadata;
};
ValidationResult validateTextRequest(const http::HttpMessage& request,
                                     JsonLimits limits = {});
std::string errorBody(const ValidationResult& result);
}  // namespace gateway::gateway_api
