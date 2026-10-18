#include "gateway/TextRequest.h"

#include <cmath>
#include <nlohmann/json.hpp>
#include <set>
#include <vector>

namespace gateway::gateway_api {
namespace {
using Json = nlohmann::json;
enum class Context { kRoot, kMessages, kMessage, kOther };
enum class ValueKind {
  kNull,
  kBoolean,
  kInteger,
  kFloat,
  kString,
  kObject,
  kArray
};
struct Frame {
  Context context;
  bool object;
  std::set<std::string> keys;
  std::string key;
  std::size_t elements = 0;
};
class TextSax final : public nlohmann::json_sax<Json> {
 public:
  explicit TextSax(JsonLimits limits) : limits_(limits) {}
  bool null() override;
  bool boolean(bool value) override;
  bool number_integer(number_integer_t value) override;
  bool number_unsigned(number_unsigned_t value) override;
  bool number_float(number_float_t value, const string_t&) override;
  bool string(string_t& value) override;
  bool binary(binary_t&) override;
  bool start_object(std::size_t) override;
  bool key(string_t& value) override;
  bool end_object() override;
  bool start_array(std::size_t) override;
  bool end_array() override;
  bool parse_error(std::size_t, const std::string&,
                   const nlohmann::detail::exception&) override;
  ValidationResult finish(bool parsed);

 private:
  bool acceptValue(ValueKind kind, std::string_view text = {},
                   double number = 0, bool flag = false);
  bool beginContainer(bool object);
  bool endContainer(bool object);
  void validateRootValue(const std::string& key, ValueKind kind,
                         std::string_view text, double number, bool flag);
  void validateMessageValue(const std::string& key, ValueKind kind,
                            std::string_view text);

  JsonLimits limits_;
  std::vector<Frame> frames_;
  TextRequestMetadata metadata_;
  std::size_t items_ = 0;
  bool rootSeen_ = false;
  bool invalid_ = false;
  bool unsupportedField_ = false;
  bool unsupportedStream_ = false;
};

bool TextSax::null() { return acceptValue(ValueKind::kNull); }

bool TextSax::boolean(bool value) {
  return acceptValue(ValueKind::kBoolean, {}, 0, value);
}

bool TextSax::number_integer(number_integer_t value) {
  return acceptValue(ValueKind::kInteger, {}, static_cast<double>(value));
}

bool TextSax::number_unsigned(number_unsigned_t value) {
  return acceptValue(ValueKind::kInteger, {}, static_cast<double>(value));
}

bool TextSax::number_float(number_float_t value, const string_t&) {
  return acceptValue(ValueKind::kFloat, {}, value);
}

bool TextSax::string(string_t& value) {
  return acceptValue(ValueKind::kString, value);
}

bool TextSax::binary(binary_t&) {
  invalid_ = true;
  return false;
}

bool TextSax::parse_error(std::size_t, const std::string&,
                          const nlohmann::detail::exception&) {
  invalid_ = true;
  return false;
}

void TextSax::validateRootValue(const std::string& key, ValueKind kind,
                                std::string_view text, double number,
                                bool flag) {
  if (key == "model") {
    if (kind != ValueKind::kString || text.empty() || text.size() > 256)
      invalid_ = true;
    else
      metadata_.model = text;
  } else if (key == "messages") {
    if (kind != ValueKind::kArray) invalid_ = true;
  } else if (key == "stream") {
    if (kind != ValueKind::kBoolean)
      invalid_ = true;
    else if (flag)
      unsupportedStream_ = true;
  } else if (key == "n") {
    if (kind != ValueKind::kInteger || number != 1) invalid_ = true;
  } else if (key == "max_tokens") {
    if (kind != ValueKind::kInteger || number < 1 || number > 8192)
      invalid_ = true;
  } else if (key == "temperature") {
    if ((kind != ValueKind::kInteger && kind != ValueKind::kFloat) ||
        !std::isfinite(number) || number < 0 || number > 2)
      invalid_ = true;
  } else
    unsupportedField_ = true;
}

void TextSax::validateMessageValue(const std::string& key, ValueKind kind,
                                   std::string_view text) {
  if (key == "role") {
    if (kind != ValueKind::kString ||
        (text != "system" && text != "user" && text != "assistant"))
      invalid_ = true;
  } else if (key == "content") {
    if (kind != ValueKind::kString) invalid_ = true;
  } else
    unsupportedField_ = true;
}

bool TextSax::acceptValue(ValueKind kind, std::string_view text, double number,
                          bool flag) {
  if (frames_.empty()) {
    if (rootSeen_ || kind != ValueKind::kObject) invalid_ = true;
    rootSeen_ = true;
    return true;
  }
  auto& frame = frames_.back();
  if (!frame.object) {
    if (++items_ > limits_.items) return false;
    ++frame.elements;
  }
  if (frame.context == Context::kRoot)
    validateRootValue(frame.key, kind, text, number, flag);
  if (frame.context == Context::kMessage)
    validateMessageValue(frame.key, kind, text);
  if (frame.context == Context::kMessages && kind != ValueKind::kObject)
    invalid_ = true;
  return true;
}

bool TextSax::beginContainer(bool object) {
  if (!acceptValue(object ? ValueKind::kObject : ValueKind::kArray))
    return false;
  if (frames_.size() >= limits_.depth) return false;
  auto context = Context::kOther;
  if (frames_.empty() && object)
    context = Context::kRoot;
  else if (!frames_.empty()) {
    const auto& parent = frames_.back();
    if (parent.context == Context::kRoot && parent.key == "messages" && !object)
      context = Context::kMessages;
    if (parent.context == Context::kMessages && object)
      context = Context::kMessage;
  }
  frames_.push_back({context, object, {}, {}, 0});
  return true;
}

bool TextSax::start_object(std::size_t) { return beginContainer(true); }

bool TextSax::start_array(std::size_t) { return beginContainer(false); }

bool TextSax::key(string_t& value) {
  if (++items_ > limits_.items || frames_.empty()) return false;
  auto& frame = frames_.back();
  if (!frame.keys.insert(value).second) return false;
  frame.key = value;
  return true;
}

bool TextSax::endContainer(bool object) {
  if (frames_.empty() || frames_.back().object != object) return false;
  const auto& frame = frames_.back();
  if (frame.context == Context::kRoot &&
      (!frame.keys.contains("model") || !frame.keys.contains("messages")))
    invalid_ = true;
  if (frame.context == Context::kMessage &&
      (!frame.keys.contains("role") || !frame.keys.contains("content")))
    invalid_ = true;
  if (frame.context == Context::kMessages) {
    metadata_.messageCount = frame.elements;
    if (frame.elements == 0 || frame.elements > 256) invalid_ = true;
  }
  frames_.pop_back();
  return true;
}

bool TextSax::end_object() { return endContainer(true); }

bool TextSax::end_array() { return endContainer(false); }

ValidationResult TextSax::finish(bool parsed) {
  if (!parsed || invalid_ || !rootSeen_ || !frames_.empty())
    return {false, 400, "invalid_request", {}};
  if (unsupportedField_) return {false, 400, "unsupported_field", {}};
  if (unsupportedStream_) return {false, 400, "unsupported_stream", {}};
  return {true, 0, "", std::move(metadata_)};
}
}  // namespace

ValidationResult validateTextRequest(const http::HttpMessage& request,
                                     JsonLimits limits) {
  if (request.target != "/v1/chat/completions")
    return {false, 404, "not_found", {}};
  if (request.method != "POST") return {false, 405, "method_not_allowed", {}};
  std::size_t contentTypes = 0;
  for (const auto& header : request.headers) {
    if (header.name == "content-type") {
      ++contentTypes;
      const auto value = http::lowerAscii(header.value);
      const auto semicolon = value.find(';');
      if (http::trimWhitespace(std::string_view(value).substr(0, semicolon)) !=
          "application/json")
        return {false, 415, "unsupported_media_type", {}};
      if (semicolon != std::string::npos) {
        auto parameter =
            http::trimWhitespace(std::string_view(value).substr(semicolon + 1));
        const auto equals = parameter.find('=');
        if (equals == std::string::npos ||
            http::trimWhitespace(
                std::string_view(parameter).substr(0, equals)) != "charset")
          return {false, 415, "unsupported_media_type", {}};
        const auto charset = http::trimWhitespace(
            std::string_view(parameter).substr(equals + 1));
        if (charset != "utf-8" && charset != "\"utf-8\"")
          return {false, 415, "unsupported_media_type", {}};
      }
    }
  }
  if (contentTypes != 1) return {false, 415, "unsupported_media_type", {}};
  try {
    TextSax validator(limits);
    const auto parsed =
        Json::sax_parse(request.body.begin(), request.body.end(), &validator);
    return validator.finish(parsed);
  } catch (...) {
    return {false, 500, "internal_error", {}};
  }
}

std::string errorBody(const ValidationResult& result) {
  // 稳定错误标识来自本模块，不包含输入正文或凭据。
  return Json{
      {"error", {{"code", result.errorCode}, {"message", "Request rejected"}}}}
      .dump();
}
}  // namespace gateway::gateway_api
