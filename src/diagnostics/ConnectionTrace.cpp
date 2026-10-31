#include "diagnostics/ConnectionTrace.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <system_error>

namespace connection_diagnosis {
namespace {
constexpr std::uint32_t kPublished = 1U << 8;
constexpr std::uint32_t kRemoved = 1U << 9;

void writeArtifact(const std::string& path, const void* data, std::size_t size,
                   std::uint64_t deadline) {
  const int fd =
      ::open(path.c_str(), O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
  if (fd < 0)
    throw std::system_error(errno, std::generic_category(), "trace open");
  const auto* bytes = static_cast<const char*>(data);
  try {
    while (size) {
      if (ConnectionTrace::monotonicNs() >= deadline)
        throw std::runtime_error("trace export deadline");
      const auto count = ::write(fd, bytes, size);
      if (count < 0 && errno == EINTR) continue;
      if (count <= 0)
        throw std::system_error(errno, std::generic_category(), "trace write");
      bytes += count;
      size -= static_cast<std::size_t>(count);
    }
    if (::close(fd) < 0) throw std::runtime_error("trace close");
  } catch (...) {
    ::close(fd);
    throw;
  }
}
}  // namespace

ConnectionTrace::ConnectionTrace(std::string directory, std::size_t capacity)
    : directory_(std::move(directory)) {
  if (directory_.empty()) return;
  if (!capacity || capacity > kCapacity)
    throw std::invalid_argument("trace capacity");
  records_ = std::make_unique<Record[]>(capacity);
  header_.capacity = capacity;
  header_.pid = static_cast<std::uint64_t>(::getpid());
  header_.identityNs = monotonicNs();
}

ConnectionTrace::~ConnectionTrace() {
  if (!enabled() || exported_) return;
  try {
    exportRecords();
  } catch (...) {
    // 导出失败必须令控制器看到非零退出，不能把缺证据当作成功。
    ::_exit(74);
  }
}

ConnectionTrace* ConnectionTrace::processTrace() {
  const char* directory = std::getenv("CONNECTION_TRACE_DIR");
  static ConnectionTrace trace(directory ? directory : "");
  return trace.enabled() ? &trace : nullptr;
}

std::uint64_t ConnectionTrace::monotonicNs() noexcept {
  return static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch())
          .count());
}

Record* ConnectionTrace::acceptRecord(std::uint32_t kind, int fd,
                                      std::uint64_t acceptedNs,
                                      std::uint32_t active,
                                      std::uint64_t reservedBytes) noexcept {
  if (!enabled()) return nullptr;
  ++header_.accepts;
  if (header_.count == header_.capacity) {
    ++header_.dropped;
    return nullptr;
  }
  auto* record = &records_[header_.count++];
  record->generation = header_.accepts;
  record->kind = kind;
  record->times[0] = acceptedNs;
  record->active = active;
  record->closing = static_cast<std::uint32_t>(header_.closing);
  record->finished = static_cast<std::uint32_t>(header_.finished);
  record->reservedBytes = reservedBytes;
  observeEndpoint(record, fd, 0);
  return record;
}

void ConnectionTrace::observeEndpoint(Record* record, int fd,
                                      std::size_t pair) noexcept {
  if (!record || pair > 1) return;
  const int savedError = errno;
  for (std::size_t side = 0; side < 2; ++side) {
    sockaddr_in address{};
    socklen_t length = sizeof(address);
    ++header_.queries;
    const int result =
        side == 0
            ? getsockname(fd, reinterpret_cast<sockaddr*>(&address), &length)
            : getpeername(fd, reinterpret_cast<sockaddr*>(&address), &length);
    if (result != 0 || address.sin_family != AF_INET) {
      ++header_.queryFailures;
      continue;
    }
    const auto index = pair * 2 + side;
    record->endpoints[index] = {ntohl(address.sin_addr.s_addr),
                                ntohs(address.sin_port), 0};
    record->flags |= 1U << index;
  }
  errno = savedError;
}

void ConnectionTrace::classifyAccept(Record* record, Outcome outcome,
                                     std::uint64_t session) noexcept {
  if (!record) return;
  if (record->outcome) {
    ++header_.duplicates;
    return;
  }
  record->outcome = static_cast<std::uint32_t>(outcome);
  record->session = session;
  if (outcome == Outcome::kPublished) {
    record->flags |= kPublished;
    ++header_.active;
    if (record->times[static_cast<std::size_t>(Time::kFinished)])
      ++header_.finished;
    else if (record->times[static_cast<std::size_t>(Time::kClosing)])
      ++header_.closing;
  }
}

void ConnectionTrace::recordTime(Record* record, Time event,
                                 std::uint64_t time) noexcept {
  if (!record) return;
  auto& value = record->times[static_cast<std::size_t>(event)];
  if (value) return;  // 同一阶段重复通知幂等，不重复推进计数。
  value = time;
  if (event == Time::kClosing && (record->flags & kPublished) &&
      !record->times[7])
    ++header_.closing;
}

void ConnectionTrace::finishRecord(Record* record, std::uint64_t time,
                                   std::uint32_t reason) noexcept {
  if (!record || record->times[7]) return;
  record->times[7] = time;
  record->reason = reason;
  if ((record->flags & kPublished) && !(record->flags & kRemoved)) {
    if (record->times[6]) --header_.closing;
    ++header_.finished;
  }
}

void ConnectionTrace::removeRecord(Record* record,
                                   std::uint64_t time) noexcept {
  if (!record || (record->flags & kRemoved)) return;
  record->times[8] = time;
  record->flags |= kRemoved;
  if (record->flags & kPublished) {
    --header_.active;
    if (record->times[7])
      --header_.finished;
    else if (record->times[6])
      --header_.closing;
  }
}

void ConnectionTrace::firstObservation(Record* record, std::uint32_t side,
                                       int error, std::uint64_t time) noexcept {
  if (!record || record->times[9]) return;
  record->times[9] = time;
  record->firstSide = side;
  record->error = static_cast<std::uint32_t>(error);
}

void ConnectionTrace::setReason(Record* record, const char* reason) noexcept {
  if (!record) return;
  std::size_t index = 0;
  for (; index < record->reasonText.size() - 1 && reason[index]; ++index)
    record->reasonText[index] = reason[index];
  if (reason[index]) record->flags |= 1U << 10;
}

void ConnectionTrace::finishTeardown(std::uint64_t time) noexcept {
  // 仅停止后调用；不在接入拒绝或事件热路径扫描记录。
  for (std::size_t index = 0; index < header_.count; ++index)
    if ((records_[index].flags & kPublished) &&
        !(records_[index].flags & kRemoved))
      removeRecord(&records_[index], time);
}

void ConnectionTrace::exportRecords() {
  if (!enabled() || exported_) return;
  header_.exportBeginNs = monotonicNs();
  const auto deadline = header_.exportBeginNs + 10'000'000'000ULL;
  // 独立进程定时器打断可能阻塞的文件写；仅导出阶段启用，不接触请求deadline。
  struct sigaction action {};
  action.sa_handler = SIG_DFL;
  sigemptyset(&action.sa_mask);
  if (::sigaction(SIGALRM, &action, nullptr) < 0)
    throw std::runtime_error("trace alarm action");
  sigset_t alarms;
  sigemptyset(&alarms);
  sigaddset(&alarms, SIGALRM);
  if (::sigprocmask(SIG_UNBLOCK, &alarms, nullptr) < 0)
    throw std::runtime_error("trace alarm mask");
  itimerval timer{};
  timer.it_value.tv_sec = 10;
  if (::setitimer(ITIMER_REAL, &timer, nullptr) < 0)
    throw std::runtime_error("trace alarm start");
  std::fprintf(stderr, "TRACE_EXPORT_BEGIN %llu\n",
               static_cast<unsigned long long>(header_.exportBeginNs));
  constexpr std::size_t kRecordsPerFile = 4096;
  for (std::size_t offset = 0; offset < header_.count;
       offset += kRecordsPerFile) {
    const auto count = std::min(
        kRecordsPerFile, static_cast<std::size_t>(header_.count) - offset);
    writeArtifact(directory_ + "/trace-" +
                      std::to_string(offset / kRecordsPerFile) + ".bin",
                  records_.get() + offset, count * sizeof(Record), deadline);
  }
  header_.exportEndNs = monotonicNs();
  writeArtifact(directory_ + "/header.bin", &header_, sizeof(header_),
                deadline);
  timer.it_value.tv_sec = 0;
  if (::setitimer(ITIMER_REAL, &timer, nullptr) < 0)
    throw std::runtime_error("trace alarm stop");
  exported_ = true;
}
}  // namespace connection_diagnosis
