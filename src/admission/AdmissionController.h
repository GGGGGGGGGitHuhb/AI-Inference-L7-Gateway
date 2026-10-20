#pragma once
#include <cstdint>
#include <deque>
#include <string>
#include <string_view>
#include <vector>

#include "app/GatewayConfig.h"
#include "http/HttpParser.h"

namespace gateway::admission {
enum class EnqueueStatus { kQueued, kCountLimit, kByteLimit, kStopping };

struct QueueEntry {
  std::uint64_t sessionId;
  std::uint64_t charge;
};

struct QueueSnapshot {
  std::size_t count = 0;
  std::uint64_t bytes = 0;
};

class AdmissionController {
 public:
  explicit AdmissionController(const app::GatewayConfig& config);
  AdmissionController(const AdmissionController&) = delete;
  AdmissionController& operator=(const AdmissionController&) = delete;

  EnqueueStatus enqueueRequest(std::size_t model, std::uint64_t sessionId,
                               std::uint64_t charge);
  bool removeRequest(std::uint64_t sessionId) noexcept;
  void stopAdmission() noexcept { stopping_ = true; }
  void markDirty() noexcept { dirty_ = true; }
  void clearDirty() noexcept { dirty_ = false; }
  void advanceCursor(std::size_t model) noexcept;

  bool stopping() const { return stopping_; }
  bool dirty() const { return dirty_; }
  bool empty() const { return total_.count == 0; }
  std::size_t modelCount() const { return queues_.size(); }
  std::size_t cursor() const { return cursor_; }
  std::size_t modelIndex(std::string_view name) const;
  std::uint64_t head(std::size_t model) const;
  QueueSnapshot snapshot(std::size_t model) const;
  QueueSnapshot total() const { return total_; }
  static std::uint64_t requestCharge(const http::HttpMessage& message);

 private:
  struct ModelQueue {
    std::string name;
    std::deque<QueueEntry> entries;
    QueueSnapshot counters;
  };

  app::AdmissionConfig limits_;
  std::size_t sessionLimit_;
  std::vector<ModelQueue> queues_;
  QueueSnapshot total_;
  std::size_t cursor_ = 0;
  bool dirty_ = false;
  bool stopping_ = false;
};
}  // namespace gateway::admission
