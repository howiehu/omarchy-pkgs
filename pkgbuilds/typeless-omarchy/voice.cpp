// SPDX-License-Identifier: MIT
// Independent implementation of the local VoiceIME socket protocol.
#include <fcitx/addonfactory.h>
#include <fcitx/addonmanager.h>
#include <fcitx/inputcontext.h>
#include <fcitx/inputmethodengine.h>
#include <fcitx/instance.h>
#include <fcitx/surroundingtext.h>
#include <fcitx-utils/event.h>
#include <fcitx-utils/log.h>
#include <glib.h>
#include <json-c/json.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>
#include <cerrno>
#include <cstring>
#include <cstdlib>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>

namespace {
constexpr size_t maxPayload = 65536;
constexpr size_t maxClients = 8;
struct Client {
  int fd;
  std::string bytes;
  std::unique_ptr<fcitx::EventSourceIO> io;
  std::unique_ptr<fcitx::EventSourceTime> timeout;
  explicit Client(int value) : fd(value) {}
  ~Client() { close(fd); }
};

class Voice final : public fcitx::AddonInstance {
public:
  explicit Voice(fcitx::Instance *instance) : instance_(instance) {
    const char *runtime = std::getenv("XDG_RUNTIME_DIR");
    if (!runtime || runtime[0] != '/') {
      throw std::runtime_error("Voice bridge needs XDG_RUNTIME_DIR");
    }
    const std::string directory = std::string(runtime) + "/typeless-voice-ime";
    if (mkdir(directory.c_str(), 0700) != 0 && errno != EEXIST) {
      throw std::runtime_error("Cannot create VoiceIME runtime directory");
    }
    struct stat info {};
    if (lstat(directory.c_str(), &info) || !S_ISDIR(info.st_mode) ||
        info.st_uid != getuid() || (info.st_mode & 077) != 0) {
      throw std::runtime_error("Unsafe VoiceIME runtime directory");
    }
    path_ = directory + "/inject.sock";
    sockaddr_un address {};
    address.sun_family = AF_UNIX;
    if (path_.size() >= sizeof(address.sun_path)) {
      throw std::runtime_error("VoiceIME socket path is too long");
    }
    std::memcpy(address.sun_path, path_.c_str(), path_.size() + 1);
    if (lstat(path_.c_str(), &info) == 0) {
      // A live IBus or another bridge must keep ownership of this endpoint.
      if (!S_ISSOCK(info.st_mode) || info.st_uid != getuid()) {
        throw std::runtime_error("Unsafe existing VoiceIME socket");
      }
      int probe = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
      if (probe < 0) { throw std::runtime_error("Cannot probe VoiceIME socket"); }
      int result = connect(probe, reinterpret_cast<sockaddr *>(&address), sizeof(address));
      int error = errno;
      close(probe);
      if (result == 0 || error != ECONNREFUSED) {
        throw std::runtime_error("VoiceIME socket is already in use");
      }
      if (unlink(path_.c_str())) { throw std::runtime_error("Cannot remove stale socket"); }
    }
    listen_ = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (listen_ < 0) { throw std::runtime_error("Cannot create VoiceIME socket"); }
    if (bind(listen_, reinterpret_cast<sockaddr *>(&address), sizeof(address))) {
      close(listen_);
      listen_ = -1;
      throw std::runtime_error("Cannot bind VoiceIME socket");
    }
    if (chmod(path_.c_str(), 0600) || listen(listen_, 8)) {
      close(listen_);
      listen_ = -1;
      unlink(path_.c_str());
      throw std::runtime_error("Cannot listen on VoiceIME socket");
    }
    lstat(path_.c_str(), &socketInfo_);
    acceptEvent_ = instance_->eventLoop().addIOEvent(listen_, fcitx::IOEventFlag::In,
      [this](auto *, int, auto) { acceptClients(); return true; });
  }

  ~Voice() override {
    clients_.clear();
    acceptEvent_.reset();
    if (listen_ >= 0) { close(listen_); }
    struct stat current {};
    if (!lstat(path_.c_str(), &current) && current.st_ino == socketInfo_.st_ino &&
        current.st_dev == socketInfo_.st_dev) { unlink(path_.c_str()); }
  }

private:
  fcitx::InputContext *focused() {
    auto *ic = instance_->lastFocusedInputContext();
    if (!ic || !ic->hasFocus()) {
      return nullptr;
    }
    return ic;
  }

  std::string status() {
    auto *ic = focused();
    if (!ic) { return "UNFOCUSED"; }
    const auto flags = ic->capabilityFlags();
    if (flags.testAny(fcitx::CapabilityFlag::PasswordOrSensitive)) { return "PASSWORD"; }
    if (flags.test(fcitx::CapabilityFlag::Disable)) { return "UNFOCUSED"; }
    // A focused Fcitx input context is the commit target. GTK may not provide
    // surrounding text for an empty entry; requiring it rejects valid targets.
    return "FOCUSED_EDITABLE";
  }

  std::string handle(const std::string &bytes) {
    if (!g_utf8_validate(bytes.data(), bytes.size(), nullptr)) { return "ERROR"; }
    auto *parser = json_tokener_new();
    if (!parser) { return "ERROR"; }
    json_tokener_set_flags(parser, JSON_TOKENER_STRICT);
    auto *raw = json_tokener_parse_ex(parser, bytes.c_str(), bytes.size() + 1);
    const bool valid = json_tokener_get_error(parser) == json_tokener_success;
    json_tokener_free(parser);
    std::unique_ptr<json_object, decltype(&json_object_put)> message(raw, json_object_put);
    if (!valid || !raw || !json_object_is_type(raw, json_type_object)) { return "ERROR"; }
    json_object *operation = nullptr;
    json_object *text = nullptr;
    json_object_object_get_ex(raw, "text", &text);
    std::string op;
    if (json_object_object_get_ex(raw, "op", &operation)) {
      if (!json_object_is_type(operation, json_type_string)) { return "ERROR"; }
      op.assign(json_object_get_string(operation), json_object_get_string_len(operation));
    }
    if (op == "status" || op == "ping" || (op.empty() && !text)) { return status(); }
    // Selection/context reading is intentionally outside the dictation prototype.
    if (op != "commit" || !text || !json_object_is_type(text, json_type_string)) { return "ERROR"; }
    const char *value = json_object_get_string(text);
    const size_t length = json_object_get_string_len(text);
    if (!length || std::strlen(value) != length) { return "ERROR"; }
    auto *ic = focused();
    if (!ic) { return "NO_FOCUS"; }
    if (ic->capabilityFlags().testAny(fcitx::CapabilityFlag::PasswordOrSensitive)) { return "PASSWORD"; }
    if (ic->capabilityFlags().test(fcitx::CapabilityFlag::Disable)) { return "NO_FOCUS"; }
    ic->commitString(std::string(value, length));
    return "OK";
  }

  void reply(int fd, const std::string &value) {
    // Replies are short status tokens; never emit injected text to logs.
    send(fd, value.data(), value.size(), MSG_NOSIGNAL);
    clients_.erase(fd);
  }

  void readClient(int fd) {
    auto &client = *clients_.at(fd);
    char buffer[4096];
    for (;;) {
      const auto count = recv(fd, buffer, sizeof(buffer), 0);
      if (count > 0) {
        if (client.bytes.size() + count > maxPayload) { reply(fd, "ERROR"); return; }
        client.bytes.append(buffer, count);
      } else if (count == 0) {
        reply(fd, handle(client.bytes));
        return;
      } else if (errno == EAGAIN || errno == EWOULDBLOCK) { return; }
      else if (errno != EINTR) { clients_.erase(fd); return; }
    }
  }

  void acceptClients() {
    // A bounded batch keeps other input-method events responsive.
    for (size_t i = 0; i < maxClients; ++i) {
      int fd = accept4(listen_, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
      if (fd < 0) { return; }
      ucred credentials {};
      socklen_t size = sizeof(credentials);
      if (clients_.size() >= maxClients ||
          getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &credentials, &size) || credentials.uid != getuid()) {
        send(fd, "UNAUTHORIZED", 12, MSG_NOSIGNAL);
        close(fd);
        continue;
      }
      auto client = std::make_unique<Client>(fd);
      client->io = instance_->eventLoop().addIOEvent(fd, fcitx::IOEventFlag::In,
        [this, fd](auto *, int, auto) { readClient(fd); return true; });
      client->timeout = instance_->eventLoop().addTimeEvent(CLOCK_MONOTONIC,
        fcitx::now(CLOCK_MONOTONIC) + 1000000, 0,
        [this, fd](auto *, auto) { reply(fd, "TIMEOUT"); return false; });
      client->timeout->setOneShot();
      clients_.emplace(fd, std::move(client));
    }
  }

  fcitx::Instance *instance_;
  int listen_ = -1;
  std::string path_;
  struct stat socketInfo_ {};
  std::unique_ptr<fcitx::EventSourceIO> acceptEvent_;
  std::map<int, std::unique_ptr<Client>> clients_;
};

class Factory final : public fcitx::AddonFactory {
  fcitx::AddonInstance *create(fcitx::AddonManager *manager) override {
    try { return new Voice(manager->instance()); }
    catch (const std::exception &error) {
      FCITX_ERROR() << "Typeless voice bridge: " << error.what();
      return nullptr;
    }
  }
};
} // namespace
FCITX_ADDON_FACTORY(Factory)
