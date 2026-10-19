#pragma once
#include <array>
#include <cstddef>
#include <string_view>

namespace gateway::http {
// 固定存储，不保留已发送历史；上限包含头、chunk封装及终止块。
class StreamOutput {
 public:
  static constexpr std::size_t kCapacity = 262144;

  bool appendHeaders(std::string_view headers);
  bool appendChunk(std::string_view bytes);
  bool appendTerminator();
  void consumeBytes(std::size_t size);

  std::string_view pending() const { return {storage_.data(), size_}; }
  std::size_t size() const { return size_; }
  std::size_t peakSize() const { return peakSize_; }
  bool terminated() const { return terminated_; }

 private:
  void appendUnchecked(std::string_view bytes);

  std::array<char, kCapacity> storage_{};
  std::size_t size_ = 0;
  std::size_t peakSize_ = 0;
  bool terminated_ = false;
};
}  // namespace gateway::http
