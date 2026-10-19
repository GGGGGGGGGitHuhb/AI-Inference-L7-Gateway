#include "gateway/ProxySession.h"

#include <arpa/inet.h>

#include <algorithm>
#include <array>
#include <cerrno>
#include <stdexcept>

#include "gateway/TextRequest.h"
#include "http/HttpNormalization.h"

namespace gateway::gateway_api {
namespace {
constexpr std::size_t kEventBytes = 65536;
constexpr std::size_t kRequestOutputLimit = 1048576 + 65536;
constexpr std::size_t kResponseOutputLimit = 4194304 + 65536;
using Milliseconds = std::chrono::milliseconds;
void releaseString(std::string& value) { std::string().swap(value); }
}  // namespace

ProxySession::ProxySession(net::EventLoop& loop,
                           const app::GatewayConfig& config, SessionIo& io,
                           upstream::ConnectionPool& pool, net::Socket client,
                           SessionIo::Clock::time_point acceptedAt)
    : loop_(loop),
      config_(config),
      io_(io),
      pool_(pool),
      downstreamSocket_(std::move(client)),
      downstreamChannel_(
          std::make_unique<net::Channel>(loop_, downstreamSocket_.fd())),
      requestParser_(
          std::make_unique<http::HttpParser>(http::MessageKind::kRequest)),
      acceptedAt_(acceptedAt),
      stageStarted_(acceptedAt_) {}

ProxySession::~ProxySession() { finishSession(); }

void ProxySession::startSession() {
  downstreamChannel_->registerEventCallback(
      [this](std::uint32_t events) { onDownstreamEvent(events); });
  updateInterests();
  armDeadline();
}

void ProxySession::closeUpstream() noexcept { upstreamLease_.invalidate(); }

void ProxySession::finishSession() noexcept {
  if (finished()) return;
  phase_ = Phase::kFinished;
  if (timerId_) {
    loop_.cancelTimer(timerId_);
    timerId_ = 0;
  }

  if (downstreamChannel_) downstreamChannel_->removeChannel();
  closeUpstream();
  downstreamSocket_.reset();
}

void ProxySession::onDownstreamEvent(std::uint32_t events) noexcept {
  try {
    handleDownstreamEvent(events);
  } catch (...) {
    prepareError(500, "internal_error");
  }
}

void ProxySession::onUpstreamEvent(std::uint32_t events) noexcept {
  try {
    handleUpstreamEvent(events);
  } catch (...) {
    prepareError(500, "internal_error");
  }
}

void ProxySession::onDeadline() noexcept {
  timerId_ = 0;
  try {
    if (!checkDeadline()) armDeadline();
  } catch (...) {
    prepareError(500, "internal_error");
  }
}

ProxySession::TimePoint ProxySession::nextDeadline() const {
  if (phase_ == Phase::kClosing)
    return std::min(outputCompletedAt_ + Milliseconds(1000),
                    errorDraining_
                        ? errorDeadline_
                        : acceptedAt_ + Milliseconds(config_.timeouts.total));
  if (errorDraining_) return errorDeadline_;
  auto deadline = acceptedAt_ + Milliseconds(config_.timeouts.total);
  if (phase_ == Phase::kReceiving)
    deadline = std::min(deadline,
                        acceptedAt_ + Milliseconds(config_.timeouts.request));
  if (phase_ == Phase::kConnecting)
    deadline = std::min(deadline,
                        stageStarted_ + Milliseconds(config_.timeouts.connect));
  if (phase_ == Phase::kUpstream) {
    deadline = std::min(deadline,
                        connectedAt_ + Milliseconds(config_.timeouts.response));
    if (upstreamOffset_ < upstreamOutput_.size())
      deadline =
          std::min(deadline,
                   connectedAt_ + Milliseconds(config_.timeouts.upstreamWrite));
  }

  if (phase_ == Phase::kStreaming) {
    if (!streamHttpComplete_)
      deadline = std::min(
          deadline, connectedAt_ + Milliseconds(config_.timeouts.response));
    if (streamOutput_ && streamOutput_->size())
      deadline = std::min(
          deadline,
          outputStarted_ + Milliseconds(config_.timeouts.downstreamWrite));
  }
  if (phase_ == Phase::kDownstream)
    deadline =
        std::min(deadline, outputStarted_ +
                               Milliseconds(config_.timeouts.downstreamWrite));
  return deadline;
}

void ProxySession::armDeadline() {
  if (finished()) return;
  const auto deadline = nextDeadline();
  if (timerId_ && loop_.rescheduleTimer(timerId_, deadline)) return;
  timerId_ = loop_.addTimer(deadline, [this] { onDeadline(); });
}

bool ProxySession::checkDeadline() {
  if (finished()) return true;
  const auto now = io_.now();
  if (now < nextDeadline()) return false;
  if (errorDraining_ || phase_ == Phase::kClosing) {
    finishSession();
    return true;
  }

  const auto earliest = nextDeadline();
  if (phase_ == Phase::kStreaming && streamOutput_->size() &&
      earliest != acceptedAt_ + Milliseconds(config_.timeouts.total) &&
      earliest ==
          outputStarted_ + Milliseconds(config_.timeouts.downstreamWrite)) {
    finishSession();
    return true;
  }
  if (earliest == acceptedAt_ + Milliseconds(config_.timeouts.total)) {
    if (phase_ == Phase::kDownstream && downstreamOffset_ != 0)
      finishSession();
    else
      prepareError(phase_ == Phase::kReceiving ? 408 : 504, "total_timeout");
  } else if (phase_ == Phase::kDownstream)
    finishSession();
  else if (phase_ == Phase::kReceiving)
    prepareError(408, "request_timeout");
  else if (phase_ == Phase::kConnecting)
    prepareError(504, "connect_timeout");
  else if (upstreamOffset_ < upstreamOutput_.size() &&
           earliest ==
               connectedAt_ + Milliseconds(config_.timeouts.upstreamWrite))
    prepareError(504, "upstream_write_timeout");
  else
    prepareError(504, "response_timeout");
  return true;
}

void ProxySession::updateInterests() {
  if (finished()) return;
  std::uint32_t downstreamEvents = downstreamEof_ ? 0 : EPOLLIN | EPOLLRDHUP;
  if (phase_ == Phase::kDownstream ||
      (phase_ == Phase::kStreaming && streamOutput_ && streamOutput_->size()) ||
      (phase_ == Phase::kClosing && !writeShutdown_))
    downstreamEvents |= EPOLLOUT;
  downstreamChannel_->setInterest(downstreamEvents);
  if (upstreamLease_.valid()) {
    std::uint32_t upstreamEvents = EPOLLIN | EPOLLRDHUP;
    if (phase_ == Phase::kConnecting ||
        upstreamOffset_ < upstreamOutput_.size())
      upstreamEvents |= EPOLLOUT;
    upstreamLease_.setInterest(upstreamEvents);
  }
}

void ProxySession::handleDownstreamEvent(std::uint32_t events) {
  if (checkDeadline()) return;
  if (events & (EPOLLIN | EPOLLRDHUP | EPOLLHUP | EPOLLERR)) readDownstream();
  if (finished()) return;
  if ((events & EPOLLERR) && io_.socketError(downstreamSocket_.fd())) {
    finishSession();
    return;
  }

  if (phase_ == Phase::kStreaming && (events & EPOLLOUT))
    writeStream();
  else if (phase_ == Phase::kDownstream && (events & EPOLLOUT))
    writeDownstream();
  else if (phase_ == Phase::kClosing && !writeShutdown_ && (events & EPOLLOUT))
    shutdownWrite();
}

void ProxySession::readDownstream() {
  std::array<char, 16384> bytes{};
  std::size_t handled = 0;
  for (int attempt = 0;
       attempt < 64 && handled < kEventBytes && !downstreamEof_; ++attempt) {
    if (checkDeadline()) return;
    const auto count =
        io_.receiveBytes(downstreamSocket_.fd(), bytes.data(),
                         std::min(bytes.size(), kEventBytes - handled));
    if (count > 0) {
      handled += count;
      if (phase_ != Phase::kReceiving)
        continue;  // 有界丢弃第二请求，不保留、不再次派发。
      const auto result = requestParser_->parseBytes(
          {bytes.data(), static_cast<std::size_t>(count)});
      if (result.status == http::ParseStatus::kRejected) {
        prepareError(result.errorStatus, result.errorCode);
        return;
      }
      if (result.status == http::ParseStatus::kComplete) {
        beginUpstream();
        return;
      }
    } else if (count == 0) {
      downstreamEof_ = true;
      if (phase_ == Phase::kReceiving)
        prepareError(400, "invalid_request");
      else if (phase_ == Phase::kClosing && writeShutdown_)
        finishSession();
      else
        updateInterests();
      return;
    } else if (errno == EINTR)
      continue;
    else if (errno == EAGAIN || errno == EWOULDBLOCK)
      return;
    else {
      finishSession();
      return;
    }
  }
}

void ProxySession::checkOutputBudget(const http::HttpMessage& message,
                                     std::size_t limit) const {
  // 最多 16KiB 解析头 + 合法配置/受控头远小于 64KiB；逐项先检查。
  std::size_t bytes = 1024;
  for (const auto& header : message.headers) {
    const auto length = header.name.size() + header.value.size() + 4;
    if (length > limit - bytes) throw std::length_error("output headers");
    bytes += length;
  }

  if (message.body.size() > limit - bytes)
    throw std::length_error("output body");
}

void ProxySession::beginUpstream() {
  const auto validation = validateTextRequest(requestParser_->message());
  if (!validation.accepted) {
    prepareError(validation.errorStatus, validation.errorCode);
    return;
  }

  streamRequest_ = validation.metadata.stream;
  checkOutputBudget(requestParser_->message(), kRequestOutputLimit);
  upstreamOutput_ = http::normalizeMessage(
      requestParser_->message(), http::MessageKind::kRequest,
      config_.upstreamAddress + ":" + std::to_string(config_.upstreamPort),
      streamRequest_ || config_.upstreamPool.maxIdle == 0);
  if (checkDeadline()) return;
  requestParser_.reset();
  responseParser_ = std::make_unique<http::HttpParser>(
      http::MessageKind::kResponse, http::ParserLimits{},
      streamRequest_ ? http::ResponseMode::kAllowEventStream
                     : http::ResponseMode::kBuffered);
  upstreamLease_ = pool_.acquireConnection(
      [this](std::uint32_t events) { onUpstreamEvent(events); });
  if (!upstreamLease_.valid()) {
    prepareError(503,
                 pool_.stopping() ? "gateway_stopping" : "upstream_capacity");
    return;
  }
  if (upstreamLease_.reused()) {
    confirmConnected();
    return;
  }
  sockaddr_in destination{};
  destination.sin_family = AF_INET;
  destination.sin_port = htons(config_.upstreamPort);
  inet_pton(AF_INET, config_.upstreamAddress.c_str(), &destination.sin_addr);
  stageStarted_ = io_.now();
  phase_ = Phase::kConnecting;
  for (int attempt = 0; attempt < 32; ++attempt) {
    if (checkDeadline()) return;
    const int result = io_.connectSocket(
        upstreamLease_.fd(), reinterpret_cast<const sockaddr*>(&destination),
        sizeof(destination));
    if (result == 0) {
      confirmConnected();
      return;
    }
    if (errno == EINTR) continue;
    if (errno == EINPROGRESS || errno == EALREADY) {
      updateInterests();
      armDeadline();
      return;
    }

    prepareError(502, "upstream_error");
    return;
  }

  updateInterests();
  armDeadline();
}

void ProxySession::confirmConnected() {
  if (io_.socketError(upstreamLease_.fd()) != 0) {
    prepareError(502, "upstream_error");
    return;
  }
  upstreamLease_.markConnected();
  phase_ = Phase::kUpstream;
  connectedAt_ = io_.now();
  updateInterests();
  armDeadline();
}

void ProxySession::handleUpstreamEvent(std::uint32_t events) {
  if (checkDeadline() || !upstreamLease_.valid()) return;
  if (events & (EPOLLRDHUP | EPOLLHUP | EPOLLERR)) responseReusable_ = false;
  if (phase_ == Phase::kDownstream || phase_ == Phase::kClosing) {
    // 响应已缓存。任何迟到读/关闭事件只失效租约，不生成第二响应。
    if (events & (EPOLLIN | EPOLLRDHUP | EPOLLHUP | EPOLLERR)) closeUpstream();
    return;
  }
  if (phase_ == Phase::kConnecting) confirmConnected();
  if (phase_ != Phase::kUpstream && phase_ != Phase::kStreaming) return;
  if (events & (EPOLLIN | EPOLLRDHUP | EPOLLHUP | EPOLLERR)) readUpstream();
  if (phase_ != Phase::kUpstream && phase_ != Phase::kStreaming) return;
  if (!upstreamLease_.valid()) return;
  if ((events & EPOLLERR) && io_.socketError(upstreamLease_.fd())) {
    prepareError(502, "upstream_error");
    return;
  }

  if (phase_ == Phase::kUpstream && (events & EPOLLOUT)) writeUpstream();
}

void ProxySession::readUpstream() {
  std::array<char, 16384> bytes{};
  std::size_t handled = 0;
  for (int attempt = 0; attempt < 64 && handled < kEventBytes; ++attempt) {
    if (checkDeadline()) return;
    auto count =
        io_.receiveBytes(upstreamLease_.fd(), bytes.data(),
                         std::min(bytes.size(), kEventBytes - handled));
    if (count < 0) {
      if (errno == EINTR) continue;
      if (errno == EAGAIN || errno == EWOULDBLOCK) return;
      prepareError(502, "upstream_error");
      return;
    }
    const auto result =
        count == 0 ? responseParser_->finishInput()
                   : responseParser_->parseBytes(
                         {bytes.data(), static_cast<std::size_t>(count)});
    if (result.status == http::ParseStatus::kRejected) {
      if (streamRequest_ &&
          std::string_view(result.errorCode) == "internal_error")
        prepareError(500, "internal_error");
      else
        prepareError(502, "upstream_error");
      return;
    }
    if (responseParser_->eventStream() &&
        responseParser_->finalHeadersReady()) {
      acceptStreamResult(result);
      if (finished() || phase_ != Phase::kStreaming || streamHttpComplete_)
        return;
      handled += static_cast<std::size_t>(count);
      if (count == 0) return;
      continue;
    }
    if (result.status == http::ParseStatus::kComplete) {
      if (count == 0 || result.consumedBytes != static_cast<std::size_t>(count))
        responseReusable_ = false;
      completeResponse();
      return;
    }
    handled += count;
    if (count == 0) {
      prepareError(502, "upstream_error");
      return;
    }
  }
}

void ProxySession::writeUpstream() {
  std::size_t handled = 0;
  for (int attempt = 0; attempt < 64 && handled < kEventBytes &&
                        upstreamOffset_ < upstreamOutput_.size();
       ++attempt) {
    if (checkDeadline()) return;
    const auto count = io_.sendBytes(
        upstreamLease_.fd(), upstreamOutput_.data() + upstreamOffset_,
        std::min(kEventBytes - handled,
                 upstreamOutput_.size() - upstreamOffset_));
    if (count > 0) {
      upstreamOffset_ += count;
      handled += count;
    } else if (count < 0 && errno == EINTR)
      continue;
    else if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
      break;
    else {
      responseReusable_ = false;
      // 写失败时也先读已到达的早期最终响应，避免 OUT/IN 同轮顺序误判。
      readUpstream();
      if (phase_ == Phase::kUpstream) prepareError(502, "upstream_error");
      return;
    }
  }

  if (upstreamOffset_ == upstreamOutput_.size()) {
    requestWriteComplete_ = true;
    releaseString(upstreamOutput_);
    upstreamOffset_ = 0;
  }

  updateInterests();
  armDeadline();
}

void ProxySession::completeResponse() {
  if (checkDeadline()) return;
  checkOutputBudget(responseParser_->message(), kResponseOutputLimit);
  downstreamOutput_ = http::normalizeMessage(
      responseParser_->message(), http::MessageKind::kResponse, {}, true);
  if (checkDeadline()) return;
  const auto& message = responseParser_->message();
  responseReusable_ = responseReusable_ && !streamRequest_ &&
                      requestWriteComplete_ && !message.eofDelimited;
  for (const auto& header : message.headers) {
    if (http::lowerAscii(header.name) != "connection") continue;
    std::string_view tokens(header.value);
    while (!tokens.empty()) {
      const auto comma = tokens.find(',');
      if (http::lowerAscii(http::trimWhitespace(tokens.substr(0, comma))) ==
          "close")
        responseReusable_ = false;
      if (comma == std::string_view::npos) break;
      tokens.remove_prefix(comma + 1);
    }
  }
  responseParser_.reset();
  releaseString(upstreamOutput_);
  upstreamOffset_ = 0;
  if (!responseReusable_) closeUpstream();
  phase_ = Phase::kDownstream;
  outputStarted_ = io_.now();
  updateInterests();
  armDeadline();
}

void ProxySession::beginStream() {
  streamOutput_ = std::make_unique<http::StreamOutput>();
  const auto headers = http::normalizeStreamHeaders(responseParser_->message());
  if (!streamOutput_->appendHeaders(headers)) {
    prepareError(502, "stream_buffer_limit");
    return;
  }

  phase_ = Phase::kStreaming;
  responseReusable_ = false;
  outputStarted_ = io_.now();
  // early SSE最终头停止上传，不能把清空offset当作已发送完请求。
  releaseString(upstreamOutput_);
  upstreamOffset_ = 0;
}

void ProxySession::acceptStreamResult(const http::ParseResult& result) {
  if (phase_ == Phase::kUpstream) beginStream();
  if (phase_ != Phase::kStreaming) return;
  const bool wasEmpty = streamOutput_->size() == 0;
  streamDecodedTotal_ = responseParser_->decodedTotal();
  streamWireTotal_ = responseParser_->wireTotal();
  if (!streamOutput_->appendChunk(responseParser_->bodyFragment())) {
    prepareError(502, "stream_buffer_limit");
    return;
  }

  // 新批次先记录起点，完成复核不能误用上一个已排空批次的写期限。
  if (wasEmpty) outputStarted_ = io_.now();
  if (result.status == http::ParseStatus::kComplete) {
    // recv/解析及候选输出构造可能跨过截止；撤销response期限前再次判定。
    if (checkDeadline()) return;
    streamHttpComplete_ = true;
    if (!streamOutput_->appendTerminator()) {
      prepareError(502, "stream_buffer_limit");
      return;
    }
    closeUpstream();
    responseParser_.reset();
  }

  updateInterests();
  armDeadline();
}

void ProxySession::writeStream() {
  std::size_t handled = 0;
  int attempts = 0;
  for (; attempts < 64 && handled < kEventBytes && streamOutput_->size();
       ++attempts) {
    if (checkDeadline()) return;
    const auto pending = streamOutput_->pending();
    const auto count =
        io_.sendBytes(downstreamSocket_.fd(), pending.data(),
                      std::min(kEventBytes - handled, pending.size()));
    if (count > 0) {
      responseStarted_ = true;
      handled += count;
      streamOutput_->consumeBytes(static_cast<std::size_t>(count));
    } else if (count < 0 && errno == EINTR)
      continue;
    else if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
      break;
    else {
      finishSession();
      return;
    }
  }

  if (streamOutput_->size() == 0 && streamHttpComplete_) {
    streamOutput_.reset();
    beginClosing(64 - attempts);
    return;
  }

  updateInterests();
  armDeadline();
}

void ProxySession::writeDownstream() {
  std::size_t handled = 0;
  int attempts = 0;
  for (; attempts < 64 && handled < kEventBytes &&
         downstreamOffset_ < downstreamOutput_.size();
       ++attempts) {
    if (checkDeadline()) return;
    const auto count = io_.sendBytes(
        downstreamSocket_.fd(), downstreamOutput_.data() + downstreamOffset_,
        std::min(kEventBytes - handled,
                 downstreamOutput_.size() - downstreamOffset_));
    if (count > 0) {
      responseStarted_ = true;
      downstreamOffset_ += count;
      handled += count;
    } else if (count < 0 && errno == EINTR)
      continue;
    else if (count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
      return;
    else {
      finishSession();
      return;
    }
  }

  if (downstreamOffset_ == downstreamOutput_.size())
    beginClosing(64 - attempts);
}

void ProxySession::beginClosing(int remainingCalls) {
  // 此时最后一个字节已提交内核；只记录一次，不代表客户端应用已消费。
  outputCompletedAt_ = io_.now();
  phase_ = Phase::kClosing;
  releaseString(downstreamOutput_);
  downstreamOffset_ = 0;
  requestParser_.reset();
  responseParser_.reset();
  releaseString(upstreamOutput_);
  shutdownWrite(remainingCalls);
}

void ProxySession::shutdownWrite(int remainingCalls) {
  if (checkDeadline()) return;
  for (int attempt = 0; attempt < remainingCalls && !writeShutdown_;
       ++attempt) {
    if (checkDeadline()) return;
    if (io_.shutdownWrite(downstreamSocket_.fd()) == 0) {
      writeShutdown_ = true;
      if (responseReusable_ && !errorDraining_)
        upstreamLease_.releaseReusable();
      else
        closeUpstream();
    } else if (errno != EINTR) {
      finishSession();
      return;
    }
  }

  if (writeShutdown_ && downstreamEof_) {
    finishSession();
    return;
  }
  // EINTR预算用尽时仍保留OUT重试；成功后仅观察读侧，EAGAIN不终结。
  updateInterests();
  armDeadline();
}

void ProxySession::prepareError(unsigned status, const char* code) noexcept {
  if (finished()) return;
  if (phase_ == Phase::kClosing || errorDraining_ || responseStarted_) {
    finishSession();
    return;
  }
  try {
    closeUpstream();
    streamOutput_.reset();
    requestParser_.reset();
    responseParser_.reset();
    releaseString(upstreamOutput_);
    downstreamOutput_ = http::serializeError(
        status, errorBody({false, status, code, {}}), true);
    if (downstreamOutput_.size() > 4096) {
      finishSession();
      return;
    }
    downstreamOffset_ = 0;
    errorDraining_ = true;
    phase_ = Phase::kDownstream;
    errorDeadline_ = io_.now() + Milliseconds(std::min(
                                     config_.timeouts.downstreamWrite, 1000));
    updateInterests();
    armDeadline();
  } catch (...) {
    finishSession();
  }
}
}  // namespace gateway::gateway_api
