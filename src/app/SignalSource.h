#pragma once
#include <signal.h>

#include "net/Socket.h"

namespace gateway::app {
class SignalSource {
 public:
  SignalSource();
  ~SignalSource();

  int fd() const { return descriptor_.fd(); }

 private:
  sigset_t oldMask_{};
  net::Socket descriptor_;
};
}  // namespace gateway::app
