# HEMS Security Audit Report

**Date**: 2026-03-07
**Scope**: Full codebase — services/*, infra/*, config files
**Tools**: Bandit 1.9.x, Semgrep (auto config, 501 rules), manual code review
**Auditor**: Automated + manual penetration test checklist

---

## Executive Summary

The HEMS codebase has a solid security posture for a single-occupant home system. The backend API uses constant-time API key comparison (`secrets.compare_digest`), MQTT has per-service ACLs with least-privilege topic permissions, and the brain's sanitizer uses a whitelist approach for command execution. However, several issues were identified — most critically, bridge services lack authentication on sensitive endpoints.

**Fixed in this commit**: 5 issues (marked with [FIXED])
**Remaining**: 7 issues requiring design decisions or larger changes

---

## Findings

### CRITICAL

#### C1. Bridge Services Lack Authentication [Remaining]
**Affected**: `openclaw-bridge`, `ha-bridge`, `obsidian-bridge`, `gas-bridge`, `biometric-bridge`, `perception`
**Location**: All `services/*/src/main.py` — no auth middleware on REST endpoints
**Description**: All bridge services expose REST APIs (command execution, device control, note writing, biometric data) without any authentication. While these are internal Docker network services not directly exposed to the internet, any service or container on the Docker network can call them.

Most critically, `openclaw-bridge` exposes:
- `POST /api/pc/command` — arbitrary shell command execution (`services/openclaw-bridge/src/main.py:146`)
- `POST /api/pc/browser/eval` — arbitrary JavaScript execution (`services/openclaw-bridge/src/main.py:184`)
- `POST /api/pc/process/kill` — process termination (`services/openclaw-bridge/src/main.py:217`)

The brain's sanitizer allowlist (`services/brain/src/sanitizer.py`) only validates at the brain layer — direct HTTP calls to the bridge bypass all safety checks.

**Severity**: Critical
**Remediation**: Add shared API key authentication to all bridge REST endpoints (similar to backend's `verify_api_key`). At minimum, add auth to openclaw-bridge's command execution endpoints.

---

### HIGH

#### H0. Path Traversal in Voice Service Audio Endpoint [FIXED]
**Location**: `services/voice/src/main.py:119-124`
**Description**: The `/audio/{filename}` endpoint passed the filename directly to `AUDIO_DIR / filename` without validating path components. An attacker could request `/audio/../../../etc/passwd` to read arbitrary files on the filesystem.
**Fix**: Added `path.resolve()` check ensuring the resolved path stays within `AUDIO_DIR`.

#### H1. `env` Command in Sanitizer Allowlist Leaks Secrets [FIXED]
**Location**: `services/brain/src/sanitizer.py:38`
**Description**: The `env` command was permitted in the PC command allowlist, allowing the LLM to execute `env` and read all environment variables — including `HEMS_API_KEY`, `HA_TOKEN`, `GITHUB_TOKEN`, `GMAIL_APP_PASSWORD`, and MQTT credentials.
**Fix**: Removed `env` from the allowed command patterns.

#### H2. Containers Running as Root [FIXED]
**Location**: All `services/*/Dockerfile` (10 Dockerfiles)
**Description**: All service containers ran as root. If an attacker compromises a service, they have root access within the container, potentially enabling container escape or host filesystem access (especially `openclaw-bridge` which uses `pid:host`).
**Fix**: Added non-root `appuser` to all Python service Dockerfiles.

#### H3. Missing Security Headers on Frontend [FIXED]
**Location**: `services/frontend/nginx.conf`
**Description**: No security headers were set. Missing `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, and `Permissions-Policy` headers.
**Fix**: Added all five security headers to nginx config.

---

### MEDIUM

#### M1. Biometric Webhook Authentication Optional [Remaining]
**Location**: `services/biometric-bridge/src/main.py:22-32`
**Description**: `BIOMETRIC_WEBHOOK_SECRET` defaults to empty, disabling HMAC signature verification on the webhook endpoint. An attacker on the same network can inject fake biometric data (heart rate, sleep, stress) which could trigger automated actions (lights off, climate changes) via brain rules.
**Severity**: Medium
**Remediation**: Make `BIOMETRIC_WEBHOOK_SECRET` required (fail startup if unset) or generate a random secret on first run.

#### M2. SQL Injection via Table Prefix f-strings [Remaining]
**Location**: `services/brain/src/event_store/aggregator.py:60,67,96,111,138,155,225,231` and `writer.py:144,156,168,184`
**Description**: SQL queries use f-string interpolation for the table prefix (`{tp}`). While the prefix comes from an internal config constant (not user input), this pattern is fragile — a misconfigured `EVENT_STORE_TABLE_PREFIX` env var could enable SQL injection.
**Severity**: Medium (Low exploitability — internal config only)
**Remediation**: Validate the table prefix at startup (alphanumeric + underscore only), or use SQLAlchemy table objects instead of raw text queries.

#### M3. Error Messages Expose Internal Details [Remaining]
**Location**: `services/openclaw-bridge/src/main.py:155,167,181,192,213,230`
**Description**: Exception messages are passed directly to HTTP responses via `raise HTTPException(500, str(e))`. This can leak internal paths, stack details, or service names to callers.
**Severity**: Medium
**Remediation**: Return generic error messages in HTTP responses; log full exceptions server-side only.

#### M4. Backend IDOR — No Resource Ownership Checks [Remaining]
**Location**: `services/backend/routers/tasks.py` (accept/complete/dispatch endpoints), `services/backend/routers/points.py` (grant endpoint)
**Description**: Task and point endpoints don't validate that the authenticated user owns the resource. Any valid API key holder can accept, complete, or dispatch any task, and grant arbitrary points to any user. Mitigated in the current single-occupant design but would become a privilege escalation vector if multi-user support is ever added.
**Severity**: Medium (Low in current single-user context)
**Remediation**: Add ownership validation if multi-user support is planned.

#### M5. No Rate Limiting on API Endpoints [Remaining]
**Location**: `services/backend/main.py`
**Description**: The backend API has no rate limiting. While protected by API key auth, a compromised key allows unlimited requests. The brain sanitizer has rate limiting for task creation (10/hour) and speak cooldowns, but the backend REST API itself is unbounded.
**Severity**: Medium
**Remediation**: Add rate limiting middleware (e.g., `slowapi`) to the backend, especially for write endpoints.

---

### LOW

#### L1. Insecure WebSocket Default URL [Remaining]
**Location**: `services/openclaw-bridge/src/config.py:9`
**Description**: Default OpenClaw Gateway URL uses `ws://` (unencrypted). On a LAN this is acceptable, but credentials/commands are sent in plaintext.
**Severity**: Low
**Remediation**: Document that `wss://` should be used if the gateway is not on localhost/LAN.

#### L2. MQTT Credentials in Docker Environment [Informational]
**Location**: `infra/mosquitto/setup-users.sh`
**Description**: MQTT uses per-service credentials with ACL-based topic isolation (good). The setup script generates strong passwords. The `service-passwords.env` file is correctly marked as secret. No issues found — this is well-implemented.

---

## Positive Findings (No Issues)

| Area | Assessment |
|------|-----------|
| **API Key Auth** | Uses `secrets.compare_digest` for constant-time comparison. Rejects requests when key is unset (503). All routers gated. |
| **CORS** | Explicit origin list, not wildcard. Credentials require specific origins. |
| **Command Sanitizer** | Whitelist approach — only known-safe commands pass. Regex patterns validated. |
| **Browser Control** | `eval` action blocked at brain sanitizer level. Only `navigate`, `get_url`, `get_title` allowed. |
| **Path Traversal (Obsidian)** | `note_writer.py` resolves symlinks and verifies path stays within vault. Writes restricted to `HEMS/` subdirectory. |
| **MQTT ACLs** | Per-service users with least-privilege topic permissions. `allow_anonymous false`. |
| **HA Bridge Validation** | Dangerous domains blocked (`shell_command`, `script`, etc.). Parameter ranges validated. |
| **Prompt Injection** | `sanitize_llm_text()` strips known injection patterns from sensor-derived text. |
| **XSS** | React frontend (auto-escapes by default). No `dangerouslySetInnerHTML` usage found. |
| **Subprocess Usage** | `rule_engine.py` uses `subprocess.check_output` with list args (no shell injection). `espeak.py` uses `create_subprocess_exec` with list args. No `shell=True` anywhere. |

---

## Scanner Results Summary

### Bandit (Python Static Analysis)
- **High severity**: 0
- **Medium severity**: 15 (all SQL f-string interpolation in event_store — internal config variable, not user input)
- **Low severity**: 13 (assert usage, try-except-pass)

### Semgrep (501 rules)
- **30 findings total**
- 10x `dockerfile.security.missing-user` [FIXED]
- 16x `sqlalchemy.security.audit.avoid-sqlalchemy-text` (same as bandit M2)
- 3x `nginx.security.missing-internal` (proxy_pass without `internal` — by design, these are frontend-facing proxies)
- 1x `detect-insecure-websocket` (L1 above)

---

## Recommendations Priority

1. **[Critical]** Add authentication to bridge service REST endpoints (especially openclaw-bridge)
2. **[Medium]** Make `BIOMETRIC_WEBHOOK_SECRET` required
3. **[Medium]** Sanitize error responses in bridge services
4. **[Medium]** Add table prefix validation at event_store startup
5. **[Low]** Add rate limiting middleware to backend API
