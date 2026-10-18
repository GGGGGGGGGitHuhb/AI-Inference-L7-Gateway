#include "base/Buffer.h"

#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <utility>

namespace gateway::base {
Buffer::Buffer(std::size_t limit) noexcept : limit_(limit) {}

Buffer::Buffer(Buffer&& other) noexcept
    : storage_(std::move(other.storage_)),
      capacity_(std::exchange(other.capacity_, 0)),
      limit_(other.limit_),
      readOffset_(std::exchange(other.readOffset_, 0)),
      writeOffset_(std::exchange(other.writeOffset_, 0)),
      preparedBytes_(std::exchange(other.preparedBytes_, 0)) {}

Buffer& Buffer::operator=(Buffer&& other) noexcept {
  if (this != &other) {
    storage_ = std::move(other.storage_);
    capacity_ = std::exchange(other.capacity_, 0);
    limit_ = other.limit_;
    readOffset_ = std::exchange(other.readOffset_, 0);
    writeOffset_ = std::exchange(other.writeOffset_, 0);
    preparedBytes_ = std::exchange(other.preparedBytes_, 0);
  }
  return *this;
}

std::span<const std::byte> Buffer::readableView() const noexcept {
  if (!storage_) return {};
  return {storage_.get() + readOffset_, readableBytes()};
}

std::span<std::byte> Buffer::prepareWritableBytes(std::size_t count) {
  const auto readable = readableBytes();
  if (count > limit_ - readable)
    throw std::length_error("buffer limit exceeded");
  if (count > writableBytes()) {
    const auto required = readable + count;
    if (required <= capacity_) {
      if (readable)
        std::memmove(storage_.get(), storage_.get() + readOffset_, readable);
    } else {
      const auto doubled =
          capacity_ > limit_ - capacity_ ? limit_ : capacity_ * 2;
      const auto grown = std::max(required, doubled);
      // 先分配：分配失败时保留原有字节及全部游标。
      auto replacement =
          Storage(static_cast<std::byte*>(::operator new(grown)));
      if (readable)
        std::memcpy(replacement.get(), storage_.get() + readOffset_, readable);
      storage_ = std::move(replacement);
      capacity_ = grown;
    }
    readOffset_ = 0;
    writeOffset_ = readable;
  }
  preparedBytes_ = count;
  if (!storage_) return {};
  return {storage_.get() + writeOffset_, count};
}

void Buffer::commitWrittenBytes(std::size_t count) {
  if (count > preparedBytes_)
    throw std::out_of_range("buffer commit exceeds prepared bytes");
  writeOffset_ += count;
  preparedBytes_ = 0;
}

void Buffer::consumeReadableBytes(std::size_t count) {
  if (count > readableBytes())
    throw std::out_of_range("buffer consumption exceeds readable bytes");
  readOffset_ += count;
  preparedBytes_ = 0;
  if (readOffset_ == writeOffset_) readOffset_ = writeOffset_ = 0;
}

void Buffer::appendBytes(std::span<const std::byte> bytes) {
  auto tail = prepareWritableBytes(bytes.size());
  if (!bytes.empty()) std::memcpy(tail.data(), bytes.data(), bytes.size());
  commitWrittenBytes(bytes.size());
}

void Buffer::resetBuffer() noexcept {
  readOffset_ = writeOffset_ = preparedBytes_ = 0;
}

void Buffer::releaseEmpty(std::size_t retainLimit) noexcept {
  if (readableBytes() == 0 && capacity_ > retainLimit) {
    storage_.reset();
    capacity_ = 0;
    resetBuffer();
  }
}
}  // namespace gateway::base
