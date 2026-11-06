# Changing router configuration with an AI agent

Use existing authorized root access (`sudo -n`; never request a password).
All responses are JSON with schema_version=1, ok and error. Prefer --json before
commands. Never use --show-secrets in transcripts. History contains real secrets
on disk; preserve the root-only permissions and protect backups accordingly.

1. `uci-history --json status`: inspect drift, staged changes and pending rollback.
2. `uci-history --json begin --timeout 300 --actor agent --note 'purpose'`.
3. Make the narrowly scoped configuration change, commit, and reload as needed.
4. Independently verify connectivity and the intended service behavior.
5. `uci-history --json diff` and `uci-history --json confirm` before the deadline.

If verification fails, run `abort`, or allow the deadline to revert automatically.
Do not confirm merely because the command succeeded. Timers survive SSH loss;
boot recovery reverts any persistent armed transaction after a reboot.
`restore REV --timeout 300` creates the same safety transaction. Extra paths are
restored without service reload and require manual acceptance. `--no-reload`
suppresses reload_config for UCI too. Atomicity is per file, not across files.

Use `commands` for the argument schema. Exit codes: 0 success, 1 runtime error,
2 usage, 3 conflict, 4 missing revision/config, 10 confirmation too late, 77 root
required. No command prompts. `log --since` accepts Unix epoch seconds.
