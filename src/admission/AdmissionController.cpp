#include "admission/AdmissionController.h"

#include <limits>
#include <stdexcept>

namespace gateway::admission {
namespace {
void addCharge(std::uint64_t& total, std::uint64_t amount) {
  if (amount > std::numeric_limits<std::uint64_t>::max() - total)
    throw std::length_error("queue charge overflow");
  total += amount;
}
}  // namespace

AdmissionController::AdmissionController(const app::GatewayConfig& config)
    : limits_(config.admission), sessionLimit_(config.maxConnections) {
  app::validateAdmission(config);
  for (const auto& model : config.models)
    queues_.push_back({model.name, {}, {}});
}

std::uint64_t AdmissionController::requestCharge(
    const http::HttpMessage& message) {
  std::uint64_t charge = 1024;
  addCharge(charge, message.method.size());
  addCharge(charge, message.target.size());
  addCharge(charge, message.body.size());
  for (const auto& header : message.headers) {
    addCharge(charge, header.name.size());
    addCharge(charge, header.value.size());
    addCharge(charge, 4);
  }
  return charge;
}

std::size_t AdmissionController::modelIndex(std::string_view name) const {
  for (std::size_t index = 0; index < queues_.size(); ++index)
    if (queues_[index].name == name) return index;
  throw std::invalid_argument("unknown admission model");
}

EnqueueStatus AdmissionController::enqueueRequest(std::size_t model,
                                                  std::uint64_t sessionId,
                                                  std::uint64_t charge) {
  if (stopping_) return EnqueueStatus::kStopping;
  auto& queue = queues_.at(model);
  if (queue.counters.count >= limits_.maxQueueRequestsPerModel ||
      total_.count >= sessionLimit_)
    return EnqueueStatus::kCountLimit;
  if (!limits_.maxQueueBytesPerModel ||
      charge > limits_.maxQueueBytesPerModel - queue.counters.bytes)
    return EnqueueStatus::kByteLimit;
  if (charge > std::numeric_limits<std::uint64_t>::max() - total_.bytes)
    throw std::length_error("total queue bytes overflow");
  // 分配完成后再记账；异常不会留下不存在的队列条目。
  queue.entries.push_back({sessionId, charge});
  ++queue.counters.count;
  queue.counters.bytes += charge;
  ++total_.count;
  total_.bytes += charge;
  dirty_ = true;
  return EnqueueStatus::kQueued;
}

bool AdmissionController::removeRequest(std::uint64_t sessionId) noexcept {
  for (auto& queue : queues_) {
    for (auto entry = queue.entries.begin(); entry != queue.entries.end();
         ++entry) {
      if (entry->sessionId != sessionId) continue;
      const auto charge = entry->charge;
      queue.entries.erase(entry);
      --queue.counters.count;
      queue.counters.bytes -= charge;
      --total_.count;
      total_.bytes -= charge;
      dirty_ = true;
      return true;
    }
  }
  return false;
}

std::uint64_t AdmissionController::head(std::size_t model) const {
  const auto& entries = queues_.at(model).entries;
  return entries.empty() ? 0 : entries.front().sessionId;
}

QueueSnapshot AdmissionController::snapshot(std::size_t model) const {
  return queues_.at(model).counters;
}

void AdmissionController::advanceCursor(std::size_t model) noexcept {
  cursor_ = (model + 1) % queues_.size();
}
}  // namespace gateway::admission
