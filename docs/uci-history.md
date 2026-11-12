# Configuration revision history

`uci-history` records committed configuration files in a local Git journal and
provides timed recovery for configuration changes. Select
`configs/uci-history.config` on a native systemd image. The companion LuCI page is
**System → Configuration History**. The package uses Python 3, Git, ubus and
systemd; it adds no sudoers rule and grants no additional root access.

## What is captured

The journal covers regular files in `/etc/config` (excluding hidden temporary
files), plus configured extra files/directories. It preserves contents, mode,
owner and group. Symlinks and special files are rejected. Empty directories,
ACLs, extended attributes and service runtime state are outside the journal.
APK `.apk-new` files, backup sidecars and nested files under `/etc/config` are
retained as opaque files, masked completely, and excluded from UCI package
diffs and reload selection. History is a bare repository in `/etc/uci-history/repo`; its parent is mode 0700
and new files use umask 0077. Real secrets remain in the repository. Keep its
permissions and protect sysupgrade backups as configuration credentials.

A path unit captures changes after one quiet second, with a ten-second settling
cap. A fifteen-minute sweep also captures extra paths; APK hooks snapshot after
transactions. Changes coalesced within the settling window form one revision;
this is a file-state journal, not an audit log of every UCI command. Identical
file contents and metadata produce no new revision. Captures include deletion.
A changed tree receives a monotonic revision trailer; restores append revisions.

Commit trailers record revision, time (Git commit timestamp), source, actor,
note, transaction ID and changed UCI packages. rpcd broadcasts apply/commit,
confirmation and rollback events with the configuration names and session
username, without session IDs. The listener matches exact package sets within
thirty seconds; an rpcd hint labels one capture, an APK hint its whole window. `uci.apply` is classified as `luci`, direct RPC commits as
`ubus`, and rollback as `rpcd-rollback`. APK provides its own hint. Unattributed
writes, including ordinary `uci commit` and editors, are `external`; a directory
watch cannot reliably identify the writer. Use an explicit CLI snapshot or a
transaction to record intentional attribution. Hints are best-effort, not a
security audit identity. During a transaction, snapshots inherit its actor,
note and ID. Boot, restore and transaction recovery have distinct sources.

## CLI

Global flags precede the command: `--json`, `--show-secrets`, `--root DIR`.
`UCI_HISTORY_JSON=1` also selects compact JSON. `--root` is a hermetic test
facility, not a way to manage a running alternate installation. Production
commands always require root, including when using `--root`.

| Command | Behavior |
| --- | --- |
| `status` | Head, uncaptured drift, current package names, staged delta paths, active transaction and rpcd rollback |
| `log --limit 50 --config network --since EPOCH` | Filtered revision list; `--since` is Unix seconds |
| `show REV --config network` | Masked configuration at a revision |
| `diff [A] [B] --config network --format uci` | Structured UCI changes; defaults to HEAD versus disk |
| `diff A B --format unified` | Unified file comparison, including extra paths |
| `snapshot --actor USER --note TEXT --source cli` | Explicit capture; `--auto` enables settling/hints and honors enabled |
| `restore REV --config network --timeout 300` | Restore selected packages, preserving permissions; repeat `--config` |
| `restore REV --path /etc/nftables.d --no-reload` | Restore configured extra paths; repeat `--path` |
| `restore REV --dry-run` | Preview affected packages and extra paths without restoring or arming a timer |
| `begin --timeout 300 --actor USER --note TEXT` | Capture checkpoint and arm automatic revert |
| `confirm [--id ID]` | Capture final state and cancel the matching timer |
| `abort [--id ID]` | Restore checkpoint now, reload UCI and cancel timer |
| `prune --keep 100` | Retain newest revisions, preserve revision numbers/timestamps and garbage collect |
| `commands` | JSON command/argument schema and exit codes |
| `guide` | Installed agent instructions |

`restore` without selectors restores the complete recorded scope. Selectors are
an inclusive union. Extra paths are restored as files and require a manual
service reload. `--no-reload` suppresses UCI reload too. Restore uses fsynced
same-directory temporary files and rename; atomicity is per file, not across the
whole restore. `reload_config` triggers UCI service events; command success does
not prove service health. Returned `configs` identifies affected UCI packages,
`triggered_configs` reports events inferred from reload_config's checksum lists
plus an explicit `config.change` event for every restored package reload_config
skipped (its baseline is its own last run, so a change applied with an init
script reload would otherwise never be reverted in the running service),
a transaction revert signals every package captured since its checkpoint, so a
retry after a failed reload still reaches the service,
`paths` identifies extra files, and `reload` reports invocation of the reload
mechanism. Previously committed drift outside the selection can also trigger
events through reload_config. A dry run reports the same affected paths without writes.

Every command response has `schema_version: 1`, `ok`, `error` (null on success)
and command-specific fields. Error objects contain numeric `code` and `message`.
Exit codes are 0 success, 1 runtime error, 2 usage, 3 conflict, 4 missing revision
or package, 10 confirmation after automatic revert, and 77 root required.
Commands never prompt. Human mode prints the same envelope with indentation.

Secrets are matched case-insensitively by option name, as a complete name or
underscore suffix: `key`, `psk`, `password`, `passwd`, `secret`, `token`,
`private_key`, `preshared_key`, `auth_secret`, `pin`, `passphrase`, `privatekey`,
`publickey`, `shortid`, `short_id`, `credentials`, `uuid` (covering Passwall/Xray
`uuid`, `reality_publicKey` and `reality_shortId`). `uuid` stays visible in `fstab`,
where it names a block device. A `credentials` entry of the form `NAME=value`
(acme.sh DNS API) keeps its name, e.g. `CF_Token=[redacted]`. Structured diffs expose only
`changed` for either secret value. Masked UCI text is normalized, with comments
omitted. Malformed text is redacted. Extra files have their complete contents
redacted by default because their formats are unknown. Metadata/secret-only
changes still have a marker in unified diffs. Never include `--show-secrets`
output in logs, tickets or agent transcripts.

## Safety transactions and recovery

`begin` captures the current disk state before scheduling a transient
`uci-history-revert-ID.timer` using `systemd-run --on-active`. The persistent
`txn.json` is written before timer creation; creation failure removes the marker.
A successful transaction is **begin → change → verify → confirm**. SSH loss does
not cancel the timer. A late confirmation reverts and returns exit 10. Matching
IDs prevent an old timer or browser from acting on a newer transaction.

At boot, `uci-history-boot.service` reverts an armed marker, even if its deadline
has not elapsed. Transient timers disappear across reboot; the marker is the
recovery authority. The transaction pins its capture settings so a malformed or
changed `/etc/config/uci-history` cannot prevent recovery. A failed restore or
reload keeps the marker for retry. Boot recovery retries on failure. A final
transaction receipt remains in `last-transaction.json`.

Begin and restore refuse while another transaction or rpcd apply rollback is
pending. Prune also refuses during pending rollback. Restore refuses staged UCI
deltas for affected packages from `/tmp/.uci` and rpcd savedirs, unless the caller
explicitly chooses `--discard-staged`; only the affected package delta files are
removed. Do not start another LuCI apply while a CLI transaction is armed: rpcd
has its own independent rollback mechanism. Watcher flock serializes history
writers, not arbitrary external configuration writers.

When `SSH_CONNECTION` is set, restoring `network`, `firewall`, `dhcp`, `wireless`,
`dropbear` or `sshd` requires `--timeout` or the explicit `--no-safety` override.
Use a timeout for remote operations. `--no-safety` grants no other bypass.

If the router is unreachable, wait for the timeout and retry its checkpoint
address. With console access, run `uci-history --json status`, then `abort` to
revert an armed transaction. Otherwise inspect `log`/`diff` and restore a known
revision. Do not edit the bare Git history or delete a live transaction marker.
If a service still fails, inspect its logs: file restoration does not guarantee
that every external service can reload successfully.

## Options and lifecycle

`/etc/config/uci-history` contains one `config history 'main'` section:

| Setting | Default | Meaning |
| --- | --- | --- |
| `option enabled` | `1` | Enable automatic captures; manual commands and recovery remain available |
| `option default_timeout` | `300` | Default begin deadline in seconds; permitted range 5–86400 |
| `list extra_path` | `/etc/sysupgrade.conf`, `/etc/nftables.d`, `/etc/crontabs` | Additional capture roots |

Extras must be below `/etc`; `/etc` itself, parent traversal, shadow/gshadow,
the history store, APK trust keys, SSH host-key directories, SSL private keys,
and signing/private-key names are refused. No parent may be a symlink. Keep SSH
server settings in their UCI package if they need journaled changes. A history
scope containing symlinks or unsupported files fails rather than silently
following them outside the declared scope.

The path unit disables its default dependencies and explicitly orders shutdown.
It starts after boot recovery: keeping the implicit ordering before
`paths.target/basic.target` would form a cycle through the OpenWrt rcS services.
Validate the complete `multi-user.target` graph when changing these units.

Post-install starts the boot capture, path unit, sweep timer and event listener
on a running systemd target. APK image construction skips live hooks. Removal
first aborts a pending transaction and then stops the units. The history itself
is retained; `/lib/upgrade/keep.d/uci-history` preserves it across kept-config
sysupgrade. This tree requires the procd recovery boot entry for actual firmware
flashing; native systemd permits image checks and backups. Return to native
systemd for normal automatic history capture and timed transactions. No pruning runs automatically; choose an explicit retention policy.

LuCI separates read (`status`, `log`, `diff`) and write (`restore`, `confirm`,
`abort`) ACLs. Its fixed-command backend validates arguments and caps responses
at 1 MiB with a thirty-second runtime limit. An empty package selection cannot
mean full restore. The page shows a revision table, structured/unified diff,
package checkboxes and a restore preview. A restore uses LuCI's rollback timeout,
waits its apply holdoff and confirms the same transaction only after a fresh
successful browser round trip. If that round trip fails, the timer stays armed.
Changing the LAN address may require reconnecting at the restored address and
confirming manually. A round trip establishes reachability, not complete service
acceptance; independently verify important services before CLI confirmation.

## Operating with AI agents

Use existing authorized root access, for example `sudo -n uci-history --json
status`. Do not change sudoers or ask for interactive passwords. Read `commands`
and `guide` when discovering the API. Start with status and ensure pending UCI or
rpcd changes belong to the task before proceeding.

```sh
sudo -n uci-history --json begin --timeout 300 --actor agent --note 'Adjust LAN DHCP'
# Make only the authorized UCI changes, commit and reload the relevant services.
# Verify actual client connectivity, DNS and the intended behavior independently.
sudo -n uci-history --json diff
sudo -n uci-history --json confirm
```

On failed verification, `abort` or let the timer expire. Do not confirm solely
because a subprocess returned success. Keep secrets masked, avoid competing
configuration writers, and report configuration capture, reload invocation and
functional acceptance separately. See [validation](uci-history-validation.md)
for the actual tested boundaries and the disposable-VM gate.
