#include "gateway/BufferBudget.h"

#include <algorithm>
#include <limits>
#include <utility>

namespace gateway::gateway_api {
namespace {
void incrementCounter(std::uint64_t& value) noexcept {
  if (value != std::numeric_limits<std::uint64_t>::max()) ++value;
}
}  // namespace

CapacityLease::CapacityLease(BufferBudget& owner, CapacityKind kind)
    : owner_(&owner), kind_(kind) {}

CapacityLease::~CapacityLease() { release(); }

CapacityLease::CapacityLease(CapacityLease&& other) noexcept
    : owner_(std::exchange(other.owner_, nullptr)), kind_(other.kind_) {}

CapacityLease& CapacityLease::operator=(CapacityLease&& other) noexcept {
  if (this != &other) {
    release();
    owner_ = std::exchange(other.owner_, nullptr);
    kind_ = other.kind_;
  }
  return *this;
}

void CapacityLease::release() noexcept {
  if (owner_) std::exchange(owner_, nullptr)->releaseCapacity(kind_);
}

BufferBudget::BufferBudget(std::uint64_t maxReserved, std::uint64_t maxStream)
    : maxReserved_(maxReserved), maxStream_(maxStream) {}

CapacityLease BufferBudget::acquireCapacity(CapacityKind kind) noexcept {
  auto& current = kind == CapacityKind::kSession ? counters_.reserved
                                                 : counters_.streamCapacity;
  auto& peak = kind == CapacityKind::kSession ? counters_.peakReserved
                                              : counters_.peakStreamCapacity;
  const auto bytes =
      kind == CapacityKind::kSession ? kSessionBytes : kStreamBytes;
  const auto maximum =
      kind == CapacityKind::kSession ? maxReserved_ : maxStream_;
  if (bytes > maximum || current > maximum - bytes) {
    incrementCounter(counters_.rejected);
    return {};
  }
  current += bytes;
  peak = std::max(peak, current);
  return CapacityLease(*this, kind);
}

void BufferBudget::releaseCapacity(CapacityKind kind) noexcept {
  if (kind == CapacityKind::kSession)
    counters_.reserved -= kSessionBytes;
  else
    counters_.streamCapacity -= kStreamBytes;
}

void BufferBudget::changePending(std::size_t before,
                                 std::size_t after) noexcept {
  counters_.pending = counters_.pending - before + after;
  counters_.peakPending = std::max(counters_.peakPending, counters_.pending);
}

void BufferBudget::recordPause() noexcept {
  ++counters_.paused;
  incrementCounter(counters_.pauses);
}

void BufferBudget::clearPause(bool resumed) noexcept {
  --counters_.paused;
  if (resumed) incrementCounter(counters_.resumes);
}

void BufferBudget::recordFinish(FinishReason reason) noexcept {
  incrementCounter(counters_.finished[static_cast<std::size_t>(reason)]);
}
}  // namespace gateway::gateway_api
