#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>

namespace connection_diagnosis {
struct Endpoint {
  std::uint32_t address = 0;
  std::uint16_t port = 0;
  std::uint16_t reserved = 0;
};

// 固定256字节原位补齐，未观察到的字段保持0并由flags区分。
struct Record {
  std::uint64_t generation = 0;
  std::uint64_t session = 0;
  std::array<std::uint64_t, 12> times{};
  std::array<Endpoint, 4> endpoints{};
  std::array<std::uint64_t, 2> sent{};
  std::uint64_t reservedBytes = 0;
  std::uint32_t active = 0;
  std::uint32_t closing = 0;
  std::uint32_t finished = 0;
  std::uint32_t kind = 0;
  std::uint32_t outcome = 0;
  std::uint32_t reason = 0;
  std::uint32_t firstSide = 0;
  std::uint32_t error = 0;
  std::uint32_t flags = 0;
  std::array<char, 32> reasonText{};
  std::array<std::byte, 20> padding{};
};
static_assert(sizeof(Record) == 256);

struct Header {
  std::uint64_t magic = 0x314543415254374cULL;
  std::uint64_t version = 1;
  std::uint64_t recordBytes = sizeof(Record);
  std::uint64_t capacity = 0;
  std::uint64_t count = 0;
  std::uint64_t dropped = 0;
  std::uint64_t accepts = 0;
  std::uint64_t duplicates = 0;
  std::uint64_t queries = 0;
  std::uint64_t queryFailures = 0;
  std::uint64_t active = 0;
  std::uint64_t closing = 0;
  std::uint64_t finished = 0;
  std::uint64_t pid = 0;
  std::uint64_t identityNs = 0;
  std::uint64_t exportBeginNs = 0;
  std::uint64_t exportEndNs = 0;
  std::array<std::uint64_t, 15> padding{};
};
static_assert(sizeof(Header) == 256);

enum class Time : std::size_t {
  kAccept,
  kRequest,
  kConnecting,
  kConnected,
  kSent,
  kOutput,
  kClosing,
  kFinished,
  kRemoved,
  kFirstObservation
};
enum class Outcome : std::uint32_t {
  kPending,
  kPublished,
  kConnectionLimit,
  kReservation,
  kConstruction,
  kOther
};

class ConnectionTrace {
 public:
  static constexpr std::size_t kCapacity = 131071;
  explicit ConnectionTrace(std::string directory = {},
                           std::size_t capacity = kCapacity);
  ~ConnectionTrace();
  ConnectionTrace(const ConnectionTrace&) = delete;
  ConnectionTrace& operator=(const ConnectionTrace&) = delete;

  static ConnectionTrace* processTrace();
  static std::uint64_t monotonicNs() noexcept;
  bool enabled() const { return records_ != nullptr; }
  const Header& header() const { return header_; }
  Record* acceptRecord(std::uint32_t kind, int fd, std::uint64_t acceptedNs,
                       std::uint32_t active,
                       std::uint64_t reservedBytes) noexcept;
  void observeEndpoint(Record* record, int fd, std::size_t pair) noexcept;
  void classifyAccept(Record* record, Outcome outcome,
                      std::uint64_t session = 0) noexcept;
  void recordTime(Record* record, Time event, std::uint64_t time) noexcept;
  void finishRecord(Record* record, std::uint64_t time,
                    std::uint32_t reason) noexcept;
  void removeRecord(Record* record, std::uint64_t time) noexcept;
  void firstObservation(Record* record, std::uint32_t side, int error,
                        std::uint64_t time) noexcept;
  void setReason(Record* record, const char* reason) noexcept;
  void finishTeardown(std::uint64_t time) noexcept;
  void exportRecords();

 private:
  std::string directory_;
  Header header_;
  std::unique_ptr<Record[]> records_;
  bool exported_ = false;
};
}  // namespace connection_diagnosis
