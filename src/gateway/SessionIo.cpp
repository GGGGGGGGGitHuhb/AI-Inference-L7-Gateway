#include "gateway/SessionIo.h"

#include <cerrno>

namespace gateway::gateway_api {
SessionIo::Clock::time_point SessionIo::now() const { return Clock::now(); }

int SessionIo::connectSocket(int fd, const sockaddr* address,
                             socklen_t length) {
  return ::connect(fd, address, length);
}

int SessionIo::socketError(int fd) {
  int error = 0;
  socklen_t length = sizeof(error);
  if (::getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &length) < 0) return errno;
  return error;
}

ssize_t SessionIo::receiveBytes(int fd, void* data, std::size_t size) {
  return ::recv(fd, data, size, 0);
}

int SessionIo::shutdownWrite(int fd) { return ::shutdown(fd, SHUT_WR); }

ssize_t SessionIo::sendBytes(int fd, const void* data, std::size_t size) {
  return ::send(fd, data, size, MSG_NOSIGNAL);
}
}  // namespace gateway::gateway_api
