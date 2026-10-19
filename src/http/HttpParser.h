#pragma once

#include <llhttp.h>

#include <array>
#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace gateway::http {
enum class ResponseMode { kBuffered, kAllowEventStream };
enum class MessageKind { kRequest, kResponse };
enum class ParseStatus { kNeedMore, kComplete, kRejected };
struct Header {
  std::string name;
  std::string value;
};
struct HttpMessage {
  std::string method;
  std::string target;
  unsigned statusCode = 0;
  std::vector<Header> headers;
  std::string body;
  bool eofDelimited = false;
};
struct ParseResult {
  ParseStatus status;
  std::size_t consumedBytes;
  unsigned errorStatus;
  const char* errorCode;
  llhttp_errno_t parserError;
};
struct ParserLimits {
  std::size_t startLineBytes = 4096;
  std::size_t headerBytes = 16384;
  std::size_t headerFields = 100;
  std::size_t informationalBytes = 131072;
  std::size_t informationalResponses = 8;
  std::size_t requestBodyBytes = 1048576;
  std::size_t responseBodyBytes = 4194304;
  std::size_t requestWireBytes = 4194304;
  std::size_t responseWireBytes = 8388608;
  std::size_t chunkLineBytes = 1024;
  std::size_t chunks = 65536;
  std::size_t streamBodyBytes = 8388608;
  std::size_t streamWireBytes = 16777216;
};

class HttpParser {
 public:
  explicit HttpParser(MessageKind kind, ParserLimits limits = {},
                      ResponseMode responseMode = ResponseMode::kBuffered);
  HttpParser(const HttpParser&) = delete;
  HttpParser& operator=(const HttpParser&) = delete;
  HttpParser(HttpParser&&) = delete;
  HttpParser& operator=(HttpParser&&) = delete;

  ParseResult parseBytes(std::string_view input) noexcept;
  ParseResult finishInput() noexcept;
  void resetParser() noexcept;

  const HttpMessage& message() const { return message_; }
  bool finalHeadersReady() const { return finalHeadersReady_; }
  bool eventStream() const { return eventStream_; }
  std::size_t decodedTotal() const { return decodedTotal_; }
  std::size_t wireTotal() const { return wireBytes_; }
  // 当前parse调用产生的片段，仅在下一次parse/reset之前有效。
  std::string_view bodyFragment() const {
    return {bodyFragment_.data(), bodyFragmentSize_};
  }

 private:
  enum class WirePhase { kHeaders, kBody, kChunkLine, kChunkData, kTrailers };
  static int onUrl(llhttp_t*, const char*, std::size_t) noexcept;
  static int onHeaderField(llhttp_t*, const char*, std::size_t) noexcept;
  static int onHeaderValue(llhttp_t*, const char*, std::size_t) noexcept;
  static int onHeaderValueComplete(llhttp_t*) noexcept;
  static int onHeadersComplete(llhttp_t*) noexcept;
  static int onBody(llhttp_t*, const char*, std::size_t) noexcept;
  static int onMessageComplete(llhttp_t*) noexcept;
  static int onChunkHeader(llhttp_t*) noexcept;
  static int onChunkComplete(llhttp_t*) noexcept;

  int handleUrl(std::string_view bytes);
  int handleHeaderField(std::string_view bytes);
  int handleHeaderValue(std::string_view bytes);
  int handleHeaderValueComplete();
  int handleHeadersComplete();
  int handleBody(std::string_view bytes);
  int handleMessageComplete();
  int handleChunkHeader();
  int handleChunkComplete();
  bool accountByte(char byte);
  llhttp_errno_t deliverByte(char byte) noexcept;
  bool validateHeaders();
  bool selectResponseMode();
  int rejectMessage(unsigned status, const char* code) noexcept;
  ParseResult result(std::size_t consumed) const noexcept;
  std::size_t bodyLimit() const;

  MessageKind kind_;
  ParserLimits limits_;
  ResponseMode responseMode_;

  std::array<char, 16384> bodyFragment_{};
  std::size_t bodyFragmentSize_ = 0;
  std::size_t decodedTotal_ = 0;
  bool finalHeadersReady_ = false;
  bool eventStream_ = false;

  llhttp_settings_t settings_{};
  llhttp_t parser_{};
  HttpMessage message_;
  std::string headerName_;
  std::string headerValue_;
  std::string chunkLine_;

  ParseStatus status_ = ParseStatus::kNeedMore;
  unsigned errorStatus_ = 0;
  const char* errorCode_ = "";
  llhttp_errno_t parserError_ = HPE_OK;
  WirePhase phase_ = WirePhase::kHeaders;
  std::size_t wireBytes_ = 0;
  std::size_t headerBytes_ = 0;
  std::size_t startLineBytes_ = 0;
  std::size_t chunkLineBytes_ = 0;
  std::size_t chunkCount_ = 0;
  std::size_t informationalCount_ = 0;
  std::size_t informationalBytes_ = 0;
  bool startLineComplete_ = false;
  bool startLineStarted_ = false;
  bool headerValueStarted_ = false;
};

std::string lowerAscii(std::string_view input);
std::string trimWhitespace(std::string_view input);
}  // namespace gateway::http
