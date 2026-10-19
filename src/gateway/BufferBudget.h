#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace gateway::gateway_api {
enum class FinishReason {
  kComplete,
  kCancelled,
  kTimeout,
  kUpstream,
  kCapacity,
  kInternal,
  kStopped,
  kCount
};
enum class CapacityKind { kSession, kStream };
struct BudgetSnapshot {
  std::uint64_t reserved = 0;
  std::uint64_t peakReserved = 0;
  std::uint64_t streamCapacity = 0;
  std::uint64_t peakStreamCapacity = 0;
  std::uint64_t pending = 0;
  std::uint64_t peakPending = 0;
  std::size_t paused = 0;
  std::uint64_t pauses = 0;
  std::uint64_t resumes = 0;
  std::uint64_t rejected = 0;
  std::array<std::uint64_t, static_cast<std::size_t>(FinishReason::kCount)>
      finished{};
};
class BufferBudget;
class CapacityLease {
 public:
  CapacityLease() = default;
  ~CapacityLease();
  CapacityLease(const CapacityLease&) = delete;
  CapacityLease& operator=(const CapacityLease&) = delete;
  CapacityLease(CapacityLease&& other) noexcept;
  CapacityLease& operator=(CapacityLease&& other) noexcept;

  bool valid() const { return owner_ != nullptr; }
  void release() noexcept;

 private:
  friend class BufferBudget;
  CapacityLease(BufferBudget& owner, CapacityKind kind);

  BufferBudget* owner_ = nullptr;
  CapacityKind kind_ = CapacityKind::kSession;
};

// 单Worker唯一账本；输出容量是会话预约的子预算，不能相加为可用内存。
class BufferBudget {
 public:
  static constexpr std::uint64_t kSessionBytes = 16777216;
  static constexpr std::uint64_t kStreamBytes = 262144;
  BufferBudget(std::uint64_t maxReserved, std::uint64_t maxStream);
  BufferBudget(const BufferBudget&) = delete;
  BufferBudget& operator=(const BufferBudget&) = delete;

  CapacityLease acquireCapacity(CapacityKind kind) noexcept;
  BudgetSnapshot snapshot() const { return counters_; }
  void changePending(std::size_t before, std::size_t after) noexcept;
  void recordPause() noexcept;
  void clearPause(bool resumed) noexcept;
  void recordFinish(FinishReason reason) noexcept;

 private:
  friend class CapacityLease;
  void releaseCapacity(CapacityKind kind) noexcept;

  std::uint64_t maxReserved_;
  std::uint64_t maxStream_;
  BudgetSnapshot counters_;
};
}  // namespace gateway::gateway_api
