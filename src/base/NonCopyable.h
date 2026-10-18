#pragma once

namespace gateway::base {

class NonCopyable {
 protected:
  constexpr NonCopyable() noexcept = default;
  ~NonCopyable() = default;

  NonCopyable(NonCopyable&&) noexcept = default;
  NonCopyable& operator=(NonCopyable&&) noexcept = default;

 public:
  NonCopyable(const NonCopyable&) = delete;
  NonCopyable& operator=(const NonCopyable&) = delete;
};

}  // namespace gateway::base
