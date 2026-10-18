#include <fcntl.h>
#include <unistd.h>

#include <array>
#include <chrono>
#include <cstring>
#include <thread>

#include "TestSupport.h"
#include "base/Buffer.h"
#include "net/Socket.h"
#include "timer/TimerQueue.h"

using gateway::base::Buffer;
using gateway::net::Socket;
using gateway::timer::TimerQueue;
namespace {
void testBuffer() {
  Buffer buffer(8);
  GATEWAY_CHECK(buffer.readableView().empty());
  auto writable = buffer.prepareWritableBytes(7);
  std::memcpy(writable.data(), "abcdefg", 7);
  buffer.commitWrittenBytes(7);
  GATEWAY_CHECK(buffer.readableBytes() == 7);
  buffer.appendBytes(std::as_bytes(std::span("h", 1)));
  GATEWAY_CHECK(buffer.readableBytes() == 8);
  bool rejected = false;
  try {
    buffer.prepareWritableBytes(1);
  } catch (const std::length_error&) {
    rejected = true;
  }
  GATEWAY_CHECK(rejected && buffer.readableBytes() == 8);
  buffer.consumeReadableBytes(4);
  buffer.appendBytes(std::as_bytes(std::span("ijkl", 4)));
  // 修改后获取新视图；原视图契约已失效，不解引用它。
  GATEWAY_CHECK(std::memcmp(buffer.readableView().data(), "efghijkl", 8) == 0);
  Buffer moved(std::move(buffer));
  GATEWAY_CHECK(moved.readableBytes() == 8 && buffer.readableBytes() == 0);
  buffer = std::move(moved);
  GATEWAY_CHECK(buffer.readableBytes() == 8 && moved.capacity() == 0);
  rejected = false;
  try {
    buffer.commitWrittenBytes(1);
  } catch (const std::out_of_range&) {
    rejected = true;
  }
  GATEWAY_CHECK(rejected);
  rejected = false;
  try {
    buffer.consumeReadableBytes(9);
  } catch (const std::out_of_range&) {
    rejected = true;
  }
  GATEWAY_CHECK(rejected);
  buffer.resetBuffer();
  buffer.releaseEmpty(0);
  GATEWAY_CHECK(buffer.capacity() == 0);
  Buffer zero(0);
  GATEWAY_CHECK(zero.prepareWritableBytes(0).empty());
}

void testSocket() {
  int descriptors[2];
  GATEWAY_CHECK(pipe(descriptors) == 0);
  const int original = descriptors[0];
  {
    Socket first(original);
    Socket second(std::move(first));
    GATEWAY_CHECK(!first.valid() && second.fd() == original);
    Socket destination(descriptors[1]);
    destination = std::move(second);
    GATEWAY_CHECK(!second.valid() && fcntl(descriptors[1], F_GETFD) == -1);
    destination.reset(destination.fd());
    GATEWAY_CHECK(fcntl(original, F_GETFD) >= 0);
    destination.setNonBlocking();
    GATEWAY_CHECK(fcntl(original, F_GETFL) & O_NONBLOCK);
    const int released = destination.release();
    GATEWAY_CHECK(released == original && !destination.valid());
    destination.reset(released);
  }
  GATEWAY_CHECK(fcntl(original, F_GETFD) == -1);
  auto listener = Socket::createTcp();
  listener.setReuseAddress(true);
  listener.setTcpNoDelay(true);
  listener.bindAny(0);
  listener.listen(1);
  GATEWAY_CHECK(listener.localPort() != 0 && listener.socketError() == 0);
  GATEWAY_CHECK(!listener.acceptNonBlocking().valid());
  GATEWAY_CHECK(fcntl(listener.fd(), F_GETFD) & FD_CLOEXEC);
}

class TimerFixture {
 public:
  void onTimerExpiry() { ++fired_; }
  void onCancelOther() {
    ++fired_;
    queue_.cancelTimer(other_);
  }
  void onAddDue() {
    ++fired_;
    queue_.addTimer(now_, [this] { onTimerExpiry(); });
  }
  void onThrow() { throw std::runtime_error("injected timer failure"); }
  void runTests();

 private:
  TimerQueue queue_;
  TimerQueue::TimePoint now_ = TimerQueue::Clock::now();
  TimerQueue::Id other_ = 0;
  int fired_ = 0;
};

void TimerFixture::runTests() {
  auto first = queue_.addTimer(now_, [this] { onTimerExpiry(); });
  GATEWAY_CHECK(queue_.size() == 1 && queue_.nextDeadline() == now_);
  GATEWAY_CHECK(queue_.rescheduleTimer(first, now_ + std::chrono::seconds(1)));
  queue_.runDueTimers(now_);
  GATEWAY_CHECK(fired_ == 0);
  GATEWAY_CHECK(queue_.cancelTimer(first) && !queue_.cancelTimer(first));
  queue_.addTimer(now_, [this] { onCancelOther(); });
  other_ = queue_.addTimer(now_, [this] { onTimerExpiry(); });
  queue_.runDueTimers(now_);
  GATEWAY_CHECK(fired_ == 1 && queue_.size() == 0);
  queue_.addTimer(now_, [this] { onAddDue(); });
  queue_.runDueTimers(now_);
  GATEWAY_CHECK(fired_ == 2 && queue_.size() == 1);
  queue_.runDueTimers(now_);
  GATEWAY_CHECK(fired_ == 3 && queue_.size() == 0);
  auto cutoff = queue_.lastId();
  queue_.addTimer(now_, [this] { onTimerExpiry(); });
  queue_.runDueTimers(now_, cutoff);
  GATEWAY_CHECK(fired_ == 3);
  queue_.clearTimers();
  GATEWAY_CHECK(!queue_.nextDeadline());
  queue_.addTimer(now_, [this] { onThrow(); });
  bool rejected = false;
  try {
    queue_.runDueTimers(now_);
  } catch (const std::runtime_error&) {
    rejected = true;
  }
  GATEWAY_CHECK(rejected && queue_.size() == 0);
  queue_.addTimer(now_, [this] { onTimerExpiry(); });
  queue_.runDueTimers(now_);
  GATEWAY_CHECK(fired_ == 4);
}
}  // namespace

int main(int argc, char**) {
  try {
    GATEWAY_CHECK(argc == 1);
    testBuffer();
    testSocket();
    TimerFixture fixture;
    fixture.runTests();
    std::cout << "Foundation checks: " << gateway::test::checks << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
