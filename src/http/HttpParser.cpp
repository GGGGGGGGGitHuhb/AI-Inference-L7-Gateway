#include "http/HttpParser.h"

#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <limits>
#include <set>

namespace gateway::http {
std::string lowerAscii(std::string_view input) {
  std::string output(input);
  for (char& byte : output) {
    if (byte >= 'A' && byte <= 'Z') byte += 'a' - 'A';
  }
  return output;
}

std::string trimWhitespace(std::string_view input) {
  while (!input.empty() && (input.front() == ' ' || input.front() == '\t'))
    input.remove_prefix(1);
  while (!input.empty() && (input.back() == ' ' || input.back() == '\t'))
    input.remove_suffix(1);
  return std::string(input);
}

HttpParser::HttpParser(MessageKind kind, ParserLimits limits)
    : kind_(kind), limits_(limits) {
  llhttp_settings_init(&settings_);
  settings_.on_url = onUrl;
  settings_.on_header_field = onHeaderField;
  settings_.on_header_value = onHeaderValue;
  settings_.on_header_value_complete = onHeaderValueComplete;
  settings_.on_headers_complete = onHeadersComplete;
  settings_.on_body = onBody;
  settings_.on_message_complete = onMessageComplete;
  settings_.on_chunk_header = onChunkHeader;
  settings_.on_chunk_complete = onChunkComplete;
  resetParser();
}

void HttpParser::resetParser() noexcept {
  message_ = {};
  headerName_.clear();
  headerValue_.clear();
  chunkLine_.clear();
  status_ = ParseStatus::kNeedMore;
  errorStatus_ = 0;
  errorCode_ = "";
  parserError_ = HPE_OK;
  phase_ = WirePhase::kHeaders;
  wireBytes_ = headerBytes_ = startLineBytes_ = chunkLineBytes_ = chunkCount_ =
      0;
  informationalCount_ = informationalBytes_ = 0;
  startLineComplete_ = startLineStarted_ = headerValueStarted_ = false;
  llhttp_init(&parser_,
              kind_ == MessageKind::kRequest ? HTTP_REQUEST : HTTP_RESPONSE,
              &settings_);
  parser_.data = this;
}

// 所有 C trampoline 都捕获异常；失败状态不分配内存。
#define GATEWAY_DATA_CALLBACK(Name, Handler)               \
  int HttpParser::Name(llhttp_t* parser, const char* data, \
                       std::size_t size) noexcept {        \
    auto& owner = *static_cast<HttpParser*>(parser->data); \
    try {                                                  \
      return owner.Handler(std::string_view(data, size));  \
    } catch (...) {                                        \
      return owner.rejectMessage(500, "internal_error");   \
    }                                                      \
  }
#define GATEWAY_CALLBACK(Name, Handler)                    \
  int HttpParser::Name(llhttp_t* parser) noexcept {        \
    auto& owner = *static_cast<HttpParser*>(parser->data); \
    try {                                                  \
      return owner.Handler();                              \
    } catch (...) {                                        \
      return owner.rejectMessage(500, "internal_error");   \
    }                                                      \
  }
GATEWAY_DATA_CALLBACK(onUrl, handleUrl)
GATEWAY_DATA_CALLBACK(onHeaderField, handleHeaderField)
GATEWAY_DATA_CALLBACK(onHeaderValue, handleHeaderValue)
GATEWAY_DATA_CALLBACK(onBody, handleBody)
GATEWAY_CALLBACK(onHeaderValueComplete, handleHeaderValueComplete)
GATEWAY_CALLBACK(onHeadersComplete, handleHeadersComplete)
GATEWAY_CALLBACK(onMessageComplete, handleMessageComplete)
GATEWAY_CALLBACK(onChunkHeader, handleChunkHeader)
GATEWAY_CALLBACK(onChunkComplete, handleChunkComplete)
#undef GATEWAY_DATA_CALLBACK
#undef GATEWAY_CALLBACK

int HttpParser::rejectMessage(unsigned status, const char* code) noexcept {
  chunkLine_.clear();
  status_ = ParseStatus::kRejected;
  errorStatus_ = kind_ == MessageKind::kResponse ? 502 : status;
  errorCode_ = code;
  return HPE_USER;
}

ParseResult HttpParser::result(std::size_t consumed) const noexcept {
  return {status_, consumed, errorStatus_, errorCode_, parserError_};
}

std::size_t HttpParser::bodyLimit() const {
  return kind_ == MessageKind::kRequest ? limits_.requestBodyBytes
                                        : limits_.responseBodyBytes;
}

bool HttpParser::accountByte(char byte) {
  const auto wireLimit = kind_ == MessageKind::kRequest
                             ? limits_.requestWireBytes
                             : limits_.responseWireBytes;
  if (++wireBytes_ > wireLimit) {
    rejectMessage(413, "wire_limit");
    return false;
  }
  if (phase_ == WirePhase::kHeaders) {
    if (++headerBytes_ > limits_.headerBytes) {
      rejectMessage(431, "header_limit");
      return false;
    }
    if (!startLineComplete_ &&
        (startLineStarted_ || (byte != '\r' && byte != '\n'))) {
      startLineStarted_ = true;
      if (++startLineBytes_ > limits_.startLineBytes) {
        rejectMessage(431, "start_line_limit");
        return false;
      }
      if (byte == '\n') startLineComplete_ = true;
    }
  }
  if (phase_ == WirePhase::kChunkLine) {
    if (++chunkLineBytes_ > limits_.chunkLineBytes) {
      rejectMessage(413, "chunk_line_limit");
      return false;
    }
    chunkLine_.push_back(byte);
  }
  return true;
}

ParseResult HttpParser::parseBytes(std::string_view input) noexcept {
  if (status_ != ParseStatus::kNeedMore) return result(0);
  std::size_t consumed = 0;
  // 逐字节喂入让预算与消息边界精确对应；S1 不作吞吐承诺。
  for (const char& byte : input) {
    try {
      if (!accountByte(byte)) return result(consumed);
    } catch (...) {
      rejectMessage(500, "internal_error");
      return result(consumed);
    }
    const auto error = deliverByte(byte);
    ++consumed;
    if (error != HPE_OK && error != HPE_PAUSED) {
      parserError_ = error;
      if (status_ != ParseStatus::kRejected) rejectMessage(400, "invalid_http");
    }
    if (status_ != ParseStatus::kNeedMore) return result(consumed);
  }
  return result(consumed);
}

ParseResult HttpParser::finishInput() noexcept {
  if (status_ != ParseStatus::kNeedMore) return result(0);
  const auto error = llhttp_finish(&parser_);
  if (error != HPE_OK && error != HPE_PAUSED) parserError_ = error;
  if (status_ == ParseStatus::kNeedMore) rejectMessage(400, "incomplete_http");
  return result(0);
}

int HttpParser::handleUrl(std::string_view bytes) {
  message_.target.append(bytes);
  return 0;
}

int HttpParser::handleHeaderField(std::string_view bytes) {
  if (phase_ == WirePhase::kTrailers)
    return rejectMessage(400, "unsupported_trailer");
  if (headerValueStarted_) {
    headerName_.clear();
    headerValue_.clear();
    headerValueStarted_ = false;
  }
  headerName_.append(bytes);
  return 0;
}

int HttpParser::handleHeaderValue(std::string_view bytes) {
  headerValue_.append(bytes);
  return 0;
}

int HttpParser::handleHeaderValueComplete() {
  if (phase_ == WirePhase::kTrailers)
    return rejectMessage(400, "unsupported_trailer");
  if (message_.headers.size() >= limits_.headerFields)
    return rejectMessage(431, "header_count_limit");
  message_.headers.push_back(
      {lowerAscii(headerName_), trimWhitespace(headerValue_)});
  headerValueStarted_ = true;
  return 0;
}

bool HttpParser::validateHeaders() {
  std::size_t hostCount = 0, lengthCount = 0, encodingCount = 0;
  bool chunked = false;
  for (const auto& header : message_.headers) {
    const auto value = lowerAscii(header.value);
    if (header.name == "host" && (++hostCount > 1 || value.empty()))
      return rejectMessage(400, "invalid_host"), false;
    if (header.name == "content-length") {
      std::size_t length = 0;
      const auto parsed =
          std::from_chars(value.data(), value.data() + value.size(), length);
      if (++lengthCount > 1 || value.empty() || parsed.ec != std::errc{} ||
          parsed.ptr != value.data() + value.size())
        return rejectMessage(400, "invalid_length"), false;
      if (length > bodyLimit() && message_.statusCode != 304)
        return rejectMessage(413, "body_limit"), false;
    }
    if (header.name == "transfer-encoding") {
      if (++encodingCount > 1 || value != "chunked")
        return rejectMessage(400, "invalid_encoding"), false;
      chunked = true;
    }
    if (header.name == "trailer" && !value.empty())
      return rejectMessage(400, "unsupported_trailer"), false;
    if (header.name == "expect" && kind_ == MessageKind::kRequest)
      return rejectMessage(417, "unsupported_expect"), false;
    if (header.name == "upgrade")
      return rejectMessage(400, "unsupported_upgrade"), false;
    if (header.name == "connection") {
      std::string_view remaining(value);
      do {
        const auto comma = remaining.find(',');
        const auto token = trimWhitespace(remaining.substr(0, comma));
        if (token == "host" || token == "content-length" ||
            token == "content-type" || token == "content-encoding" ||
            token == "transfer-encoding")
          return rejectMessage(400, "invalid_connection"), false;
        if (token.empty() ||
            token.find_first_not_of(
                "!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyz") !=
                std::string::npos)
          return rejectMessage(400, "invalid_connection"), false;
        if (comma == std::string_view::npos) break;
        remaining.remove_prefix(comma + 1);
      } while (true);
    }
    if (header.name == "content-encoding" && value != "identity")
      return rejectMessage(415, "unsupported_encoding"), false;
    if (kind_ == MessageKind::kResponse && header.name == "content-type" &&
        trimWhitespace(std::string_view(value).substr(0, value.find(';'))) ==
            "text/event-stream")
      return rejectMessage(502, "unsupported_stream"), false;
  }
  if (chunked && lengthCount)
    return rejectMessage(400, "ambiguous_length"), false;
  if (kind_ == MessageKind::kRequest) {
    if (hostCount != 1) return rejectMessage(400, "invalid_host"), false;
    if (message_.method == "CONNECT")
      return rejectMessage(400, "unsupported_tunnel"), false;
    if (message_.method == "POST" && !lengthCount && !encodingCount)
      return rejectMessage(411, "length_required"), false;
  }
  if (chunked)
    phase_ = WirePhase::kChunkLine;
  else
    phase_ = WirePhase::kBody;
  message_.eofDelimited =
      kind_ == MessageKind::kResponse && message_.statusCode >= 200 &&
      message_.statusCode != 204 && message_.statusCode != 304 &&
      !lengthCount && !encodingCount;
  return true;
}

int HttpParser::handleHeadersComplete() {
  if (parser_.http_major != 1 || parser_.http_minor != 1)
    return rejectMessage(505, "unsupported_version");
  if (kind_ == MessageKind::kRequest)
    message_.method =
        llhttp_method_name(static_cast<llhttp_method_t>(parser_.method));
  else
    message_.statusCode = parser_.status_code;
  if (kind_ == MessageKind::kResponse &&
      (message_.statusCode < 100 || message_.statusCode > 599))
    return rejectMessage(502, "invalid_status");
  if (message_.statusCode == 101)
    return rejectMessage(502, "unsupported_upgrade");
  if (!validateHeaders()) return HPE_USER;
  return 0;
}

int HttpParser::handleBody(std::string_view bytes) {
  if (bytes.size() > bodyLimit() - message_.body.size())
    return rejectMessage(413, "body_limit");
  message_.body.append(bytes);
  return 0;
}

int HttpParser::handleMessageComplete() {
  if (kind_ == MessageKind::kResponse && message_.statusCode < 200) {
    informationalBytes_ += headerBytes_;
    if (++informationalCount_ > limits_.informationalResponses ||
        informationalBytes_ > limits_.informationalBytes)
      return rejectMessage(502, "informational_limit");
    message_ = {};
    headerName_.clear();
    headerValue_.clear();
    headerValueStarted_ = false;
    headerBytes_ = startLineBytes_ = 0;
    startLineComplete_ = startLineStarted_ = false;
    phase_ = WirePhase::kHeaders;
    return 0;
  }
  status_ = ParseStatus::kComplete;
  return HPE_PAUSED;
}

namespace {
bool isToken(char byte) {
  return std::string_view(
             "!#$%&'*+-.^_`|~"
             "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
             .find(byte) != std::string_view::npos;
}

void skipBadWhitespace(std::string_view line, std::size_t& offset) {
  while (offset < line.size() && (line[offset] == ' ' || line[offset] == '\t'))
    ++offset;
}

bool consumeToken(std::string_view line, std::size_t& offset) {
  const auto beginning = offset;
  while (offset < line.size() && isToken(line[offset])) ++offset;
  return offset != beginning;
}

bool consumeQuotedString(std::string_view line, std::size_t& offset) {
  ++offset;
  while (offset < line.size()) {
    const unsigned char byte = line[offset++];
    if (byte == '"') return true;
    if (byte == '\\') {
      if (offset == line.size()) return false;
      const unsigned char escaped = line[offset++];
      // quoted-pair = "\\" ( HTAB / SP / VCHAR / obs-text )。
      if (escaped != '\t' && (escaped < 32 || escaped == 127)) return false;
    } else if (byte != '\t' && (byte < 32 || byte == 127))
      return false;
  }
  return false;
}

bool validateExtensions(std::string_view line, std::size_t offset) {
  while (offset < line.size()) {
    skipBadWhitespace(line, offset);
    if (offset == line.size() || line[offset++] != ';') return false;
    skipBadWhitespace(line, offset);
    if (!consumeToken(line, offset)) return false;
    auto equalsOffset = offset;
    skipBadWhitespace(line, equalsOffset);
    if (equalsOffset < line.size() && line[equalsOffset] == '=') {
      offset = equalsOffset + 1;
      skipBadWhitespace(line, offset);
      if (offset == line.size()) return false;
      if (line[offset] == '"') {
        if (!consumeQuotedString(line, offset)) return false;
      } else if (!consumeToken(line, offset))
        return false;
    }
    // 不跳过尾部空白：它必须归属下一扩展的分号，否则整行非法。
  }
  return true;
}

bool decodeChunkLine(std::string_view line, std::uint64_t& chunkSize) {
  if (!line.ends_with("\r\n")) return false;
  line.remove_suffix(2);
  std::size_t digits = 0;
  while (digits < line.size() &&
         std::string_view("0123456789abcdefABCDEF").find(line[digits]) !=
             std::string_view::npos)
    ++digits;
  if (!digits) return false;
  const auto decoded =
      std::from_chars(line.data(), line.data() + digits, chunkSize, 16);
  if (decoded.ec != std::errc{} || decoded.ptr != line.data() + digits)
    return false;
  return validateExtensions(line, digits);
}
}  // namespace

llhttp_errno_t HttpParser::deliverByte(char byte) noexcept {
  if (phase_ != WirePhase::kChunkLine)
    return llhttp_execute(&parser_, &byte, 1);
  if (byte != '\n') return HPE_OK;
  std::uint64_t chunkSize = 0;
  if (!decodeChunkLine(chunkLine_, chunkSize)) {
    rejectMessage(400, "invalid_chunk_line");
    return HPE_USER;
  }
  // 独立栈存储不受 llhttp 同步回调清空 chunkLine_ 的影响。
  // 内部编码不进入原始 wire/行预算；16 个 hex 字符加 CRLF。
  std::array<char, 18> canonicalLine{};
  auto encoded = std::to_chars(canonicalLine.data(), canonicalLine.data() + 16,
                               chunkSize, 16);
  *encoded.ptr++ = '\r';
  *encoded.ptr++ = '\n';
  chunkLine_.clear();
  return llhttp_execute(&parser_, canonicalLine.data(),
                        encoded.ptr - canonicalLine.data());
}

int HttpParser::handleChunkHeader() {
  if (parser_.content_length != 0 && ++chunkCount_ > limits_.chunks)
    return rejectMessage(413, "chunk_count_limit");
  if (parser_.content_length > bodyLimit() - message_.body.size())
    return rejectMessage(413, "body_limit");
  phase_ = parser_.content_length == 0 ? WirePhase::kTrailers
                                       : WirePhase::kChunkData;
  chunkLineBytes_ = 0;
  return 0;
}

int HttpParser::handleChunkComplete() {
  phase_ = WirePhase::kChunkLine;
  chunkLineBytes_ = 0;
  return 0;
}
}  // namespace gateway::http
