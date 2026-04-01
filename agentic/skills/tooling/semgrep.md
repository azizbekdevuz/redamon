---
name: semgrep
description: Exact Semgrep CLI structure, metrics-off scanning, scoped ruleset selection, and automation-safe output patterns.
---

# Semgrep CLI Playbook

Official docs:
- https://semgrep.dev/docs/cli-reference
- https://semgrep.dev/docs/getting-started/cli

Canonical syntax:
`semgrep scan [flags]`

High-signal flags:
- `--config <rule_or_ruleset>` ruleset, registry pack, local rule file, or directory
- `--metrics=off` disable telemetry and metrics reporting
- `--json` JSON output
- `--sarif` SARIF output
- `--output <file>` write findings to file
- `--severity <level>` filter by severity
- `--error` return non-zero exit when findings exist
- `--quiet` suppress progress noise
- `--jobs <n>` parallel workers
- `--timeout <seconds>` per-file timeout
- `--exclude <pattern>` exclude path pattern
- `--include <pattern>` include path pattern
- `--exclude-rule <rule_id>` suppress specific rule
- `--baseline-commit <sha>` only report findings introduced after baseline
- `--pro` enable Pro engine if available
- `--oss-only` force OSS engine only

Agent-safe baseline for automation:
`semgrep scan --config p/default --metrics=off --json --output semgrep.json --quiet --jobs 4 --timeout 20 /workspace`

Common patterns:
- Default security scan:
  `semgrep scan --config p/default --metrics=off --json --output semgrep.json --quiet /workspace`
- High-severity focused pass:
  `semgrep scan --config p/default --severity ERROR --metrics=off --json --output semgrep_high.json --quiet /workspace`
- OWASP-oriented scan:
  `semgrep scan --config p/owasp-top-ten --metrics=off --sarif --output semgrep.sarif --quiet /workspace`
- Language-specific rules:
  `semgrep scan --config p/python --config p/secrets --metrics=off --json --output semgrep_python.json --quiet /workspace`

Critical correctness rules:
- Always include `--metrics=off`; Semgrep sends telemetry by default.
- Always provide an explicit `--config`.
- Prefer `--json --output <file>` or `--sarif --output <file>` for machine-readable output.
- Keep the target path explicit; use an absolute or clearly scoped workspace path.

Failure recovery:
- If scans are too slow, narrow the target path and reduce active rulesets.
- If scans time out, increase `--timeout` modestly or lower `--jobs`.
- If Pro mode fails, rerun with `--oss-only`.

If uncertain, query web_search with:
`site:semgrep.dev semgrep <flag> cli`
