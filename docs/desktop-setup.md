# LuCI desktop setup wizard

`luci-app-desktop-setup` enrolls an ordinary user for the shared GNOME desktop
and selected application features. The permanent entry is **System → Desktop
Setup Wizard**, `/cgi-bin/luci/admin/system/desktop-setup`. The English UI has
a Simplified Chinese translation in `luci-i18n-desktop-setup-zh-cn`.

## First visit and later access

On a native-systemd image, the LuCI status overview redirects an authorized
administrator to the wizard until initial setup completes. The overview
checks write access to the wizard RPC before redirecting; read-only accounts
are not forced into enrollment. It does not replace LuCI authentication.

Prepare the router's LAN IPv4 address and administrator password first. Use
HTTPS when entering account credentials. GNOME also needs its normal graphics
and display prerequisites. Recovery boots do not redirect or configure GNOME.

**Skip setup** is available on the Account, Features and Review pages without
completing any fields. It returns to the overview and suppresses future automatic
entry without creating an account or applying desktop configuration. The permanent System menu
and overview link remain available. Completion and deferral are device-wide,
not per-browser settings. `/etc/desktop-setup/state.json` participates in
configuration-preserving sysupgrade backups; a clean flash starts fresh.

## Workflow

1. **Account:** create a new ordinary user or select an eligible existing user.
   New usernames use 1–32 lowercase letters, digits, `_` or `-`, starting with
   a letter or `_`. New account/RDP passwords require at least 12 characters.
2. **Features:** select RDP, Sunshine/Moonlight, rootless containers, per-user
   Flatpak and virtual-machine administration. Choose portal or explicit KMS
   capture. Features whose helper is missing are unavailable.
3. **Review:** check the account and permissions, then explicitly confirm the
   GNOME start/restart. This closes current desktop applications. The wizard
   does not change router network settings or restart the router.
4. **Result:** a background worker reports each completed/failed step. The page
   can be closed and reopened while work continues. On success it supplies the
   RDP address and TLS fingerprint, Sunshine link and follow-up instructions.

Existing unlocked users retain their system passwords and home data. If an
existing login keyring has no unattended bootstrap credential, the wizard
asks for its current passphrase. Existing RDP credentials can be kept by
leaving that field blank only when RDP is already configured for the same user.

The wizard configures one active desktop account, matching the main desktop
integration. Choosing another account changes that active desktop user;
previous user data remains. Unchecked features retain existing settings and
permissions: this is enrollment, not a permission-revocation interface.

## Operations and permissions

| Step | Existing helper or operation |
| --- | --- |
| Account creation | Shadow `useradd -m -U`, then SHA512 `chpasswd` with stdin |
| GNOME | `desktop-setup USER --keyring-password-stdin` |
| RDP | `desktop-rdp-setup USER --password-stdin` |
| RDP-only audio | `desktop-audio-setup USER` |
| Moonlight | `sunshine-setup USER --capture=portal` or `--enable-kms` |
| Containers | `podman-rootless-setup USER`, plus a deduplicated LuCI Podman allowlist entry |
| Flatpak | `flatpak-user-setup USER` |
| Virtual machines | `virt-manager-setup USER` |
| Activation | Restart the desktop and check its native systemd service |

Container enrollment allocates subordinate IDs and enables user linger. VM
enrollment grants the existing `libvirt-admin` role with privileges comparable
to root. KMS enrollment grants the Sunshine executable its existing capture
capability. These effects appear in the UI before applying. The wizard does
not add the user to `sudo`.

For a new account, VM groups are granted before the first GNOME/PAM session.
For an existing account, re-login to obtain updated groups. A running user
manager can retain old groups: the result page reports this when detected.
Restart that manager or reboot during maintenance to refresh all user services;
the wizard never terminates it or existing containers to force a refresh. Moonlight still requires
Sunshine Web credentials, PIN pairing and, for portal capture, any initial
screen-selection grant. Add Flatpak remotes/applications, container images and
VM definitions separately. See [GNOME](gnome-desktop.md),
[Podman](podman-rootless.md), [Flatpak](flatpak.md) and [VM management](virt-manager.md).

## Failure and retry

Account creation, password setup, feature helpers and activation have separate
progress records. Failure leaves completed changes in place; there is no
rollback that deletes accounts, homes, containers or VM data. Select the
existing account on retry. A locked account created by a failed wizard run
can finish password enrollment without being recreated. Other locked/system
accounts are not offered for reuse.

Only one apply/deferral operation can run at a time. A lost worker releases
its lock; the status API then reports an interrupted job. A reboot clears
volatile progress but preserves wizard-created account metadata, completion
and deferral. Refresh status and inspect the existing account before retrying.

Runtime jobs are in root-only `/run/desktop-setup/`. RPC request passwords are
not written to progress files, command arguments or logs. Helpers receive
secrets over stdin; the existing integrations still store the account hash,
RDP credentials in the user keyring, and the root-only keyring bootstrap
credential in their intended locations. The RPC exposes only `status`, `apply`
and `defer`, not arbitrary commands or file access. Delegating its write ACL
is an administrator-level grant.

If an existing saved keyring bootstrap becomes invalid after a manual
keyring passphrase change, repair it with the existing root CLI:
`desktop-setup USER --refresh-keyring`. The wizard preserves an existing
bootstrap rather than silently replacing it.

## Configuration and build

The GNOME fragment and full saved desktop configuration select the wizard and
Chinese translation. For an existing build configuration, merge its fragment
without replacing other selections:

```sh
./scripts/kconfig.pl + .config configs/desktop-setup.config > .config.setup
mv .config.setup .config
make defconfig
./scripts/feeds update -i custom
make package/custom/luci-app-desktop-setup/compile V=s
```

The app selects its helper/UI dependencies. `openwrt-desktop` release 26 adds
the non-interactive existing-keyring input option while retaining its original
interactive CLI behavior. A live package installation must use that release
or newer, plus matching dependencies from this project's signed APK source.
The LuCI package's normal post-install hook refreshes rpcd.

Source and frontend checks:

```sh
python3 scripts/tests/test-desktop-setup.py
node scripts/tests/test-luci-desktop-setup.js
python3 scripts/tests/desktop-rdp-config.py
python3 scripts/tests/test-gnome-keyring.py
python3 scripts/tests/test-sunshine-gnome.py
python3 scripts/tests/test-custom-package-updates.py
```

See [validation](desktop-setup-validation.md) for actual build evidence and
checks still required on a fresh guest and physical device.
