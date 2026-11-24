# Pluggable Desktop Session Switcher and LuCI Control

`openwrt-desktop-base` owns the shared native-systemd desktop launcher,
PAM/logind VT7 session manager, `/etc/config/desktop`, `desktop-setup`,
`desktop-ctl`, `openwrt-desktop-services.service` (audio, Flatpak, and Sunshine
supervision), and the `sessions.d` plugin dispatcher, with no GNOME package
dependencies. `openwrt-desktop-core` depends on `openwrt-desktop-base` and
provides the GNOME session plugin (`sessions.d/gnome`), TPM2-sealed unattended
GNOME keyring bootstrap/unlock, Mutter settings, and `openwrt-gnome-remotes.service`.
`luci-app-desktop` (`Services -> Desktop`) depends only on `openwrt-desktop-base`.

## Session Plugin Contract

Installed desktop environments register a root-owned (`0644`) regular file
under `/usr/libexec/openwrt-desktop/sessions.d/<id>` where `<id>` matches
`^[a-z0-9][a-z0-9_-]{0,31}$` (symlinks are rejected).

Each plugin defines static metadata lines (parsed without execution by
`desktop-ctl`) and POSIX shell functions (with optional credential hooks):

- `SESSION_ID`: must match the filename (`<id>`).
- `SESSION_TITLE` / `SESSION_DESCRIPTION`: display strings shown in LuCI.
- `SESSION_EXEC`: absolute path to the session binary checked for
  executability.
- `SESSION_SUPPORTS_RDP` / `SESSION_SUPPORTS_KMS_SCHEDULING`: `"1"` or `"0"`.
- `SESSION_CREDENTIAL_BACKEND` / `SESSION_RDP_UNIT` (optional): credential
  backend identifier (for example `"gnome-keyring"`) and user RDP unit name
  (for example `"gnome-remote-desktop.service"`). Sessions without them report
  `not_applicable` / `rdp_available: false` and start without `LoadCredential*`.
- `SESSION_UNSET_VARS`: space-separated list of DE-specific variables cleared
  from the surviving `systemd --user` manager before any session starts.
- `desktop_session_check()`: verifies runtime prerequisites before starting.
- `desktop_session_setup()` / `desktop_session_user_setup()` (optional):
  root-side credential/TLS provisioning and per-user unit enablement run by
  `desktop-setup`.
- `desktop_session_credential_prop()` (optional): prints a `systemd-run`
  `LoadCredential*` property when the session requires a systemd credential.
- `desktop_session_unlock()` (optional): unlocks session credentials inside the
  user session before starting the compositor.
- `desktop_session_exec()`: exports DE variables, imports them into
  `systemctl --user`, and `exec`s the compositor/session manager.
- `desktop_session_stop()`: gracefully shuts down the user session before
  `openwrt-desktop.service` stops.

Session selection follows one shared rule across `desktop.init`, `desktop-setup`,
`desktop-ctl`, and LuCI: an explicitly configured `desktop.main.session` must
be installed and available; when unconfigured (`''`), a single available session
is selected automatically, while zero or multiple available sessions fail
preflight with an explicit message before touching any running session.

`openwrt-desktop-core` installs the `gnome` plugin
(`/usr/libexec/openwrt-desktop/sessions.d/gnome`), and
`openwrt-desktop-plasma-core` installs the `plasma` plugin
(`/usr/libexec/openwrt-desktop/sessions.d/plasma`). `desktop-ctl` and
`luci-app-desktop` automatically discover installed plugins.
See [KDE Plasma 6.8.3](kde-plasma.md) and
[desktop package decoupling validation](desktop-package-decoupling-validation.md).

## Lifecycle and Active-Session Tracking

- `/etc/config/desktop` defaults `option session ''` (auto-selecting when a
  single session plugin is installed, and requiring an explicit `'gnome'` or
  `'plasma'` value when multiple plugins are installed).
- When `/etc/init.d/desktop start` launches `openwrt-desktop.service`, it
  passes `OPENWRT_DESKTOP_SESSION` to `/usr/libexec/desktop-session` and
  atomically writes `/run/openwrt-desktop/active.env` (`ACTIVE_SESSION`,
  `ACTIVE_USER`, `ACTIVE_KMS_SCHEDULING`, `ACTIVE_OUTPUT`, `ACTIVE_MODE`).
- `/usr/libexec/desktop-session` collects `SESSION_UNSET_VARS` from all
  registered plugins, clears them from both the process and `systemctl --user`,
  calls `desktop_session_unlock` (which invokes `/usr/libexec/desktop-keyring-unlock`
  in both the `gnome` and `plasma` plugins, preserving TPM2 SRK unlock) and
  `/usr/libexec/desktop-user-setup --xdg-dirs`, then calls
  `desktop_session_exec`.
- `/etc/init.d/desktop stop` reads `/run/openwrt-desktop/active.env` so a
  session switch always shuts down the **previously running** DE via its own
  `desktop_session_stop` before starting the newly selected DE.

## CLI (`desktop-ctl`) and LuCI (`luci-app-desktop`)

`/usr/sbin/desktop-ctl --json` provides structured `schema_version: 1` JSON:

- `desktop-ctl --json status`: service state, UCI config, active runtime state,
  config drift (`restart_required` / `drifted_keys`), discovered sessions,
  connected DRM outputs, provisioning status (never reading or exposing secret
  contents), and live user-unit probes (keyring `Locked`, RDP, Sunshine,
  PipeWire/WirePlumber).
- `desktop-ctl --json action <start|stop|restart|reload>`: preflight-validates
  user, keyring credential, and target session availability before `start` or
  `restart` so an unavailable target never kills a running session.
- `desktop-ctl --json switch --session <id>`: validates `<id>`, writes UCI
  `desktop.main.session`, and restarts the service if currently active.
- `desktop-ctl --json sync-boot`: aligns `/etc/init.d/desktop enable|disable`
  with UCI `desktop.main.enabled`.
- `desktop-ctl --json logs --lines <1..200>`: reads bounded `journalctl` output
  for `openwrt-desktop.service`.

`luci-app-desktop` exposes `Services -> Desktop` (`admin/services/desktop`)
through `/usr/share/rpcd/ucode/luci.desktop` with separated read/write ACLs:

- **Editable in LuCI**: `enabled`, `session`, `output`, `mode`,
  `kms_scheduling`, `rdp_enabled`.
- **Read-only in LuCI** (managed over SSH): `user` (`desktop-setup USER`),
  `rdp_port` (`desktop-rdp-setup USER`), `sunshine_capture`
  (`sunshine-setup USER --capture=portal|--enable-kms`).
- **Save & Apply vs. Restart**: `Save & Apply` updates UCI and boot enable
  state without interrupting the active graphical session. When restart-bound
  settings drift from `/run/openwrt-desktop/active.env`, LuCI displays a drift
  banner with a confirmed **Restart desktop** action alongside a dedicated
  **Switch & Restart** control.

## Installed Session Plugins

- **GNOME 51 (`gnome`)**: `/usr/libexec/openwrt-desktop/sessions.d/gnome` (from
  `openwrt-desktop-core`), with GNOME-specific `openwrt-gnome-remotes.service`
  and `openwrt-fcitx5.service` (`openwrt-desktop-ime`). See
  [GNOME desktop](gnome-desktop.md).
- **KDE Plasma 6.8.3 (`plasma`)**: `/usr/libexec/openwrt-desktop/sessions.d/plasma`
  (from `openwrt-desktop-plasma-core`), with `openwrt-plasma-remotes.service`,
  KWin-managed Wayland Fcitx5 (`openwrt-desktop-ime-plasma` +
  `org.fcitx.Fcitx5.desktop`), and shared
  Secret Service keyring unlock (`kf6-kwallet` client-only so `gnome-keyring-daemon`
  owns `org.freedesktop.secrets`). See [KDE Plasma 6.8.3](kde-plasma.md).
- **Shared services**: `openwrt-audio-session.target`,
  `openwrt-flatpak-session.target`, and `sunshine.service` bind to
  `graphical-session.target` via `openwrt-desktop-services.service`.

## Validation

See [desktop session switcher validation](desktop-session-switcher-validation.md).
