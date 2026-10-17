# Ordinary-user authorization, sessions and services

The native x86_64/glibc/APK image includes systemd with polkit and PAM,
logind, PAM-enabled OpenSSH, BusyBox PAM console login, and a user D-Bus
service. The base packages create no ordinary account, password, key or
service grant. This checkout's personal firmware overlay provisions the
[desktop-user sudo account](multiuser.md) on first boot.
The existing seatd backend continues to control desktop display/input devices.
Logind tracks sessions; this integration does not provide udev device ACLs.

## Explicit service delegation

Root installs and reviews a native unit, then grants a named ordinary account
specific operations on its canonical service name:

```sh
systemd-access grant alice example.service start,stop,restart
systemd-access list
# In alice's SSH session:
systemctl start example.service
systemctl stop example.service
# As root:
systemd-access revoke alice example.service
```

Omitting the operation list grants start, stop, restart and reload. Rules match
the exact account, unit and operation. They do not grant enable/disable,
daemon-reload, manager configuration or arbitrary transient system services.
The helper rejects bare templates, aliases, transient units, non-root-owned
unit files/drop-ins and paths writable by other users. Root must also review
the service's executable, configuration and inputs: a delegated service that
executes user-controlled code with root privileges remains unsafe. Dependencies
and the unit's own start/stop hooks run normally.

Grants live in `/etc/polkit-1/rules.d/`, are reloaded by polkit and survive
configuration backups. File monitoring reloads rules asynchronously; allow
the reload to finish before issuing dependent automated requests.
Revocation affects subsequent requests; it does not
undo an operation already accepted. Existing polkit rules and temporary
administrator authorizations can add other permissions, so review custom
rules together with these grants and test revocation in a fresh login.

Operations without a grant use the action's normal polkit policy. The included
`pkttyagent` allows an interactive terminal to request root authentication;
`systemctl --no-ask-password` is appropriate for unattended requests that
must fail instead of prompting. There is no graphical authentication agent
or `pkexec` in this package. Router power actions and enabling lingering require
administrator authentication, including from a local active session.

Procd-managed UCI services retain `/etc/init.d` and ubus ownership. Do not
delegate `openwrt-procd.service` or `openwrt-services.service` merely to control
one router service: those units control the whole compatibility layer.
Libvirt's existing `libvirt-admin` UNIX socket authorization is unchanged;
this group grants full libvirt management. This integration does not enable
libvirt's polkit access-control driver or restrict VM operations by VM name.

## PAM and logind sessions

Native builds select `openssh-server-pam` instead of `openssh-server`, retain
the existing SSH listener/configuration and add `pam_systemd` to its session
stack. Password and public-key authentication still use the configured SSH
policy. Console login uses BusyBox PAM, with login sessions running as child
processes so PAM closes them on logout. The existing OpenWrt console root
autologin/`ttylogin` setting is retained.

`desktop-setup alice` still requires an existing, unlocked ordinary account
and creates its TLS VNC credentials. In native mode the desktop starts as
that user in a transient system service with a dedicated PAM stack. It shares
the logind-managed runtime directory and user D-Bus with that user's SSH
sessions. On systems with virtual terminals, the desktop activates VT 7.
Stopping `/etc/init.d/desktop` terminates the desktop's session and apps while
leaving separate SSH sessions and their shared user manager available.

Inspect the resulting sessions with:

```sh
loginctl list-sessions
loginctl session-status SESSION
loginctl user-status alice
```

Logind does not spawn extra gettys, handle power/lid keys, suspend the router,
or perform idle power actions. `KillUserProcesses=no` preserves the existing
behavior of background processes after SSH logout; those processes can keep
their closing session around. `RemoveIPC=no` preserves existing user IPC.
This policy does not promise immediate cleanup of arbitrary background jobs.

## User services and lifecycle

PAM creates `/run/user/UID` with mode 0700, exports `XDG_RUNTIME_DIR`, starts
`user@UID.service`, and supplies a user bus at `/run/user/UID/bus`. The user
manager reads units in `~/.config/systemd/user/`:

```sh
mkdir -p ~/.config/systemd/user
# Write your own example.service and example.timer here.
systemctl --user daemon-reload
systemctl --user enable --now example.timer
systemctl --user list-timers
systemd-run --user --unit=my-task --property=MemoryMax=128M \
    --property=TasksMax=32 /usr/bin/sleep 300
```

User services run with that user's privileges; starting one does not grant
root access. Memory, process and CPU limits use the delegated cgroup v2
controllers and depend on the kernel configuration. Runtime storage is bounded
to 64 MiB per user. Multiple sessions of one user share the manager and bus.
Normally the manager stops after the last session has gone and logind's stop
delay expires. A lingering user manager starts at boot and survives logout:

```sh
# Root explicitly opts an existing account in or out:
loginctl enable-linger alice
loginctl disable-linger alice
```

Linger markers are persisted in `/etc/systemd/linger/` and bind-mounted at
logind's canonical `/var/lib/systemd/linger` location (or `/tmp/lib/...` when
`/var` is volatile). Lingering services consume resources without an active
login; configure their resource limits explicitly. The base firmware opts in
no account. An administrator who explicitly enrolls an account for rootless
Podman with `podman-rootless-setup USER` performs that opt-in for the account
(see [Rootless Podman](podman-rootless.md)); `loginctl disable-linger USER`
still opts it back out.

## Recovery and build

The GRUB `procd recovery` and failsafe paths remain available. PAM session
registration is optional for SSH/console so login does not require logind
under procd. The desktop retains its previous procd, seatd and private D-Bus
startup path. Logind/polkit/user managers are native-mode facilities.

Enable `CONFIG_OPENWRT_SYSTEMD=y`, select the PAM OpenSSH variant, run
`make defconfig`, build the integration package and rebuild the full image.
BusyBox PAM, child login sessions and `chvt` are selected by native mode.
The OpenSSH PAM session change is maintained in
`feeds/packages/net/openssh/Makefile`, and native D-Bus socket activation is
enabled in `feeds/packages/utils/dbus/Makefile`. Preserve these feed-local
changes when updating feeds. System and user buses use standard socket
activation so both managers expose their systemd D-Bus interfaces. All new
target packages use the cross-toolchain; host tools are not replaced.
The Wayland profile in `feeds/video/frameworks/wayland/` also preserves an
existing PAM/desktop runtime directory instead of replacing it on shell login.

```sh
make package/system/systemd-openwrt/compile -j3 V=s
make -j3 V=s
```

Outputs are under `bin/systemd`. Before hardware deployment, verify fresh
native boot, allow/deny/revoke authorization, SSH and console sessions, user
service lifecycle and lingering, desktop/VNC, router services and a separate
procd recovery boot. A VM cannot establish physical HDMI/USB/NIC behavior.
The [2026-10-11 validation record](systemd-permissions-validation.md) covers
the rebuilt image, isolated VM acceptance and recovery/failsafe checks.
