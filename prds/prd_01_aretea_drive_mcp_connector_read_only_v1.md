# PRD 2: Aretea Drive MCP connector read-only v1

> **Status:** Active — Last refreshed: 2026-07-02

_Consolidates and **amends** the initial draft (root `prd-1`) into the house style. The one
material change from that draft is the FR2 amendment below (per-user identity), which needs
owner sign-off. Implementation detail (the *how*) lives in `docs/ARCHITECTURE.md`._

## Problem

Aretea's team works in Claude web chat and wants to query a curated set of company documents
that live in one Google Drive. The two off-the-shelf ways to connect Claude to Drive both fail:

- Claude's **native Drive connector** — and every managed gateway on a non-enterprise plan — uses
  **per-user OAuth**, so Claude inherits each individual's *full personal Drive* access. That is
  the wrong security boundary: it exposes everything a person can see, not a curated corpus.
- The gateways that *do* support a shared admin credential (MintMCP, TrueFoundry) are
  **enterprise-priced**.

After evaluating Composio, Nango, Docker MCP Gateway and others, none satisfies all of
{shared service-account credential + claude.ai web + curated corpus + EU processing +
non-enterprise cost} at once. This is also the **first of several planned connectors** (Slack,
HubSpot, Granola), so whatever pattern solves auth + hosting here is reused beyond Drive.

Additional symptom motivating the FR2 amendment: for a security company (MSSP) standing up a
reusable connector pattern, a design that cannot answer *"which person read which document"*
is a weak control to standardize on — yet the "zero-prompt" shape the draft assumed makes that
attribution structurally impossible.

## Goals

- All Claude **Team web** users get **read** access to one admin-defined Drive corpus.
- The security boundary is a **single service account's Drive membership**, not application logic.
- **No per-user Drive OAuth** and **no per-seat / third-party-gateway cost** in the data path.
- **Per-user attribution** of tool calls — the audit log answers *who read what, when* (amended goal).
- Structured so a **second connector** (Slack/HubSpot/Granola) is added as a new toolset behind
  the same auth front — no re-solving auth or hosting.
- Runs in an **EU region**.

## Non-Goals

- **All write/edit/delete/share/permission operations.** v1 is read-only. → later "write ops" PRD.
- **Higher read fidelity** (Google Sheets formulas, Slides structure/layout). v1 reads values and
  text only. → PRD "read fidelity".
- **Monitoring / usage analytics / dashboards / alerting.** Logs only; adoption judged by asking
  the team. → PRD "monitoring".
- **Per-user or per-group *data* access differentiation.** All-or-nothing at the org level (a
  platform limit, accepted). Identity is used for **attribution only, never to scope Drive data** —
  do not build application-layer data gating; it would be a false boundary.
- **Any drive** beyond the single AI-Visible Shared Drive.
- **Slack / HubSpot / Granola** connectors (future; design must not preclude them).
- **Claude Code / Desktop** as the target surface — this is a claude.ai **web** connector (it will
  also work in Code/Desktop, but that is not the requirement, and web is where the live risk is).

## Design

### Decisions (locked)

- **Self-hosted MCP server, Python + FastMCP.** No third-party gateway in the data path (NFR5).
- **Two-hop auth, decoupled (NFR2):** client hop establishes *identity*; drive hop is a fixed
  service account used inside tool execution. Neither hop uses domain-wide delegation.
- **Drive hop = service account, read-only, member of the AI-Visible drive only (NFR1).** Scopes
  `drive.readonly` + `spreadsheets.readonly` + `presentations.readonly`; **no `subject=`
  impersonation.** Membership is the primary boundary; a content-time `driveId` assertion is
  defense-in-depth (FR5).
- **Read-only tool surface (FR6):** search / get-metadata / read-content only; no mutation tool
  exists in the schema.
- **Org gate = "a valid Aretea identity."** Not a shared static secret — nothing static to leak,
  and revocation is per-user, not all-or-nothing.
- **Host:** Railway, **EU-West / Amsterdam** (NFR3); publicly reachable over HTTPS (NFR4).
- **Token store (amended — see A1):** FastMCP-native persistence via a `FileTreeStore`
  (`AsyncKeyValue`) on the Railway persistent volume, `FernetEncryptionWrapper` with a **fixed**
  encryption key. (FastMCP has **no SQLite storage backend**; the original "SQLite on a volume"
  wording is unbuildable.)
- **Regular-file fidelity:** text where trivial, metadata otherwise; PDF/Office extraction is a
  fast-follow, not v1.
- **Audit:** structured JSON per tool call → Railway platform logs (no dashboards).

**(NEEDS SIGN-OFF) FR2 amendment (FR2′).** Original FR2 said users are never *prompted to
authorize their own Google account*. We replace it with: **no per-user *Drive* authorization —
users get zero Drive scopes** (Drive hop stays 100% service-account) — **but a one-time
identity-only sign-in is accepted**, to obtain per-user attribution + per-user revoke. Rationale:
Anthropic mandates an interactive consent on every connection, so "zero prompt" was never
actually available; given a prompt is unavoidable, we spend it on identity. FR2-as-written becomes
false — **owner (Frederik) must acknowledge this as a spec change.** Test: a connected user's
Google account shows **no Drive grant**.

**(PENDING SPIKE) Client-hop authorization server = FastMCP `GoogleProvider`** (an `OAuthProxy`
DCR-face bundled with Google's token verifier; identity scopes `openid email profile` only).
FastMCP **mints and verifies its own bearer token** — no hand-rolled JWT (`JWT_SIGNING_KEY` = its
`jwt_signing_key`). Domain gate = **Google OAuth app set to Internal** (primary) + a server-side
`@aretea-group.com` email-suffix check (defense-in-depth); `hd`/`email_verified` are **not** in the
default claims (amendment A2). Plan-of-record, **contingent on the Phase-1 spike confirming each
Team user runs their own client-hop OAuth flow** carrying a distinct identity. If disproven,
attribution is impossible: audit degrades to org/session-level, the identity step is dropped (FR2
then stands unamended).

**(NEEDS SIGN-OFF) v1.1 stack-findings amendments.** A current-library spike (FastMCP 3.4.2, Google
client libs — see `ARCHITECTURE.md`) contradicts items written as *locked*. Each needs owner
(Frederik) acknowledgment, same as FR2′:

- **A1 — Token store is not SQLite.** FastMCP's `client_storage` is an `AsyncKeyValue` with **no
  SQLite backend**; OAuth token + client-registration persistence is native. Use **`FileTreeStore`
  on the volume + `FernetEncryptionWrapper`**. Adds a **second required secret** — a **fixed
  encryption key** — because Linux storage is ephemeral without one (tokens lost on restart),
  alongside `JWT_SIGNING_KEY`.
- **A2 — "No token issued" is Google-side, not our code.** `hd`/`email_verified` aren't default
  claims and the pre-mint reject hook is undocumented. AC3's "no token issued" rests on the **Google
  OAuth app = Internal (Workspace-only)** (a non-Aretea identity never receives an auth code); our
  email-suffix check is **post-mint** ("no data reachable"), not "no token." **AC3 retargeted.**
- **A3 — Per-user revoke is a Google-side action.** With no bespoke token DB, "revoke" = disable /
  remove the user's Workspace identity (consistent with A2). §2.5's "drop their tokens" is dropped
  as a code feature.
- **A4 — Double-consent risk to FR2′.** FastMCP's `require_authorization_consent` defaults **True**,
  adding its own consent screen atop Google's — FR2′ assumes exactly one unavoidable prompt.
  Decision needed: remember/off (note the confused-deputy tradeoff) vs accept two prompts. Confirm
  on web in the spike.

### Design details

Full architecture — flows, the reversal from the earlier auto-approve design, scope rationale,
Railway/secret specifics, verification matrix — is in **`docs/ARCHITECTURE.md`**. Summary:

- **Client hop:** claude.ai ↔ our FastMCP server over Streamable HTTP, OAuth 2.1 (PKCE-S256).
  `OAuthProxy` fronts Google Workspace OIDC; only an `@aretea-group.com` identity completes the
  flow. Our server issues its own bearer token bound to that user; **no Drive scopes** ever
  requested of the user.
- **Drive hop:** service-account credentials, all queries pinned to `driveId=<AI-Visible drive>`
  (`corpora=drive`, `includeItemsFromAllDrives`, `supportsAllDrives`), with a content-time
  `driveId` equality assertion before returning any file.
- **Extensibility (NFR6):** tools live behind a `toolsets/` registry; a future connector is a new
  `register(app)` module behind the identical auth front.
- **Platform risk (current, not historical):** claude.ai *web* custom-connector OAuth has active
  breakages (metadata discovered but no `/token` POST; callback errors; instant Connect failure) —
  through-line "works in Claude Code/ChatGPT, fails on web." Hence the spike and smoke test run on
  **web**, and we budget for an Anthropic-side blocker (issue tracker + support path ready).

## Phasing

Gate-first — the OAuth handshake is the load-bearing step; prove it before building tools.

1. **Phase 0 — Google setup (manual, admin).** AI-Visible Shared Drive; service account added as
   viewer of that drive only; OIDC OAuth client + Workspace domain restriction.
   _Exit:_ SA reads the AI-Visible drive and **nothing else** (membership verified).
2. **Phase 1 — AS + spike (STOP GATE), on claude.ai web.** Stand up the `OAuthProxy`→OIDC AS only.
   _Exit (both required):_ **(a) per-user flow** — a second, non-admin user reaches our authorize
   endpoint with a **distinct** identity; **(b) negative gate** — a non-Aretea identity is
   **rejected, no data**. (Also observe whether claude.ai passes a free per-user id — §2.4.)
   **Do not build tools until (a)+(b) pass.**
3. **Phase 2 — Drive hop + read tools.** _Exit:_ FR3/FR4 pass against the corpus; FR5 negative test
   passes; only read tools in the schema.
4. **Phase 3 — Per-user audit + EU deploy.** _Exit:_ each tool call emits one per-user log line;
   deployed to Railway EU with secrets in the secrets manager.
5. **Phase 4 — Rollout.** One test user first, then Owner enables org-wide.
   _Exit:_ FR2′–FR5 verified for the test user; post-deploy web smoke test green.

## Success criteria / Metrics

- **Primary (adoption):** connector in **weekly active use within 4 weeks** of launch. Measured
  informally (Frederik asks the team); no in-code tracking in v1. _Timeframe assumed — confirm._
- **Guardrail:** **zero** reads outside the AI-Visible drive (Finance/HR never reachable) —
  verified before launch (FR5 negative test) and spot-checked after. Baseline: must be 0.
- **Design-acceptance (secondary, not a launch metric):** a second connector can be added as a
  toolset without re-solving auth or hosting.

## Observability

- Per-user structured-JSON audit line per tool call → Railway logs: `{ts, user, tool,
  args_summary, outcome, duration_ms}`. No file contents logged. Retention = Railway default
  unless configured (open question).
- Post-deploy smoke test (handshake + one read) on claude.ai web, to catch platform regressions.

## Acceptance criteria

- [ ] **AC1** — Given a Team Owner with the server URL, When they complete the OAuth handshake on
      claude.ai **web**, Then the connector shows as connected. _(test: e2e)_
- [ ] **AC2** — Given the connector is enabled org-wide, When a **second, non-admin** Aretea user
      enables it, Then they reach our authorize endpoint with a **distinct identity** our AS
      records. _(test: e2e)_ — *load-bearing; gates the whole attribution design.*
- [ ] **AC3** — Given a non-`aretea-group.com` identity, When it attempts the OAuth flow, Then the
      **Google Internal-app restriction** denies it an upstream auth code (**no token issued**), and
      the server-side email-domain check refuses any minted session (**no data reachable**).
      _(test: integration on Google config + unit on the domain check)_ — *see amendment A2.*
- [ ] **AC4** — Given a connected Aretea user, When their Google account grants are inspected, Then
      **no Drive scope** was granted to them (FR2′). _(test: integration)_
- [ ] **AC5** — Given the corpus, When Claude searches it, Then matching files from the AI-Visible
      drive are returned. _(test: integration)_
- [ ] **AC6** — Given a corpus Doc / Sheet / Slides / text file, When Claude reads it, Then it gets
      Doc text / Sheet cell values / per-slide text / file text at basic fidelity. _(test: integration)_
- [ ] **AC7** — Given a known Finance/HR file outside the AI-Visible drive, When a tool targets it,
      Then **no data** is returned. _(test: integration)_
- [ ] **AC8** — Given the served tool schema, When it is inspected, Then it contains **only** read
      tools (no create/update/delete/share/permission). _(test: unit)_
- [ ] **AC9** — Given the service-account credential is built, When constructed, Then it uses **no
      `subject=`/domain-wide delegation** and only the three read scopes. _(test: unit)_
- [ ] **AC10** — Given a file whose `driveId` ≠ the AI-Visible drive, When `read_file` runs, Then
      it refuses before returning content (defense-in-depth). _(test: unit)_
- [ ] **AC11** — Given a document exceeding the size cap, When read, Then output is truncated and
      the result **states the truncation explicitly** (never silent). _(test: unit)_
- [ ] **AC12** — Given any tool call, When it completes, Then exactly one per-user JSON audit line
      is emitted to logs. _(test: integration)_

## Open questions

- **FR2 amendment sign-off** (owner: Frederik) — surfaced in `docs/ARCHITECTURE.md` §0. Blocks
  treating FR2′ as the requirement of record.
- **Per-user client-hop flow** — does claude.ai run per-user OAuth exposing a distinct identity to
  the AS? Resolved by the Phase-1 spike (`ARCHITECTURE.md` §2.2). Determines whether attribution
  is achievable at all.
- **Free per-user identifier** — does claude.ai already pass a verifiable per-user id (which would
  avoid the identity sign-in and leave FR2 unamended)? Checked in the spike (`§2.4`).
- **Audit log retention** on Railway (owner: Frederik).
- **Weekly-active timeframe** for the adoption metric (owner: Frederik; needed pre-launch).
- **`require_authorization_consent` on web** (A4) — does FastMCP double-prompt on claude.ai? Decide
  the value in the Phase-1 spike; it touches the FR2′ "one prompt" argument.
- **Fixed storage encryption key** (A1) — provision a Fernet key secret so volume-persisted tokens
  survive restarts; confirm rotation policy (owner: Frederik).

## References

- Root `prd-1` — initial draft this PRD consolidates and amends.
- `docs/ARCHITECTURE.md` — concrete technical design (the *how*), incl. the verification matrix,
  the FR2 amendment (§0), and the spike objectives (§8.1).
