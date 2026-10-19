#pragma once
#include <sys/socket.h>

#include <chrono>
#include <cstddef>

namespace gateway::gateway_api {
// 窄系统调用/时钟接缝；产品仅装配默认实现，配置没有故障注入开关。
class SessionIo {
 public:
  using Clock = std::chrono::steady_clock;

  virtual ~SessionIo() = default;

  virtual Clock::time_point now() const;

  virtual int connectSocket(int fd, const sockaddr* address, socklen_t length);
  virtual int socketError(int fd);

  virtual ssize_t receiveBytes(int fd, void* data, std::size_t size);
  virtual ssize_t peekByte(int fd);
  virtual int shutdownWrite(int fd);
  virtual ssize_t sendBytes(int fd, const void* data, std::size_t size);
};
}  // namespace gateway::gateway_api
