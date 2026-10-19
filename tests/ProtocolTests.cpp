#include <charconv>
#include <cstdlib>
#include <new>
#include <random>

#include "TestSupport.h"
#include "gateway/TextRequest.h"
#include "http/HttpNormalization.h"
#include "http/HttpParser.h"

// 故障注入仅在测试可执行文件中替换分配器，不改变产品接口。
namespace {
bool failAllocation = false;
}

void* operator new(std::size_t size) {
  if (failAllocation) {
    failAllocation = false;
    throw std::bad_alloc();
  }
  if (void* memory = std::malloc(size ? size : 1)) return memory;
  throw std::bad_alloc();
}

void operator delete(void* memory) noexcept { std::free(memory); }

void operator delete(void* memory, std::size_t) noexcept { std::free(memory); }

void* operator new[](std::size_t size) { return ::operator new(size); }

void operator delete[](void* memory) noexcept { ::operator delete(memory); }

void operator delete[](void* memory, std::size_t) noexcept {
  ::operator delete(memory);
}

using namespace gateway::http;
using namespace gateway::gateway_api;
namespace {
const std::string kBody =
    R"({"model":"demo","messages":[{"role":"user","content":"hello"}]})";

std::string request(std::string body = kBody, std::string headers = "") {
  return "POST /v1/chat/completions HTTP/1.1\r\nHost: "
         "localhost\r\nContent-Type: application/json\r\nContent-Length: " +
         std::to_string(body.size()) + "\r\n" + headers + "\r\n" + body;
}

ParseResult parse(HttpParser& parser, const std::string& wire) {
  auto outcome = parser.parseBytes(wire);
  if (outcome.status == ParseStatus::kNeedMore) {
    auto finished = parser.finishInput();
    finished.consumedBytes = outcome.consumedBytes;
    return finished;
  }
  return outcome;
}

void expectReject(const std::string& wire, MessageKind kind, unsigned status) {
  HttpParser parser(kind);
  auto outcome = parse(parser, wire);
  if (outcome.status != ParseStatus::kRejected || outcome.errorStatus != status)
    std::cerr << "Unexpected rejection for " << wire.substr(0, 160)
              << " status " << outcome.errorStatus << " code "
              << outcome.errorCode << '\n';
  GATEWAY_CHECK(outcome.status == ParseStatus::kRejected &&
                outcome.errorStatus == status);
  GATEWAY_CHECK(parser.parseBytes(request()).consumedBytes == 0);
}

void verifyMessage(HttpParser& parser, const std::string& body,
                   unsigned status) {
  GATEWAY_CHECK(parser.message().body == body);
  GATEWAY_CHECK(parser.message().statusCode == status);
}

void splitFixture(const std::string& wire, MessageKind kind,
                  const std::string& body, unsigned status = 0,
                  bool eof = false) {
  HttpParser baseline(kind);
  GATEWAY_CHECK(parse(baseline, wire).status == ParseStatus::kComplete);
  const auto normalized =
      normalizeMessage(baseline.message(), kind, "backend:80");
  for (std::size_t split = 0; split <= wire.size(); ++split) {
    HttpParser parser(kind);
    auto first = parser.parseBytes(std::string_view(wire).substr(0, split));
    auto second = parser.parseBytes(std::string_view(wire).substr(split));
    auto final = eof ? parser.finishInput() : second;
    if (first.status == ParseStatus::kComplete) final = first;
    GATEWAY_CHECK(final.status == ParseStatus::kComplete);
    GATEWAY_CHECK(first.consumedBytes + second.consumedBytes == wire.size());
    verifyMessage(parser, body, status);
    GATEWAY_CHECK(normalizeMessage(parser.message(), kind, "backend:80") ==
                  normalized);
  }
  HttpParser parser(kind);
  for (char byte : wire) parser.parseBytes(std::string_view(&byte, 1));
  GATEWAY_CHECK(parser.finishInput().status == ParseStatus::kComplete);
  verifyMessage(parser, body, status);
  std::mt19937 generator(20261018);
  parser.resetParser();
  for (std::size_t offset = 0; offset < wire.size();) {
    auto length =
        std::min(wire.size() - offset, std::size_t(generator() % 17 + 1));
    GATEWAY_CHECK(
        parser.parseBytes(std::string_view(wire).substr(offset, length))
            .consumedBytes == length);
    offset += length;
  }
  GATEWAY_CHECK(parser.finishInput().status == ParseStatus::kComplete);
  verifyMessage(parser, body, status);
  if (!eof) {
    parser.resetParser();
    auto outcome = parser.parseBytes(wire + wire);
    GATEWAY_CHECK(outcome.status == ParseStatus::kComplete &&
                  outcome.consumedBytes == wire.size());
  }
}

void testFraming() {
  splitFixture(request(), MessageKind::kRequest, kBody);
  splitFixture(
      "POST /v1/chat/completions HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: "
      "ChUnKeD\r\nContent-Type: "
      "application/json\r\n\r\n2;x=\"y\"\r\n{}\r\n0\r\n\r\n",
      MessageKind::kRequest, "{}");
  splitFixture(
      "HTTP/1.1 200 OK\r\nContent-Length: 3\r\nX-A: 1\r\nX-A: 2\r\n\r\nabc",
      MessageKind::kResponse, "abc", 200);
  splitFixture(
      "HTTP/1.1 500 Error\r\nTransfer-Encoding: "
      "chunked\r\n\r\n1\r\na\r\n2\r\nbc\r\n0\r\n\r\n",
      MessageKind::kResponse, "abc", 500);
  splitFixture("HTTP/1.1 204 Empty\r\n\r\n", MessageKind::kResponse, "", 204);
  splitFixture("HTTP/1.1 304 Same\r\nContent-Length: 10\r\n\r\n",
               MessageKind::kResponse, "", 304);
  splitFixture(
      "HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 103 Early Hints\r\nLink: "
      "</a>\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n",
      MessageKind::kResponse, "", 200);
  splitFixture("HTTP/1.1 404 Missing\r\n\r\nabc", MessageKind::kResponse, "abc",
               404, true);
  for (const auto& header :
       {"Transfer-Encoding: chunked\r\n", "Content-Length: 1\r\n",
        "Content-Length: 1, 1\r\n", "Host: duplicate\r\n", "Trailer: X-End\r\n",
        "Upgrade: websocket\r\n", "Connection: Content-Length\r\n",
        "Connection: Host\r\n", "Connection: Content-Type\r\n",
        "Connection: Content-Encoding\r\n", "Bad Name: x\r\n",
        "X-Test: a\r\n continued\r\n", "X-Test: x\nInjected: x\r\n"})
    expectReject(request(kBody, header), MessageKind::kRequest, 400);
  expectReject(request(kBody, "Expect: 100-continue\r\n"),
               MessageKind::kRequest, 417);
  expectReject(request(kBody, "Content-Encoding: gzip\r\n"),
               MessageKind::kRequest, 415);
  expectReject("POST / HTTP/1.1\r\nHost: h\r\n\r\n", MessageKind::kRequest,
               411);
  expectReject("GET / HTTP/1.1\r\n\r\n", MessageKind::kRequest, 400);
  expectReject("GET / HTTP/1.1\r\nHost: \r\n\r\n", MessageKind::kRequest, 400);
  expectReject("GET / HTTP/1.0\r\nHost: h\r\n\r\n", MessageKind::kRequest, 505);
  expectReject("CONNECT host:80 HTTP/1.1\r\nHost: h\r\n\r\n",
               MessageKind::kRequest, 400);
  for (const auto& value : {"", "gzip", "chunked, chunked",
                            "chunked\r\nTransfer-Encoding: chunked"})
    expectReject("POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: " +
                     std::string(value) + "\r\n\r\n0\r\n\r\n",
                 MessageKind::kRequest, 400);
  expectReject(
      "POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: "
      "chunked\r\n\r\n0\r\nX-End: x\r\n\r\n",
      MessageKind::kRequest, 400);
  for (const auto& tail :
       {"3\r\nab", "0\r\n", "q\r\n", "1;=x\r\na\r\n0\r\n\r\n"})
    expectReject("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" +
                     std::string(tail),
                 MessageKind::kResponse, 502);
  for (const auto& response :
       {"HTTP/1.1 101 Switching\r\n\r\n", "HTTP/1.0 200 OK\r\n\r\n",
        "HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nabc",
        "HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n\r\n",
        "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream; "
        "charset=utf-8\r\n\r\n",
        "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\nab"})
    expectReject(response, MessageKind::kResponse, 502);
}

ValidationResult validateBody(std::string body, JsonLimits limits = {}) {
  HttpParser parser(MessageKind::kRequest);
  GATEWAY_CHECK(parse(parser, request(std::move(body))).status ==
                ParseStatus::kComplete);
  return validateTextRequest(parser.message(), limits);
}

void testJson() {
  auto valid = validateBody(kBody);
  GATEWAY_CHECK(valid.accepted && valid.metadata.model == "demo" &&
                valid.metadata.messageCount == 1);
  GATEWAY_CHECK(!valid.metadata.stream);
  GATEWAY_CHECK(
      validateBody(kBody.substr(0, kBody.size() - 1) + ",\"stream\":true}")
          .metadata.stream);
  for (const auto& field :
       {"\"stream\":false", "\"stream\":true", "\"n\":1", "\"max_tokens\":1",
        "\"max_tokens\":8192", "\"temperature\":0", "\"temperature\":2",
        "\"temperature\":1.5"})
    GATEWAY_CHECK(
        validateBody(kBody.substr(0, kBody.size() - 1) + "," + field + "}")
            .accepted);
  for (const auto& field :
       {"\"stream\":0", "\"n\":2", "\"n\":0", "\"n\":1.0", "\"max_tokens\":0",
        "\"max_tokens\":8193", "\"max_tokens\":1.0", "\"temperature\":-1",
        "\"temperature\":2.1", "\"temperature\":\"1\"", "\"tools\":[]",
        "\"n\":null", "\"n\":true", "\"n\":[]"})
    GATEWAY_CHECK(
        !validateBody(kBody.substr(0, kBody.size() - 1) + "," + field + "}")
             .accepted);
  for (const auto& body :
       {"{}", "[]", "null", "{bad}",
        "{\"model\":\"x\",\"model\":\"y\",\"messages\":[]}",
        "{\"model\":1,\"messages\":[]}", "{\"model\":\"\",\"messages\":[]}",
        "{\"model\":\"x\",\"messages\":[{}]}",
        "{\"model\":\"x\",\"messages\":[{\"role\":\"tool\",\"content\":\"x\"}]"
        "}",
        "{\"model\":\"x\",\"messages\":[{\"role\":\"user\",\"content\":3}]}",
        "{\"model\":\"x\",\"messages\":[{\"role\":\"user\",\"content\":\"a\","
        "\"content\":\"b\"}]}"})
    GATEWAY_CHECK(!validateBody(body).accepted);
  GATEWAY_CHECK(!validateBody(kBody + "x").accepted);
  GATEWAY_CHECK(!validateBody("/*comment*/" + kBody).accepted);
  GATEWAY_CHECK(!validateBody("{\"model\":\"\xff\",\"messages\":[]}").accepted);
  for (std::size_t size : {255, 256, 257})
    GATEWAY_CHECK(
        validateBody(
            "{\"model\":\"" + std::string(size, 'm') +
            "\",\"messages\":[{\"role\":\"system\",\"content\":\"\"}]}")
            .accepted == (size <= 256));
  for (std::size_t count : {0, 1, 255, 256, 257}) {
    std::string body = "{\"model\":\"m\",\"messages\":[";
    for (std::size_t index = 0; index < count; ++index) {
      if (index) body += ",";
      body += "{\"role\":\"assistant\",\"content\":\"\"}";
    }
    body += "]}";
    GATEWAY_CHECK(validateBody(body).accepted == (count >= 1 && count <= 256));
  }
  // 合法 API 的自然最大深度为 3；用收紧预算验证等于上限允许。
  GATEWAY_CHECK(!validateBody(kBody, {2, 8192}).accepted);
  GATEWAY_CHECK(validateBody(kBody, {3, 8192}).accepted);
  GATEWAY_CHECK(validateBody(kBody, {4, 8192}).accepted);
  // 两个根键、一个数组元素、两个 message 键，共 5 项。
  GATEWAY_CHECK(!validateBody(kBody, {32, 4}).accepted);
  GATEWAY_CHECK(validateBody(kBody, {32, 5}).accepted);
  GATEWAY_CHECK(validateBody(kBody, {32, 6}).accepted);
  for (std::size_t depth : {31, 32, 33}) {
    auto body = kBody.substr(0, kBody.size() - 1) +
                ",\"extra\":" + std::string(depth - 1, '[') + "0" +
                std::string(depth - 1, ']') + "}";
    const auto outcome = validateBody(body);
    GATEWAY_CHECK(!outcome.accepted);
    GATEWAY_CHECK(std::string(outcome.errorCode) ==
                  (depth <= 32 ? "unsupported_field" : "invalid_request"));
  }
  for (std::size_t items : {8191, 8192, 8193}) {
    std::string body =
        "{\"model\":\"m\",\"messages\":[{\"role\":\"user\",\"content\":\"\"}],"
        "\"extra\":[";
    for (std::size_t index = 0; index < items - 6; ++index) {
      if (index) body += ",";
      body += "0";
    }
    body += "]}";
    auto outcome = validateBody(body);
    GATEWAY_CHECK(!outcome.accepted);
    GATEWAY_CHECK(std::string(outcome.errorCode) ==
                  (items <= 8192 ? "unsupported_field" : "invalid_request"));
  }
  HttpParser parser(MessageKind::kRequest);
  parse(parser, request());
  auto message = parser.message();
  message.target = "/other";
  GATEWAY_CHECK(validateTextRequest(message).errorStatus == 404);
  message.target = "/v1/chat/completions?x=1";
  GATEWAY_CHECK(validateTextRequest(message).errorStatus == 404);
  message.target = "/v1/chat/completions";
  message.method = "GET";
  GATEWAY_CHECK(validateTextRequest(message).errorStatus == 405);
  message.method = "POST";
  message.headers[1].value = "text/plain";
  GATEWAY_CHECK(validateTextRequest(message).errorStatus == 415);
  message.headers[1].value = "application/json; charset=UTF-8";
  GATEWAY_CHECK(validateTextRequest(message).accepted);
  message.headers[1].value = "application/json; charset=latin1";
  GATEWAY_CHECK(validateTextRequest(message).errorStatus == 415);
}

void testFieldTypes() {
  const std::vector<std::string> values{"null", "true",  "false", "0", "1",
                                        "1.0",  "\"x\"", "[]",    "{}"};
  for (const auto& field :
       {"model", "messages", "stream", "n", "max_tokens", "temperature"}) {
    for (const auto& value : values) {
      std::string body = "{";
      if (std::string(field) != "model") body += "\"model\":\"demo\",";
      if (std::string(field) != "messages")
        body += "\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],";
      body += "\"" + std::string(field) + "\":" + value + "}";
      bool expected = false;
      if (std::string(field) == "model") expected = value == "\"x\"";
      if (std::string(field) == "stream")
        expected = value == "false" || value == "true";
      if (std::string(field) == "n" || std::string(field) == "max_tokens")
        expected = value == "1";
      if (std::string(field) == "temperature")
        expected = value == "0" || value == "1" || value == "1.0";
      GATEWAY_CHECK(validateBody(body).accepted == expected);
    }
  }
  for (const auto& value : values) {
    const auto body =
        "{\"model\":\"m\",\"messages\":[{\"role\":\"user\",\"content\":" +
        value + "}]}";
    GATEWAY_CHECK(validateBody(body).accepted == (value == "\"x\""));
  }
  for (const auto& role : {"system", "user", "assistant"})
    GATEWAY_CHECK(validateBody("{\"model\":\"m\",\"messages\":[{\"role\":\"" +
                               std::string(role) + "\",\"content\":\"\"}]}")
                      .accepted);
  for (const auto& value :
       {"NaN", "Infinity", "1e1000", "18446744073709551615"})
    GATEWAY_CHECK(!validateBody(kBody.substr(0, kBody.size() - 1) +
                                ",\"temperature\":" + value + "}")
                       .accepted);
  for (const auto& header :
       {"Content-Length: -1\r\n", "Content-Length: +1\r\n",
        "Content-Length: \r\n", "Content-Length: 1,1\r\n",
        "Content-Length: 1\r\nContent-Length: 1\r\n", "Transfer-Encoding: \r\n",
        "Transfer-Encoding: gzip\r\n",
        "Transfer-Encoding: chunked, chunked\r\n",
        "Transfer-Encoding: chunked\r\nContent-Length: 0\r\n", "Trailer: X\r\n",
        "Connection: Content-Type\r\n", "Upgrade: websocket\r\n"})
    expectReject("HTTP/1.1 200 OK\r\n" + std::string(header) + "\r\n",
                 MessageKind::kResponse, 502);
  splitFixture(
      "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nTrailer: "
      "\r\n\r\n1;foo=\"a\\b\";bar=token\r\nx\r\n0\r\n\r\n",
      MessageKind::kResponse, "x", 200);
  // Expect 必须在尚未收到声明正文时拒绝。
  HttpParser parser(MessageKind::kRequest);
  auto outcome = parser.parseBytes(
      "POST / HTTP/1.1\r\nHost: h\r\nExpect: 100-continue\r\nContent-Length: "
      "100\r\n\r\n");
  GATEWAY_CHECK(outcome.status == ParseStatus::kRejected &&
                outcome.errorStatus == 417);
}

void testNormalization() {
  auto wire = request(
      " \n" + kBody + " \t",
      "Authorization: secret\r\nConnection: X-Hop, close\r\nX-Hop: "
      "remove\r\nX-Stay: one\r\nX-Stay: two\r\nVia: 1.1 "
      "prior\r\nProxy-Authorization: secret\r\nKeep-Alive: timeout=5\r\n");
  HttpParser parser(MessageKind::kRequest);
  GATEWAY_CHECK(parse(parser, wire).status == ParseStatus::kComplete);
  GATEWAY_CHECK(validateTextRequest(parser.message()).accepted);
  auto normalized =
      normalizeMessage(parser.message(), MessageKind::kRequest, "backend:8000");
  GATEWAY_CHECK(normalized.find("secret") == std::string::npos &&
                normalized.find("x-hop") == std::string::npos);
  GATEWAY_CHECK(normalized.find("Host: backend:8000") != std::string::npos);
  GATEWAY_CHECK(normalized.find("x-stay: one\r\nx-stay: two") !=
                std::string::npos);
  GATEWAY_CHECK(normalized.find("via: 1.1 prior") != std::string::npos);
  GATEWAY_CHECK(normalized.ends_with(" \n" + kBody + " \t"));
  bool rejected = false;
  try {
    normalizeMessage(parser.message(), MessageKind::kRequest,
                     "bad\r\nInjected: yes");
  } catch (const std::invalid_argument&) {
    rejected = true;
  }
  GATEWAY_CHECK(rejected);
  GATEWAY_CHECK(
      serializeError(405, errorBody({false, 405, "method_not_allowed", {}}))
          .find("Allow: POST") != std::string::npos);
}

void boundary(const std::string& wire, MessageKind kind, ParserLimits limits,
              bool accepted) {
  HttpParser parser(kind, limits);
  auto outcome = parse(parser, wire);
  GATEWAY_CHECK((outcome.status == ParseStatus::kComplete) == accepted);
}

void testBudgets() {
  const std::string shortRequest = "GET / HTTP/1.1\r\nHost: h\r\n\r\n";
  for (int delta : {-1, 0, 1}) {
    ParserLimits limits;
    limits.startLineBytes = 16 + delta;
    boundary(shortRequest, MessageKind::kRequest, limits, delta >= 0);
    limits = {};
    limits.headerBytes = shortRequest.size() + delta;
    boundary(shortRequest, MessageKind::kRequest, limits, delta >= 0);
    limits = {};
    limits.headerFields = 1 + delta;
    boundary(shortRequest, MessageKind::kRequest, limits, delta >= 0);
    limits = {};
    limits.requestWireBytes = shortRequest.size() + delta;
    boundary(shortRequest, MessageKind::kRequest, limits, delta >= 0);
    limits = {};
    limits.requestBodyBytes = kBody.size() + delta;
    boundary(request(), MessageKind::kRequest, limits, delta >= 0);
    const std::string response =
        "HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc";
    limits = {};
    limits.responseBodyBytes = 3 + delta;
    boundary(response, MessageKind::kResponse, limits, delta >= 0);
    limits = {};
    limits.responseWireBytes = response.size() + delta;
    boundary(response, MessageKind::kResponse, limits, delta >= 0);
    const std::string chunked =
        "HTTP/1.1 200 OK\r\nTransfer-Encoding: "
        "chunked\r\n\r\n1\r\nx\r\n0\r\n\r\n";
    limits = {};
    limits.chunkLineBytes = 3 + delta;
    boundary(chunked, MessageKind::kResponse, limits, delta >= 0);
    limits = {};
    limits.chunks = 1 + delta;
    boundary(chunked, MessageKind::kResponse, limits, delta >= 0);
    const std::string info = "HTTP/1.1 103 Hints\r\n\r\n";
    const std::string final = "HTTP/1.1 204 Empty\r\n\r\n";
    limits = {};
    limits.informationalResponses = 1 + delta;
    boundary(info + final, MessageKind::kResponse, limits, delta >= 0);
    limits = {};
    limits.informationalBytes = info.size() + delta;
    boundary(info + final, MessageKind::kResponse, limits, delta >= 0);
  }
  for (std::size_t count : {7, 8, 9}) {
    std::string wire;
    for (std::size_t index = 0; index < count; ++index)
      wire += "HTTP/1.1 100 Continue\r\n\r\n";
    wire += "HTTP/1.1 204 Empty\r\n\r\n";
    boundary(wire, MessageKind::kResponse, {}, count <= 8);
  }
  for (std::size_t size : {1048575, 1048576, 1048577})
    boundary(request(std::string(size, 'x')), MessageKind::kRequest, {},
             size <= 1048576);
  for (std::size_t size : {4194303, 4194304, 4194305})
    boundary("HTTP/1.1 200 OK\r\nContent-Length: " + std::to_string(size) +
                 "\r\n\r\n" + std::string(size, 'x'),
             MessageKind::kResponse, {}, size <= 4194304);
  for (std::size_t count : {65535, 65536, 65537}) {
    std::string wire = "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n";
    for (std::size_t index = 0; index < count; ++index) wire += "1\r\nx\r\n";
    wire += "0\r\n\r\n";
    boundary(wire, MessageKind::kResponse, {}, count <= 65536);
  }
}

std::string paddedHeaders(std::size_t size, const std::string& start) {
  const std::string suffix = "X-Padding: ";
  return start + suffix +
         std::string(size - start.size() - suffix.size() - 4, 'a') + "\r\n\r\n";
}

std::string overheadWire(std::size_t size, MessageKind kind) {
  std::string wire =
      kind == MessageKind::kRequest
          ? "POST / HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n"
          : "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n";
  while (size - wire.size() - 5 > 1030)
    wire += "1;x=" + std::string(1018, 'a') + "\r\nx\r\n";
  const auto remaining = size - wire.size() - 5;
  if (remaining >= 9)
    wire += "1;x=" + std::string(remaining - 9, 'a') + "\r\nx\r\n";
  else
    throw std::logic_error("wire fixture remainder");
  return wire + "0\r\n\r\n";
}

void testDefaultBudgets() {
  for (int delta : {-1, 0, 1}) {
    auto size = static_cast<std::size_t>(4096 + delta);
    const std::string start =
        "GET /" + std::string(size - 16, 'a') + " HTTP/1.1\r\n";
    GATEWAY_CHECK(start.size() == size);
    boundary(start + "Host: h\r\n\r\n", MessageKind::kRequest, {}, delta <= 0);
    boundary("\r\n" + start + "Host: h\r\n\r\n", MessageKind::kRequest, {},
             delta <= 0);
    size = 16384 + delta;
    auto wire = paddedHeaders(size, "GET / HTTP/1.1\r\nHost: h\r\n");
    GATEWAY_CHECK(wire.size() == size);
    boundary(wire, MessageKind::kRequest, {}, delta <= 0);
    wire = "GET / HTTP/1.1\r\nHost: h\r\n";
    for (int count = 1; count < 100 + delta; ++count) wire += "X: y\r\n";
    boundary(wire + "\r\n", MessageKind::kRequest, {}, delta <= 0);
    wire = "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1;x=" +
           std::string(1024 + delta - 6, 'a') + "\r\nx\r\n0\r\n\r\n";
    boundary(wire, MessageKind::kResponse, {}, delta <= 0);
    wire.clear();
    for (int count = 0; count < 8; ++count)
      wire += paddedHeaders(16384 - (count == 7 && delta < 0 ? 1 : 0),
                            "HTTP/1.1 103 Hints\r\n");
    // 8 * 16KiB 已等于累计默认上限；上限+1 需单独提高每组上限来隔离累计判定。
    if (delta > 0)
      wire =
          paddedHeaders(16385, "HTTP/1.1 103 Hints\r\n") + wire.substr(16384);
    ParserLimits limits;
    if (delta > 0) limits.headerBytes = 16385;
    boundary(wire + "HTTP/1.1 204 Empty\r\n\r\n", MessageKind::kResponse,
             limits, delta <= 0);
    for (auto kind : {MessageKind::kRequest, MessageKind::kResponse}) {
      size = (kind == MessageKind::kRequest ? 4194304 : 8388608) + delta;
      wire = overheadWire(size, kind);
      GATEWAY_CHECK(wire.size() == size);
      boundary(wire, kind, {}, delta <= 0);
    }
  }
}

std::string chunkPrefix(MessageKind kind) {
  if (kind == MessageKind::kRequest)
    return "POST /v1/chat/completions HTTP/1.1\r\nHost: h\r\nContent-Type: "
           "application/json\r\nTransfer-Encoding: chunked\r\n\r\n";
  return "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n";
}

std::string hexSize(std::size_t size) {
  char digits[32];
  auto encoded = std::to_chars(digits, digits + sizeof(digits), size, 16);
  return std::string(digits, encoded.ptr);
}

void rejectedSplits(const std::string& wire, MessageKind kind,
                    unsigned errorStatus, ParserLimits limits = {}) {
  HttpParser baseline(kind, limits);
  const auto expected = parse(baseline, wire);
  GATEWAY_CHECK(expected.status == ParseStatus::kRejected);
  GATEWAY_CHECK(expected.errorStatus == errorStatus);
  for (std::size_t split = 0; split <= wire.size(); ++split) {
    HttpParser parser(kind, limits);
    const auto first =
        parser.parseBytes(std::string_view(wire).substr(0, split));
    auto last = parser.parseBytes(std::string_view(wire).substr(split));
    const auto consumed = first.consumedBytes + last.consumedBytes;
    if (last.status == ParseStatus::kNeedMore) last = parser.finishInput();
    GATEWAY_CHECK(last.status == ParseStatus::kRejected);
    GATEWAY_CHECK(last.errorStatus == expected.errorStatus);
    GATEWAY_CHECK(std::string_view(last.errorCode) == expected.errorCode);
    GATEWAY_CHECK(consumed == expected.consumedBytes);
    GATEWAY_CHECK(parser.parseBytes(request()).consumedBytes == 0);
  }
}

void testResponseStatusRework() {
  for (const auto* status : {"000", "099", "600", "999"}) {
    const auto wire = "HTTP/1.1 " + std::string(status) +
                      " Unknown\r\nContent-Length: 0\r\n\r\n";
    rejectedSplits(wire, MessageKind::kResponse, 502);
    HttpParser parser(MessageKind::kResponse);
    GATEWAY_CHECK(parse(parser, wire).status == ParseStatus::kRejected);
    parser.resetParser();
    GATEWAY_CHECK(
        parse(parser, "HTTP/1.1 599 Unknown\r\nContent-Length: 0\r\n\r\n")
            .status == ParseStatus::kComplete);
    GATEWAY_CHECK(parser.message().statusCode == 599);
  }
  for (unsigned status : {299, 471, 599})
    splitFixture("HTTP/1.1 " + std::to_string(status) +
                     " Unknown\r\nContent-Length: 0\r\n\r\n",
                 MessageKind::kResponse, "", status);
  splitFixture(
      "HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 599 Unknown\r\nContent-Length: "
      "0\r\n\r\n",
      MessageKind::kResponse, "", 599);
  rejectedSplits("HTTP/1.1 101 Switching\r\n\r\n", MessageKind::kResponse, 502);
  rejectedSplits("HTTP/1.1 100 Continue\r\n\r\n", MessageKind::kResponse, 502);
}

void testChunkExtensionsRework() {
  const std::vector<std::string> valid{"",
                                       ";foo",
                                       ";foo=bar",
                                       ";foo = bar",
                                       ";foo=\"x\" ;bar=y",
                                       " \t; \tfoo\t =\t bar\t ;\t next",
                                       ";foo=\"\"",
                                       ";foo=\"x ; = y\"",
                                       ";foo=\"a\\\"b\\\\c\";bar",
                                       ";foo=\"\t \x80\xff\"",
                                       ";foo=\"\\\x80\\\xff\\\t\""};
  for (auto kind : {MessageKind::kRequest, MessageKind::kResponse}) {
    const auto body =
        kind == MessageKind::kRequest ? kBody : "1;body = data\r\n";
    for (const auto& extension : valid) {
      const auto wire = chunkPrefix(kind) + hexSize(body.size()) + extension +
                        "\r\n" + body + "\r\n0" + extension + "\r\n\r\n";
      splitFixture(wire, kind, body, kind == MessageKind::kResponse ? 200 : 0);
      if (kind == MessageKind::kRequest) {
        HttpParser parser(kind);
        GATEWAY_CHECK(parse(parser, wire).status == ParseStatus::kComplete);
        GATEWAY_CHECK(validateTextRequest(parser.message()).accepted);
      }
    }
    const auto wire =
        chunkPrefix(kind) +
        "1;foo = bar\r\na\r\n1;foo=\"x\" ;bar=y\r\nb\r\n000;last\r\n\r\n";
    splitFixture(wire, kind, "ab", kind == MessageKind::kResponse ? 200 : 0);
  }
  std::vector<std::string> invalid{"\r\n",
                                   "+1\r\n",
                                   "-1\r\n",
                                   "0x1\r\n",
                                   "g\r\n",
                                   " 1\r\n",
                                   "10000000000000000\r\n",
                                   "1 \r\n",
                                   "1\t\r\n",
                                   "1;\r\n",
                                   "1; =x\r\n",
                                   "1;foo=\r\n",
                                   "1;foo= \r\n",
                                   "1;foo=bar \r\n",
                                   "1;foo \r\n",
                                   "1;foo=\"x\" \r\n",
                                   "1;foo=\"x\"suffix\r\n",
                                   "1;foo=\"unterminated\r\n",
                                   "1;foo=\"escape\\\r\n",
                                   "1;foo=\"\x7f\"\r\n",
                                   "1;foo=\"\x01\"\r\n",
                                   "1;foo=\"\\\x7f\"\r\n",
                                   "1;foo=\"\\\x01\"\r\n",
                                   "1;fo(o=x\r\n",
                                   "1;foo=\x80\r\n",
                                   "1\n",
                                   "1\rx\n",
                                   "1;foo=bar\r",
                                   "1;foo=bar"};
  invalid.push_back(std::string("1;foo=\"") + char(0) + "\"\r\n");
  for (auto kind : {MessageKind::kRequest, MessageKind::kResponse}) {
    for (const auto& line : invalid) {
      // 不附加正文以保留被截断大小行的 EOF 边界。
      rejectedSplits(chunkPrefix(kind) + line, kind,
                     kind == MessageKind::kRequest ? 400 : 502);
      if (!line.empty() && line.front() == '1') {
        auto terminal = line;
        terminal.front() = '0';
        rejectedSplits(chunkPrefix(kind) + terminal, kind,
                       kind == MessageKind::kRequest ? 400 : 502);
      }
    }
    rejectedSplits(chunkPrefix(kind) + "1;ok\r\nxX\n0\r\n\r\n", kind,
                   kind == MessageKind::kRequest ? 400 : 502);
  }
}

void testChunkAdapterBudgets() {
  for (auto kind : {MessageKind::kRequest, MessageKind::kResponse}) {
    const auto line = "1;foo = \"" + std::string(40, 'x') + "\" ;bar=y\r\n";
    const auto wire = chunkPrefix(kind) + line + "x\r\n0;last = yes\r\n\r\n";
    for (int delta : {-1, 0, 1}) {
      ParserLimits limits;
      limits.chunkLineBytes = line.size() + delta;
      boundary(wire, kind, limits, delta >= 0);
      if (delta < 0)
        rejectedSplits(wire, kind, kind == MessageKind::kRequest ? 413 : 502,
                       limits);
      limits = {};
      if (kind == MessageKind::kRequest)
        limits.requestWireBytes = wire.size() + delta;
      else
        limits.responseWireBytes = wire.size() + delta;
      boundary(wire, kind, limits, delta >= 0);
      if (delta < 0)
        rejectedSplits(wire, kind, kind == MessageKind::kRequest ? 413 : 502,
                       limits);
    }
    HttpParser parser(kind);
    const auto prefix = chunkPrefix(kind);
    GATEWAY_CHECK(parser.parseBytes(prefix).consumedBytes == prefix.size());
    for (char byte : line)
      GATEWAY_CHECK(
          parser.parseBytes(std::string_view(&byte, 1)).consumedBytes == 1);
    GATEWAY_CHECK(parser.parseBytes("x\r\n0;last").consumedBytes == 9);
    GATEWAY_CHECK(parser.finishInput().status == ParseStatus::kRejected);
    parser.resetParser();
    GATEWAY_CHECK(parse(parser, wire).status == ParseStatus::kComplete);

    HttpParser allocationParser(kind);
    allocationParser.parseBytes(prefix);
    const auto longLine = "1;foo=" + std::string(100, 'x');
    failAllocation = true;
    const auto rejected = allocationParser.parseBytes(longLine);
    failAllocation = false;
    GATEWAY_CHECK(rejected.status == ParseStatus::kRejected);
    GATEWAY_CHECK(rejected.errorStatus ==
                  (kind == MessageKind::kRequest ? 500 : 502));
    GATEWAY_CHECK(rejected.consumedBytes < longLine.size());
    GATEWAY_CHECK(allocationParser.parseBytes(wire).consumedBytes == 0);
    allocationParser.resetParser();
    GATEWAY_CHECK(parse(allocationParser, wire).status ==
                  ParseStatus::kComplete);
  }
}

void testLifecycle() {
  HttpParser parser(MessageKind::kRequest);
  for (int repeat = 0; repeat < 100; ++repeat) {
    parser.resetParser();
    GATEWAY_CHECK(parse(parser, request()).status == ParseStatus::kComplete);
    parser.resetParser();
    GATEWAY_CHECK(parser.message().body.empty());
    GATEWAY_CHECK(parser.parseBytes("POST /v1/").status ==
                  ParseStatus::kNeedMore);
    GATEWAY_CHECK(parser.finishInput().status == ParseStatus::kRejected);
  }
  parser.resetParser();
  parser.parseBytes("POST /");
  const std::string longTarget(200, 'a');
  failAllocation = true;
  const auto failed = parser.parseBytes(longTarget);
  failAllocation = false;
  GATEWAY_CHECK(failed.status == ParseStatus::kRejected &&
                failed.errorStatus == 500);
  parser.resetParser();
  GATEWAY_CHECK(parse(parser, request()).status == ParseStatus::kComplete);
}
}  // namespace

int main() {
  try {
    testFraming();
    testJson();
    testFieldTypes();
    testNormalization();
    testBudgets();
    testDefaultBudgets();
    testLifecycle();
    testResponseStatusRework();
    testChunkExtensionsRework();
    testChunkAdapterBudgets();
    std::cout << "Protocol checks: " << gateway::test::checks
              << "; fragmentation seed 20261018\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
