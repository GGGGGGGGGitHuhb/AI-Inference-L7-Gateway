#pragma once

#include <string>
#include <string_view>

#include "http/HttpParser.h"

namespace gateway::http {
// 只接受 HttpParser 已完成的消息；request 必须另经 validateTextRequest。
std::string normalizeMessage(const HttpMessage& message, MessageKind kind,
                             std::string_view upstreamAuthority = {});
std::string serializeError(unsigned status, std::string_view body);
}  // namespace gateway::http
