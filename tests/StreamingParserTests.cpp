#include <algorithm>
#include <memory>
#include <random>
#include <string>

#include "TestSupport.h"
#include "gateway/TextRequest.h"
#include "http/HttpNormalization.h"
#include "http/HttpParser.h"
#include "http/StreamOutput.h"

namespace {
using namespace gateway;
using http::HttpParser;
using http::MessageKind;
using http::ParseStatus;
using http::ResponseMode;
const std::string kPayload =
    "\xef\xbb\xbf: comment\r\ndata: hel\xe4\xbd\xa0\n"
    "data: next\n\ndata: [DONE]\n\ndata: after\n\n";

std::string headers(std::string_view framing,
                    std::string_view type = "text/event-stream") {
  return "HTTP/1.1 200 OK\r\nContent-Type: " + std::string(type) + "\r\n" +
         std::string(framing) + "\r\n";
}

void parsePieces(const std::string& wire,
                 const std::vector<std::size_t>& pieces, bool eof) {
  HttpParser parser(MessageKind::kResponse, {},
                    ResponseMode::kAllowEventStream);
  std::string decoded;
  std::size_t offset = 0;
  http::ParseResult result{ParseStatus::kNeedMore, 0, 0, "", HPE_OK};
  for (const auto count : pieces) {
    result = parser.parseBytes(std::string_view(wire).substr(offset, count));
    GATEWAY_CHECK(result.status != ParseStatus::kRejected);
    decoded += parser.bodyFragment();
    offset += count;
    GATEWAY_CHECK(parser.message().body.empty());
  }
  if (eof) result = parser.finishInput();
  GATEWAY_CHECK(result.status == ParseStatus::kComplete && decoded == kPayload);
  GATEWAY_CHECK(parser.finalHeadersReady() && parser.eventStream());
  GATEWAY_CHECK(parser.decodedTotal() == kPayload.size() &&
                parser.wireTotal() == wire.size());
  GATEWAY_CHECK(parser.parseBytes("extra").consumedBytes == 0 &&
                parser.bodyFragment().empty());
  parser.resetParser();
  GATEWAY_CHECK(!parser.finalHeadersReady() && !parser.eventStream() &&
                parser.decodedTotal() == 0);
}

void testFragmentation() {
  char number[32];
  std::snprintf(number, sizeof(number), "%zx", kPayload.size());
  for (int mode = 0; mode < 3; ++mode) {
    auto wire = headers(mode == 0 ? "Content-Length: " +
                                        std::to_string(kPayload.size()) + "\r\n"
                        : mode == 1 ? "Transfer-Encoding: chunked\r\n"
                                    : "");
    wire += mode == 1 ? std::string(number) + ";foo = bar\r\n" + kPayload +
                            "\r\n0\r\n\r\n"
                      : kPayload;
    for (std::size_t split = 0; split <= wire.size(); ++split)
      parsePieces(wire, {split, wire.size() - split}, mode == 2);
    parsePieces(wire, std::vector<std::size_t>(wire.size(), 1), mode == 2);
    std::mt19937 random(20261019);
    for (int trial = 0; trial < 20; ++trial) {
      std::vector<std::size_t> pieces;
      std::size_t left = wire.size();
      while (left) {
        const auto count =
            std::min(left, static_cast<std::size_t>(random() % 13 + 1));
        pieces.push_back(count);
        left -= count;
      }
      parsePieces(wire, pieces, mode == 2);
    }
  }
}

void testSelection() {
  for (const auto* type :
       {"text/event-stream", " TEXT/EVENT-STREAM ; CHARSET = UTF-8 ",
        "text/event-stream;charset=\"utf-8\""}) {
    HttpParser parser(MessageKind::kResponse, {},
                      ResponseMode::kAllowEventStream);
    GATEWAY_CHECK(
        parser.parseBytes(headers("Content-Length: 1\r\n", type)).status ==
        ParseStatus::kNeedMore);
    GATEWAY_CHECK(parser.finalHeadersReady() && parser.eventStream());
    GATEWAY_CHECK(parser.parseBytes("x").status == ParseStatus::kComplete &&
                  parser.bodyFragment() == "x");
  }
  for (const auto* type :
       {"text/event-stream;foo=bar", "text/event-stream;charset=ascii",
        "text/event-stream;charset=utf-8;charset=utf-8",
        "text/event-stream;"}) {
    HttpParser parser(MessageKind::kResponse, {},
                      ResponseMode::kAllowEventStream);
    GATEWAY_CHECK(
        parser.parseBytes(headers("Content-Length: 0\r\n", type)).status ==
        ParseStatus::kRejected);
    GATEWAY_CHECK(!parser.finalHeadersReady());
  }
  for (auto status : {200, 204, 304, 400, 500}) {
    HttpParser parser(MessageKind::kResponse, {},
                      ResponseMode::kAllowEventStream);
    const auto wire =
        "HTTP/1.1 " + std::to_string(status) +
        " OK\r\nContent-Type: application/json\r\nContent-Length: 0\r\n\r\n";
    GATEWAY_CHECK(parser.parseBytes(wire).status == ParseStatus::kComplete &&
                  !parser.eventStream());
  }
  for (const auto* fields :
       {"Content-Type: application/json\r\nContent-Length: 0\r\n",
        "Content-Length: 0\r\nTransfer-Encoding: chunked\r\n",
        "Content-Encoding: gzip\r\n", "Connection: content-type\r\n"}) {
    HttpParser parser(MessageKind::kResponse, {},
                      ResponseMode::kAllowEventStream);
    GATEWAY_CHECK(parser.parseBytes(headers(fields)).status ==
                  ParseStatus::kRejected);
  }
  HttpParser illegalStatus(MessageKind::kResponse, {},
                           ResponseMode::kAllowEventStream);
  GATEWAY_CHECK(
      illegalStatus
          .parseBytes("HTTP/1.1 500 Error\r\nContent-Type: "
                      "text/event-stream\r\nContent-Length: 0\r\n\r\n")
          .status == ParseStatus::kRejected);
  HttpParser buffered(MessageKind::kResponse);
  GATEWAY_CHECK(buffered.parseBytes(headers("Content-Length: 0\r\n")).status ==
                ParseStatus::kRejected);
  HttpParser informational(MessageKind::kResponse, {},
                           ResponseMode::kAllowEventStream);
  GATEWAY_CHECK(
      informational.parseBytes("HTTP/1.1 100 Continue\r\n\r\n").status ==
          ParseStatus::kNeedMore &&
      !informational.finalHeadersReady());
  GATEWAY_CHECK(
      informational.parseBytes(headers("Content-Length: 0\r\n")).status ==
          ParseStatus::kComplete &&
      informational.finalHeadersReady());
  const auto normalized = http::normalizeStreamHeaders(informational.message());
  GATEWAY_CHECK(normalized.find("Content-Length") == std::string::npos &&
                normalized.find("Transfer-Encoding: chunked") !=
                    std::string::npos);
}

void testActualStreamLimit() {
  HttpParser parser(MessageKind::kResponse, {},
                    ResponseMode::kAllowEventStream);
  GATEWAY_CHECK(parser.parseBytes(headers("")).status ==
                ParseStatus::kNeedMore);
  const std::string block(16384, 'x');
  for (int index = 0; index < 512; ++index) {
    GATEWAY_CHECK(parser.parseBytes(block).status == ParseStatus::kNeedMore);
    GATEWAY_CHECK(parser.bodyFragment().size() == block.size() &&
                  parser.message().body.empty());
  }
  GATEWAY_CHECK(parser.decodedTotal() == 8388608);
  GATEWAY_CHECK(parser.parseBytes("x").status == ParseStatus::kRejected);
  for (int length : {8388607, 8388608, 8388609}) {
    HttpParser sized(MessageKind::kResponse, {},
                     ResponseMode::kAllowEventStream);
    const auto result = sized.parseBytes(
        headers("Content-Length: " + std::to_string(length) + "\r\n"));
    GATEWAY_CHECK((result.status == ParseStatus::kRejected) ==
                  (length > 8388608));
  }
  HttpParser fallback(MessageKind::kResponse, {},
                      ResponseMode::kAllowEventStream);
  GATEWAY_CHECK(fallback
                    .parseBytes(headers("Content-Length: 4194305\r\n",
                                        "application/json"))
                    .status == ParseStatus::kRejected);
  http::ParserLimits limits;
  limits.chunks = 1;
  HttpParser chunks(MessageKind::kResponse, limits,
                    ResponseMode::kAllowEventStream);
  GATEWAY_CHECK(chunks
                    .parseBytes(headers("Transfer-Encoding: chunked\r\n") +
                                "1\r\na\r\n1\r\nb\r\n")
                    .status == ParseStatus::kRejected);
}

void testLimitsAndOutput() {
  http::ParserLimits limits;
  limits.streamBodyBytes = 8;
  for (int length : {7, 8, 9}) {
    HttpParser parser(MessageKind::kResponse, limits,
                      ResponseMode::kAllowEventStream);
    const auto result = parser.parseBytes(
        headers("Content-Length: " + std::to_string(length) + "\r\n") +
        std::string(length, 'x'));
    GATEWAY_CHECK((result.status == ParseStatus::kComplete) == (length <= 8));
  }
  auto sample = headers("") + "x";
  for (int delta : {-1, 0, 1}) {
    limits.streamWireBytes = sample.size() + delta;
    HttpParser parser(MessageKind::kResponse, limits,
                      ResponseMode::kAllowEventStream);
    parser.parseBytes(sample);
    GATEWAY_CHECK((parser.finishInput().status == ParseStatus::kComplete) ==
                  (delta >= 0));
  }
  for (const auto* ending :
       {"1\r\nx", "1\r\nx\n", "1\r\nx\r\n0\r\nBad: trailer\r\n\r\n"}) {
    HttpParser parser(MessageKind::kResponse, {},
                      ResponseMode::kAllowEventStream);
    parser.parseBytes(headers("Transfer-Encoding: chunked\r\n") + ending);
    GATEWAY_CHECK(parser.finishInput().status == ParseStatus::kRejected);
  }
  auto output = std::make_unique<http::StreamOutput>();
  for (int delta : {-1, 0, 1}) {
    output = std::make_unique<http::StreamOutput>();
    GATEWAY_CHECK(output->appendHeaders(
        std::string(http::StreamOutput::kCapacity - 6 + delta, 'h')));
    GATEWAY_CHECK(output->appendChunk("x") == (delta <= 0));
    GATEWAY_CHECK(output->size() <= http::StreamOutput::kCapacity);
  }
  output = std::make_unique<http::StreamOutput>();
  GATEWAY_CHECK(output->appendChunk("abc") &&
                output->pending() == "3\r\nabc\r\n");
  output->consumeBytes(2);
  GATEWAY_CHECK(output->pending() == "\nabc\r\n");
  output->consumeBytes(output->size());
  GATEWAY_CHECK(output->appendTerminator() && output->appendTerminator() &&
                output->pending() == "0\r\n\r\n");
  GATEWAY_CHECK(!output->appendChunk("extra"));
}
}  // namespace

int main() {
  try {
    testFragmentation();
    testSelection();
    testLimitsAndOutput();
    testActualStreamLimit();
    std::cout << "Streaming parser/output checks: " << gateway::test::checks
              << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
