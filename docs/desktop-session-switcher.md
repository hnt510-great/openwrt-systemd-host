# Pluggable Desktop Session Switcher and LuCI Control

`openwrt-desktop` separates the shared native-systemd desktop launcher from
desktop-environment-specific startup and shutdown logic, and pairs it with
`luci-app-desktop` (`Services -> Desktop`) for web inspection and control.

Local display, TPM2-sealed unattended GNOME keyring unlock, PAM/logind session
creation on VT7, and LAN RDP/Sunshine supervision remain owned by
`openwrt-desktop-core`. Switching sessions does not require GDM or changing
the keyring bootstrap model.

## Session Plugin Contract

Installed desktop environments register a root-owned (`0644`) regular file
under `/usr/libexec/openwrt-desktop/sessions.d/<id>` where `<id>` matches
`^[a-z0-9][a-z0-9_-]{0,31}$` (symlinks are rejected).

Each plugin defines static metadata lines (parsed without execution by
`desktop-ctl`) and three POSIX shell functions:

- `SESSION_ID`: must match the filename (`<id>`).
- `SESSION_TITLE` / `SESSION_DESCRIPTION`: display strings shown in LuCI.
- `SESSION_EXEC`: absolute path to the session binary checked for
  executability.
- `SESSION_SUPPORTS_RDP` / `SESSION_SUPPORTS_KMS_SCHEDULING`: `"1"` or `"0"`.
- `SESSION_UNSET_VARS`: space-separated list of DE-specific variables cleared
  from the surviving `systemd --user` manager before any session starts.
- `desktop_session_check()`: verifies runtime prerequisites before starting.
- `desktop_session_exec()`: exports DE variables, imports them into
  `systemctl --user`, and `exec`s the compositor/session manager.
- `desktop_session_stop()`: gracefully shuts down the user session before
  `openwrt-desktop.service` stops.

`openwrt-desktop-core` installs the default `gnome` plugin
(`/usr/libexec/openwrt-desktop/sessions.d/gnome`). Adding another Wayland
desktop (such as KDE Plasma) later requires only installing a matching plugin
(for example `sessions.d/plasma`) alongside its desktop packages; `desktop-ctl`
and `luci-app-desktop` discover it automatically.

## Lifecycle and Active-Session Tracking

- `/etc/config/desktop` stores `option session 'gnome'` (defaulting to `gnome`
  when absent).
- When `/etc/init.d/desktop start` launches `openwrt-desktop.service`, it
  passes `OPENWRT_DESKTOP_SESSION` to `/usr/libexec/desktop-session` and
  atomically writes `/run/openwrt-desktop/active.env` (`ACTIVE_SESSION`,
  `ACTIVE_USER`, `ACTIVE_KMS_SCHEDULING`, `ACTIVE_OUTPUT`, `ACTIVE_MODE`).
- `/usr/libexec/desktop-session` collects `SESSION_UNSET_VARS` from all
  registered plugins, clears them from both the process and `systemctl --user`,
  runs `/usr/libexec/desktop-keyring-unlock` (preserving TPM2 SRK unlock) and
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

## Future KDE Plasma Notes

When a second DE (such as KDE Plasma) is ported:

1. Install `/usr/libexec/openwrt-desktop/sessions.d/plasma` with
   `SESSION_EXEC="/usr/bin/startplasma-wayland"` and
   `SESSION_UNSET_VARS="KDE_FULL_SESSION KDE_SESSION_VERSION KDE_SESSION_UID"`.
2. Migrate shared user units (`openwrt-fcitx5.service`,
   `openwrt-audio-session.target`, `sunshine.service`) from
   `gnome-session.target` to `graphical-session.target` while keeping
   `openwrt-gnome-remotes.service` attached to `gnome-session.target`.
3. Disable KWallet's Secret Service backend so KDE applications share the
   TPM2-unlocked `gnome-keyring-daemon` over `org.freedesktop.secrets`.

## Validation

See [desktop session switcher validation](desktop-session-switcher-validation.md).
