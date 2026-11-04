# Chinese input in the shared GNOME session

`openwrt-desktop-ime` installs Fcitx5, Chinese addons, GTK input modules, Noto
Sans CJK and the GNOME Kimpanel extension. The saved desktop configuration
selects it. GNOME's native text-input path uses Fcitx's IBus compatibility
frontend; GTK3/GTK4 modules serve other clients.

## Build and enrollment

```sh
make package/custom/openwrt-desktop-ime/compile V=s
```

Create the ordinary desktop account and configure it with `desktop-setup USER`.
The session starts the enrolled user's `openwrt-fcitx5.service`. Its lifetime
follows GNOME, and `Restart=always` recovers a clean daemon exit while an
explicit session stop still stops it. Do not launch another Fcitx instance.

The setup helper preserves existing profiles, dictionaries and shortcuts.
Fresh profiles use **Ctrl+Space** as the primary trigger. In a text field,
activate Pinyin, type `nihao`, and press Space to commit `你好`. Existing
profiles may retain a different trigger, including Ctrl+Shift+Return.

The settings live in `${XDG_CONFIG_HOME:-$HOME/.config}/fcitx5/`; packaged
defaults are under `/usr/share/openwrt-desktop-ime/`. Use `fcitx5-remote -r`
inside the desktop after editing settings. Native Wayland and Flatpak clients
do not receive a forced global GTK input-module override.

## Remote clients

RDP and Moonlight send input to the same GNOME session. Keep the client input
source suitable for sending raw keys when composing with remote Pinyin. A
client OS may intercept Ctrl+Space; adjust the client shortcut or the Fcitx
trigger if needed. Reconnecting RDP preserves the active session and profile.

## Checks and evidence

Check the user service and journal inside the enrolled user's session:

```sh
systemctl --user status openwrt-fcitx5.service
journalctl --user -u openwrt-fcitx5.service
```

Validate candidate display and Chinese/ASCII commits separately in Shell,
GTK3, GTK4, Firefox and Xwayland, using both local and remote input. Current
observations are in [GNOME VM validation](gnome-desktop-validation.md) and the
[input-method follow-up](gnome-desktop-deployment-20261028.md#input-method-follow-up).
