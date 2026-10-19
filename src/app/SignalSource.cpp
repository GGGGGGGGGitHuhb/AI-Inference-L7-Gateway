#include "app/SignalSource.h"

#include <sys/signalfd.h>

#include <cerrno>
#include <system_error>

namespace gateway::app {
SignalSource::SignalSource() {
  sigset_t mask;
  sigemptyset(&mask);
  sigaddset(&mask, SIGINT);
  sigaddset(&mask, SIGTERM);
  if (sigprocmask(SIG_BLOCK, &mask, &oldMask_) < 0)
    throw std::system_error(errno, std::generic_category(), "signal mask");
  const int fd = signalfd(-1, &mask, SFD_NONBLOCK | SFD_CLOEXEC);
  if (fd < 0) {
    const int error = errno;
    sigprocmask(SIG_SETMASK, &oldMask_, nullptr);
    throw std::system_error(error, std::generic_category(), "signalfd");
  }

  descriptor_.reset(fd);
}

SignalSource::~SignalSource() {
  descriptor_.reset();
  sigprocmask(SIG_SETMASK, &oldMask_, nullptr);
}
}  // namespace gateway::app
