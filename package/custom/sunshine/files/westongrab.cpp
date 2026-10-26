/**
 * SPDX-License-Identifier: GPL-3.0-only
 * Capture a named Weston mirror on the desktop user's PipeWire core.
 */
#include "pipewire.cpp"
#include <cerrno>
#include <cstdlib>

namespace weston {
  constexpr const char *node_name = "weston.pipewire";

  // Resolve object.serial on every connection: PipeWire node IDs are reusable.
  class discovery_t {
  public:
    uint32_t node = PW_ID_ANY;
    uint64_t serial = SPA_ID_INVALID;

    ~discovery_t() {
      if (registry) {
        spa_hook_remove(&registry_listener);
        pw_proxy_destroy(reinterpret_cast<pw_proxy *>(registry));
      }
      if (core) {
        spa_hook_remove(&core_listener);
        pw_core_disconnect(core);
      }
      if (context) {
        pw_context_destroy(context);
      }
      if (loop) {
        pw_main_loop_destroy(loop);
      }
    }

    bool resolve() {
      pw_init(nullptr, nullptr);
      loop = pw_main_loop_new(nullptr);
      if (!loop) {
        return false;
      }
      context = pw_context_new(pw_main_loop_get_loop(loop), nullptr, 0);
      if (!context) {
        return false;
      }
      core = pw_context_connect(context, nullptr, 0);
      if (!core) {
        return false;
      }
      pw_core_add_listener(core, &core_listener, &core_events, this);
      registry = pw_core_get_registry(core, PW_VERSION_REGISTRY, 0);
      if (!registry) {
        return false;
      }
      pw_registry_add_listener(registry, &registry_listener, &registry_events, this);
      sequence = pw_core_sync(core, PW_ID_CORE, 0);
      const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(5000);
      while ((!complete || matches == 0) && !failed && std::chrono::steady_clock::now() < deadline) {
        if (pw_loop_iterate(pw_main_loop_get_loop(loop), 100) < 0) {
          failed = true;
        }
      }
      return complete && !failed && matches == 1 && node != PW_ID_ANY && serial != SPA_ID_INVALID;
    }

  private:
    pw_main_loop *loop = nullptr;
    pw_context *context = nullptr;
    pw_core *core = nullptr;
    pw_registry *registry = nullptr;
    spa_hook core_listener {}, registry_listener {};
    int sequence = 0;
    unsigned matches = 0;
    bool complete = false, failed = false;

    static void global(void *data, uint32_t id, uint32_t, const char *type, uint32_t, const spa_dict *props) {
      auto &self = *static_cast<discovery_t *>(data);
      if (strcmp(type, PW_TYPE_INTERFACE_Node) || !props) {
        return;
      }
      const auto name = spa_dict_lookup(props, PW_KEY_NODE_NAME);
      const auto serial = spa_dict_lookup(props, PW_KEY_OBJECT_SERIAL);
      if (!name || strcmp(name, node_name) || !serial) {
        return;
      }
      char *end = nullptr;
      errno = 0;
      auto value = std::strtoull(serial, &end, 10);
      if (errno || end == serial || *end) {
        return;
      }
      self.matches++;
      self.node = id;
      self.serial = value;
    }

    static void removed(void *data, uint32_t id) {
      auto &self = *static_cast<discovery_t *>(data);
      if (id == self.node) {
        self.node = PW_ID_ANY;
        self.failed = true;
      }
    }

    static void done(void *data, uint32_t id, int seq) {
      auto &self = *static_cast<discovery_t *>(data);
      if (id == PW_ID_CORE && seq == self.sequence) {
        self.complete = true;
      }
    }

    static void error(void *data, uint32_t, int, int, const char *) {
      static_cast<discovery_t *>(data)->failed = true;
    }

    static constexpr pw_registry_events registry_events {
      .version = PW_VERSION_REGISTRY_EVENTS,
      .global = global,
      .global_remove = removed,
    };
    static constexpr pw_core_events core_events {
      .version = PW_VERSION_CORE_EVENTS,
      .done = done,
      .error = error,
    };
  };

  class display_t: public pipewire::pipewire_display_t {
  public:
    int configure_stream(const std::string &name, int &fd, uint32_t &node, uint64_t &serial) override {
      if (!name.empty() && name != node_name) {
        return -1;
      }
      discovery_t discovery;
      if (!discovery.resolve()) {
        BOOST_LOG(error) << "[westongrab] Weston PipeWire mirror is unavailable; KMS fallback is disabled";
        return -1;
      }
      const char *output = std::getenv("OPENWRT_DESKTOP_OUTPUT");
      if (!output || !*output) {
        BOOST_LOG(error) << "[westongrab] OPENWRT_DESKTOP_OUTPUT is missing";
        return -1;
      }
      for (const auto &monitor : wl::monitors()) {
        if (monitor->name != output) {
          continue;
        }
        offset_x = monitor->viewport.offset_x;
        offset_y = monitor->viewport.offset_y;
        width = monitor->viewport.width;
        height = monitor->viewport.height;
        logical_width = monitor->viewport.logical_width;
        logical_height = monitor->viewport.logical_height;
        if (width <= 0 || height <= 0) {
          return -1;
        }
        fd = -1;
        node = discovery.node;
        serial = discovery.serial;
        BOOST_LOG(info) << "[westongrab] " << node_name << " serial=" << serial
                        << " mirrors " << output << " at " << width << 'x' << height;
        return 0;
      }
      BOOST_LOG(error) << "[westongrab] Physical output not found: " << output;
      return -1;
    }
  };
}

namespace platf {
  std::vector<std::string> weston_display_names() {
    weston::discovery_t discovery;
    if (discovery.resolve()) {
      return {weston::node_name};
    }
    return {};
  }

  std::shared_ptr<display_t> weston_display(mem_type_e type, const std::string &name, const video::config_t &config) {
    if (!weston::display_t::init_pipewire_and_check_hwdevice_type(type)) {
      return nullptr;
    }
    auto display = std::make_shared<weston::display_t>();
    if (display->init(type, name, config)) {
      return nullptr;
    }
    return display;
  }
}
