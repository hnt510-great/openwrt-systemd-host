# Plan: pfSense-style configuration revision history (`uci-history`)

Status: implemented 2026-11-06. The guide is `docs/uci-history.md`; the validation record
`docs/uci-history-validation.md` lists the completed checks and their scope.

## Context

pfSense records every configuration change as a numbered revision, with a timestamp, the user and a
description, and lets you diff and restore any of them from the GUI. This fork's router is also the
desktop, VM and container host, so one bad UCI change has a large blast radius. OpenWrt only has
LuCI's 90-second apply/rollback (rpcd, in-memory, one change at a time) and whole-system backup
tarballs. There is no history, no diff, no attribution and no safe way for a remote operator to make
a risky change.

Goal: a package that

1. snapshots `/etc/config` plus a few configured extra paths into a local, root-only git history on
   every change, whether it came from LuCI, the `uci` CLI, an editor, APK or a boot-time uci-defaults
   script;
2. shows the revisions as a log, a structured UCI-level diff and a restore, both from LuCI and from a
   CLI;
3. is easy for AI agents to operate over SSH: JSON output, stable exit codes, no prompts,
   secret masking by default, a self-describing command schema, and a **begin → change → verify →
   confirm** transaction that reverts itself automatically if the agent locks itself out.

Decisions already made with the user:

- **No sudoers change.** Agents run the tool with whatever root access the user grants
  (`sudo -n` fails fast; it never hangs on a prompt).
- **Scope:** `/etc/config` plus configurable extra paths. Extras are restored as files, without a
  service reload.
- **rpcd patch** for LuCI/ubus attribution and rollback tagging.

## Components

### 1. `package/custom/uci-history` (new). CLI, units, hooks

`Makefile`: `PKG_VERSION:=1.0.0`, `PKG_RELEASE:=1`, `Build/Compile` empty.
`DEPENDS:=@OPENWRT_SYSTEMD +python3-light +git` (check that `python3-light` provides `json`, `fcntl`
and `subprocess`; otherwise use `+python3` as `kernelctl` does). `conffiles`: `/etc/config/uci-history`.

Files:

| File | Purpose |
|---|---|
| `files/uci-history` → `/usr/sbin/uci-history` | Python CLI. All logic lives here and can be loaded by host tests through `importlib` (the same pattern as `kernelctl` in `scripts/tests/test-kernel-upgrade.py`). |
| `files/uci-history.config` → `/etc/config/uci-history` | `option enabled 1`, `option default_timeout 300`, `list extra_path '/etc/sysupgrade.conf'`, `list extra_path '/etc/nftables.d'`, `list extra_path '/etc/crontabs'` |
| `uci-history.path` | `PathChanged=/etc/config` → `uci-history-snapshot.service` |
| `uci-history-snapshot.service` | oneshot `uci-history snapshot --auto` (settles until `/etc/config` has been quiet for 1 s, with a 10 s cap) |
| `uci-history-sweep.timer` | every 15 min plus `OnBootSec`; captures changes to the extra paths, which the path unit cannot watch recursively |
| `uci-history-events.service` | long-running `uci-history listen`: reads `ubus listen uci.apply uci.commit uci.confirm uci.rollback` and writes attribution hints to `/run/uci-history/hints/` |
| `uci-history-boot.service` | captures any uci-defaults/sysupgrade changes as `source=boot`, and reverts a transaction that was still armed when the system went down (its transient timer is lost on reboot) |
| `files/apk.hook` → `/lib/apk/commit_hooks.d/80-uci-history` | pre-commit writes an `apk` hint; post-commit runs `snapshot --source apk` (same hook pattern as `lan-apk-feeds.hook` and `needrestart.hook`) |
| `keep.d` → `/lib/upgrade/keep.d/uci-history` | `/etc/uci-history/` survives sysupgrade |
| `files/AGENT-GUIDE.md` → `/usr/share/doc/uci-history/` | printed by `uci-history guide` |

Postinst/prerm follow `openwrt-needrestart/Makefile` (daemon-reload; start/stop the path unit, the
timer and the events service). The units are enabled through `multi-user.target.wants` symlinks.

### 2. Storage model (`/etc/uci-history/`, mode 0700 root)

- `repo/`: a bare git repository. A snapshot builds a tree with a temporary `GIT_INDEX_FILE` and
  `--work-tree=/`, using the pathspecs `etc/config` plus the extra paths and excluding
  `etc/config/.*` (libuci's temporary files). The snapshot is a no-op when the tree equals HEAD.
- Each commit carries a `.meta.json` blob in its tree (mode/uid/gid per file) and commit trailers:
  `Revision: N` (monotonic; restores never rewrite history), `Source:`
  (`cli|luci|ubus|rpcd-rollback|apk|boot|external|restore|txn-revert`), `Actor:`, `Note:`,
  `Transaction:`, `Configs:` (the changed packages).
- `txn.json`: the active transaction (id, checkpoint revision, deadline, actor, note, revert unit).
- The extra-path deny list rejects anything outside `/etc`, plus `/etc/shadow`, `/etc/gshadow`,
  `/etc/uci-history` and the signing keys.
- `/run/uci-history.lock` is a flock that serializes every writer.

### 3. CLI surface (agent-first)

Global flags: `--json` (or `UCI_HISTORY_JSON=1`), `--show-secrets` (never the default),
`--root DIR` (for tests only).

| Command | Effect |
|---|---|
| `status` | head revision, uncaptured drift on disk, staged-but-uncommitted uci deltas (`/tmp/.uci`, rpcd session savedirs), active transaction, pending rpcd rollback (`/var/run/rpcd/snapshot-files`) |
| `log [--limit N] [--config X] [--since T]` | list of revisions |
| `show REV [--config X]` | file contents at a revision, masked |
| `diff [REV_A] [REV_B] [--config X] [--format unified\|uci]` | the default `uci` format is a structured list of `{config, section, type, option, op, old, new}`; secrets show only `"changed"` |
| `snapshot [--note] [--actor] [--source]` | manual or auto capture |
| `restore REV [--config X ...] [--path P ...] [--dry-run] [--timeout S] [--no-reload]` | atomic writes (tmp + rename, original mode and ownership), records a new revision with `source=restore`, then runs `/sbin/reload_config` and reports the triggered packages and the extra paths that need a manual reload |
| `begin [--timeout S] [--note] [--actor]` | checkpoints the current state and arms a revert with `systemd-run --unit uci-history-revert-<id> --on-active=S`. Auto-snapshots taken while it is active inherit its actor, note and id. |
| `confirm` / `abort` | disarm and record the final revision / revert to the checkpoint now |
| `prune --keep N` | rebuilds history while keeping the revision-number trailers; `git gc` |
| `commands` | machine-readable JSON schema of commands, arguments and exit codes |
| `guide` | prints `AGENT-GUIDE.md` |

Agent safety rules:

- Nothing ever prompts.
- If the caller is not root, the tool exits **77** with a JSON error.
- When `SSH_CONNECTION` is set and a restore touches `network`, `firewall`, `dhcp`, `wireless` or
  `dropbear`/`sshd`, the tool requires `--timeout` or `--no-safety`.
- `begin` and `restore` refuse with exit **3** while another transaction or an rpcd rollback is
  pending.
- A restore refuses staged uci deltas for the affected configs unless `--discard-staged` is given.

Exit codes: 0 ok, 1 runtime error, 2 usage, 3 conflict, 4 revision/config not found,
10 transaction already reverted (confirmed too late), 77 not root.
Every JSON response has the shape `{"schema_version":1,"ok":bool,...,"error":{"code","message"}}`.

The UCI parsing used for the structured diff is done in Python: there is no host `uci` binary in
`staging_dir`, and parsing in Python keeps the host tests hermetic. It handles quoting, `list`
lines and anonymous sections (keyed as `@type[i]`, the same as `uci show`). Secrets are any option
whose name matches `key|psk|password|passwd|secret|token|private_key|preshared_key|auth_secret|pin`
as a full word or `_` suffix.

### 4. rpcd attribution patch

New `package/system/rpcd/patches/100-ubus-uci-apply-events.patch` (the rpcd directory has no
`patches/` yet), plus a bump of `PKG_RELEASE` 5→6 in `package/system/rpcd/Makefile`. In
`uci.c`, `ubus_send_event` broadcasts:

- `uci.apply`: `{configs[], username, rollback, timeout}`
- `uci.commit`: `{config, username}`, from `rpc_uci_revert_commit`
- `uci.confirm`
- `uci.rollback`: `{configs[], reason: "timeout"|"request"}`, from `rpc_uci_do_rollback`

The username comes from a small `rpc_session_username(sid)` helper added to
`session.c`/`include/rpcd/session.h` (`rpc_reclaim_apply_session` already reads the `username`
session datum the same way). The patch only adds events and changes no behavior. The listener in
`uci-history` matches hints by config set and a timestamp window of 30 s or less; changes without a
hint are recorded as `source=external`. Regenerate the patch with `make package/rpcd/refresh`.

### 5. `package/custom/luci-app-uci-history` (new)

Copies the layout of `luci-app-needrestart`:

- `root/usr/share/rpcd/ucode/luci.uci-history`. Methods: `status`, `log`, `diff`, `restore`,
  `confirm`, `abort`. Each one runs `popen` on `/usr/sbin/uci-history --json` with a fixed argv;
  arguments are validated by regex (revision `^[0-9]+$`, config `^[a-z0-9_-]+$`) and the output is
  size-capped.
- An ACL with a read scope (status/log/diff) and a write scope (restore/confirm/abort).
- A menu entry at `admin/system/uci-history`, "Configuration History", that depends on the
  executable `/usr/sbin/uci-history`.
- The view `view/system/uci-history.js`: a revision table (rev, time, actor, source, note, configs);
  a diff panel (structured UCI rows, with a toggle for unified diff); and a restore action with
  per-config checkboxes. A restore from LuCI is armed with `--timeout L.env.apply_rollback` and
  confirmed by the view once the browser can still reach the router, mirroring LuCI's
  `changes.confirm` flow in `luci-base/ui.js`.
- `po/templates`, `po/zh_Hans`.

### 6. Wiring and documentation

- Register `uci-history` and `luci-app-uci-history` as `provider: local` entries in
  `configs/custom-package-updates.json`.
- New fragment `configs/uci-history.config` with both `CONFIG_PACKAGE_…=y`. After review, merge it
  into the working `.config` and the snapshot `configs/x86-64-systemd-desktop.config` (`kconfig.pl`
  + `make defconfig`).
- `docs/uci-history.md` (English guide: concepts, CLI table, UCI options, LuCI page, recovery
  steps, an **"Operating with AI agents"** section) and `docs/uci-history-validation.md`
  (hand-written after testing).
- Add a short "Changing router configuration" rule to `AGENTS.md`, `CLAUDE.md` and `GEMINI.md`:
  over SSH, use `uci-history begin --timeout …` → change → verify → `confirm`; read state with
  `status/log/diff --json`; never pass `--show-secrets` into transcripts.

## Critical files

- New: `package/custom/uci-history/**`, `package/custom/luci-app-uci-history/**`,
  `package/system/rpcd/patches/100-ubus-uci-apply-events.patch`, `configs/uci-history.config`,
  `docs/uci-history{,-validation}.md`, and the tests listed below.
- Modified: `package/system/rpcd/Makefile`, `configs/custom-package-updates.json`, `AGENTS.md`,
  `CLAUDE.md`, `GEMINI.md`, and later `.config` and the snapshot config.
- Reference and reuse: `package/custom/openwrt-needrestart/Makefile` (units, postinst),
  `package/custom/luci-app-needrestart/**` (ucode RPC, ACL, menu, view),
  `package/custom/lan-apk-feeds/files/lan-apk-feeds.hook` (APK hook),
  `scripts/apply-elf-migration.py:164` (the `systemd-run --on-active` rollback timer pattern),
  `package/system/procd/files/reload_config` (the reload mechanism), and
  `rpc_uci_trigger_event`, `rpc_uci_apply`, `rpc_uci_confirm` and `rpc_uci_do_rollback` in the
  unpacked rpcd source `build_dir/target-x86_64_glibc/rpcd-*/uci.c` (a build artifact, not tracked).

## Verification

1. **Host unit tests:** `python3 scripts/tests/test-uci-history.py` loads the CLI with `--root`
   pointed at a temporary tree, with PATH shims for `reload_config`, `systemd-run`, `systemctl` and
   `ubus`. It covers:
   - a no-op snapshot and monotonic revisions
   - the UCI parser (quotes, lists, anonymous sections)
   - the structured diff and secret masking
   - restore: atomic writes, preserved mode, partial restore, refusal of staged deltas, the SSH
     safety gate
   - transactions: begin/confirm/abort, timeout revert, a stale transaction at boot
   - hint attribution: LuCI user, rpcd rollback, APK
   - prune keeping revision numbers, the extra-path deny list
   - the JSON schema and exit code of every command, the `commands` output
2. **LuCI:** `python3 scripts/tests/test-luci-uci-history.py` (the real ucode backend through
   `staging_dir/hostpkg/bin/ucode` with a stub CLI, checking argv validation and size caps) and
   `node scripts/tests/test-luci-uci-history-view.js` (DOM/RPC fixtures, in the style of
   `test-luci-needrestart.js`).
3. **Builds:** `make package/system/rpcd/{clean,compile} V=s`,
   `make package/custom/uci-history/compile V=s`,
   `make package/custom/luci-app-uci-history/compile V=s`, `scripts/checkpatch.pl` on the rpcd
   patch, and `git diff --check`.
4. **VM gate:** `scripts/tests/test-uci-history-vm.py`, modeled on `test-daed-vm.py` and reusing
   `scripts/test-image-network.py`, on a freshly built exact image (router + client, never the
   physical router). It checks:
   - `uci set` + `commit` produces a revision with `source=cli`
   - a LuCI-style `ubus call uci apply` produces a revision attributed to the session user, and
     letting it time out produces an `rpcd-rollback` revision
   - `begin --timeout 60` → change the LAN IP → the client loses access → the automatic revert
     restores access, and the client can reach LuCI again
   - `restore` of an older revision followed by `diff` shows no difference
   - a reboot with an armed transaction reverts at boot
   - the history survives a sysupgrade with kept config
5. Write `docs/uci-history-validation.md` with the image SHA-256, the check table, the scope ("no
   physical device was flashed") and the evidence directory.
