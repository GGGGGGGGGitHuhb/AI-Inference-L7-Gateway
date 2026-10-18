#pragma once

#include <cstddef>
#include <limits>
#include <memory>
#include <span>

namespace gateway::base {
// 单一所有者的连续存储；视图在下一次修改时失效。
class Buffer {
 public:
  explicit Buffer(std::size_t limit) noexcept;
  Buffer(Buffer&& other) noexcept;
  Buffer& operator=(Buffer&& other) noexcept;
  Buffer(const Buffer&) = delete;
  Buffer& operator=(const Buffer&) = delete;

  std::span<const std::byte> readableView() const noexcept;
  std::size_t readableBytes() const noexcept {
    return writeOffset_ - readOffset_;
  }
  std::size_t capacity() const noexcept { return capacity_; }
  std::size_t writableBytes() const noexcept {
    return capacity_ - writeOffset_;
  }

  std::span<std::byte> prepareWritableBytes(std::size_t count);
  void commitWrittenBytes(std::size_t count);
  void consumeReadableBytes(std::size_t count);
  // 源数据不得与此 Buffer 的存储重叠。
  void appendBytes(std::span<const std::byte> bytes);
  void resetBuffer() noexcept;
  void releaseEmpty(std::size_t retainLimit) noexcept;

 private:
  struct StorageDeleter {
    void operator()(std::byte* data) const noexcept { ::operator delete(data); }
  };

  using Storage = std::unique_ptr<std::byte[], StorageDeleter>;

  Storage storage_;
  std::size_t capacity_ = 0;
  std::size_t limit_;

  std::size_t readOffset_ = 0;
  std::size_t writeOffset_ = 0;
  std::size_t preparedBytes_ = 0;
};
}  // namespace gateway::base
