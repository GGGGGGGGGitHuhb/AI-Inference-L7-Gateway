#pragma once

#include <iostream>
#include <stdexcept>
#include <string>

namespace gateway::test {
inline std::size_t checks = 0;
inline void require(bool condition, const char* expression, int line) {
  ++checks;
  if (!condition)
    throw std::runtime_error(std::string(expression) + " at line " +
                             std::to_string(line));
}
}  // namespace gateway::test
#define GATEWAY_CHECK(expression) \
  ::gateway::test::require((expression), #expression, __LINE__)
