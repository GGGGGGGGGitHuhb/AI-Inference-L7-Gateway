#include <unistd.h>

#include <cstdlib>
#include <filesystem>
#include <string>

#include "../TestSupport.h"
#include "diagnostics/ConnectionTrace.h"

namespace {
void checkDisabledRecorder() {
  connection_diagnosis::ConnectionTrace disabled;
  GATEWAY_CHECK(!disabled.enabled());
  GATEWAY_CHECK(disabled.acceptRecord(1, -1, 1, 0, 0) == nullptr);
  GATEWAY_CHECK(disabled.header().accepts == 0);
  GATEWAY_CHECK(disabled.header().queries == 0);
}

void checkBoundedLifecycle(const std::string& directory) {
  using namespace connection_diagnosis;
  ConnectionTrace trace(directory, 3);
  auto* first = trace.acceptRecord(1, -1, 10, 0, 0);
  trace.classifyAccept(first, Outcome::kPublished, 40);
  trace.recordTime(first, Time::kClosing, 20);
  trace.recordTime(first, Time::kClosing, 21);
  GATEWAY_CHECK(trace.header().closing == 1);
  trace.finishRecord(first, 30, 2);
  trace.finishRecord(first, 31, 3);
  GATEWAY_CHECK(first->times[7] == 30);
  GATEWAY_CHECK(trace.header().closing == 0);
  GATEWAY_CHECK(trace.header().finished == 1);
  auto* rejected = trace.acceptRecord(1, -1, 35, 1, 16777216);
  GATEWAY_CHECK(rejected->finished == 1);
  trace.classifyAccept(rejected, Outcome::kConnectionLimit);
  trace.finishRecord(rejected, 36, 0);
  trace.removeRecord(first, 50);
  trace.removeRecord(first, 51);
  GATEWAY_CHECK(first->times[8] - first->times[7] == 20);
  GATEWAY_CHECK(trace.header().active == 0);
  GATEWAY_CHECK(trace.header().finished == 0);
  auto* early = trace.acceptRecord(1, -1, 60, 0, 0);
  trace.finishRecord(early, 61, 1);
  trace.classifyAccept(early, Outcome::kPublished, 41);
  GATEWAY_CHECK(trace.header().finished == 1);
  trace.removeRecord(early, 62);
  GATEWAY_CHECK(trace.header().finished == 0);
  GATEWAY_CHECK(trace.acceptRecord(1, -1, 70, 0, 0) == nullptr);
  GATEWAY_CHECK(trace.header().count == 3);
  GATEWAY_CHECK(trace.header().dropped == 1);
  GATEWAY_CHECK(trace.header().accepts == 4);
  trace.exportRecords();
  GATEWAY_CHECK(std::filesystem::file_size(directory + "/header.bin") == 256);
  GATEWAY_CHECK(std::filesystem::file_size(directory + "/trace-0.bin") ==
                3 * 256);
}
}  // namespace

int main() {
  checkDisabledRecorder();
  const char* temporary = std::getenv("TMPDIR");
  GATEWAY_CHECK(temporary != nullptr);
  const std::string directory =
      std::string(temporary) + "/trace-unit-" + std::to_string(getpid());
  GATEWAY_CHECK(std::filesystem::create_directory(directory));
  checkBoundedLifecycle(directory);
  std::filesystem::remove_all(directory);
}
