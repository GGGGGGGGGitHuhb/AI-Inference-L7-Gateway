#include "http/StreamOutput.h"

#include <algorithm>
#include <charconv>
#include <cstring>
#include <stdexcept>

namespace gateway::http {
void StreamOutput::appendUnchecked(std::string_view bytes) {
  std::memcpy(storage_.data() + size_, bytes.data(), bytes.size());
  size_ += bytes.size();
  peakSize_ = std::max(peakSize_, size_);
}

bool StreamOutput::appendHeaders(std::string_view headers) {
  if (terminated_ || headers.size() > kCapacity - size_) return false;
  appendUnchecked(headers);
  return true;
}

bool StreamOutput::appendChunk(std::string_view bytes) {
  if (bytes.empty()) return true;
  if (terminated_) return false;
  std::array<char, 2 * sizeof(std::size_t)> number{};
  const auto encoded = std::to_chars(
      number.data(), number.data() + number.size(), bytes.size(), 16);
  const auto digits = static_cast<std::size_t>(encoded.ptr - number.data());
  const auto overhead = digits + 4;
  if (overhead > kCapacity - size_ ||
      bytes.size() > kCapacity - size_ - overhead)
    return false;
  appendUnchecked({number.data(), digits});
  appendUnchecked("\r\n");
  appendUnchecked(bytes);
  appendUnchecked("\r\n");
  return true;
}

bool StreamOutput::appendTerminator() {
  if (terminated_) return true;
  if (kCapacity - size_ < 5) return false;
  appendUnchecked("0\r\n\r\n");
  terminated_ = true;
  return true;
}

void StreamOutput::consumeBytes(std::size_t size) {
  if (size > size_) throw std::out_of_range("stream consume");
  size_ -= size;
  std::memmove(storage_.data(), storage_.data() + size, size_);
}
}  // namespace gateway::http
