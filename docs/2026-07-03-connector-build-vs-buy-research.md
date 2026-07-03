<!-- Decision note supporting prd_03. Produced 2026-07-03 by a multi-agent research workflow
     (6 research lanes + adversarial verification of 22 load-bearing claims; 19 confirmed, 3
     partly-true). This is the *evidence base*; the *decision* lives in prd_03. -->

# Build vs. Buy: Adding Governed Multi-Service Connectors to the Aretea LLM Connector

> **Citations & staleness.** Every load-bearing claim carries an inline source marker `[n]`; full URLs are in **Sources** at the end. All URLs accessed **2026-07-03**. Several claims are time-sensitive (vendor roadmaps, GA dates) — these are date-stamped and flagged **⚠ may be stale — re-verify at build**.

## Executive Recommendation

**A) Build the parts that are your moat and your residency risk; buy only commoditized, self-hostable plumbing — and keep the read-only tool schema _structural_, not configuration-enforced.** No single platform survives your two gating filters (EU self-host + dual auth) while covering all three named services — so this is *not* a monolithic buy. Concretely:

- **BUILD L1 (the per-user OAuth token vault)** on the FastMCP primitives you already run (`FileTreeStore` + `FernetEncryptionWrapper` + `authlib`).
- **BUILD L2 (the tool surface) as thin read-only tools over each vendor's REST API** — HubSpot CRM via a shared private-app token (the Drive-SA shape) [1][2], Slack via user tokens over the Web API, Granola via its REST API [3]. **This is the default for every connector** because it keeps read-only-by-construction (AC8) *structural*: no write tool ever enters the schema. Where you would rather not re-implement an API, self-host an **OSS MCP server whose tool schema you pin/hash and allow-list to reads at load** (Klavis / IBM ContextForge) [8][9]. **Proxying a vendor's official remote MCP** (`mcp.slack.com`, `mcp.hubspot.com`, `mcp.granola.ai`) behind your gate is an **explicitly-gated fallback only** — see the AC8 posture rule below.
- **BUILD L3 (governance) in-house** because it is your stated differentiator and it sits on the data path where a US SaaS is disqualified.

**The AC8 posture rule (deciding governance criterion, not a footnote).** Proxying *any* official vendor MCP imports that vendor's full tool schema into your surface, which **includes write tools**: Slack's official MCP ships send-message, react, and canvas create/manage tools [4][5]; HubSpot's went GA on **2026-04-13** with full CRM read **and** write [1][2]. Proxying therefore **degrades AC8 from by-construction to configuration-enforced** — you are then one allow-list mistake away from breaking the cross-connector-exfil containment this doc calls the single load-bearing control. So: **default to build-thin-read (or a pinned/allow-listed OSS MCP); treat vendor-MCP-proxy as an explicitly-gated exception, permitted only where no self-host/REST path exists and only behind a mandatory, tested read-only allow-list.** This is exactly the reasoning that already routes HubSpot via REST to dodge its MCP's write tools — applied uniformly, including to Slack (where allow-listing writes *out* is **mandatory, not optional**).

**B) Effort is moderate and front-loaded, not greenfield.** Auth + hosting are already solved, so a *shared-token* connector (HubSpot CRM) is a few days. The genuinely new work is one OAuth "third hop" vault (~1 month to production-grade). The **first** per-user connector on top of the vault realistically runs **1–2 weeks** (not days) once provider-specific refresh-token rotation, scope negotiation, and pagination/rate-limit handling are dealt with; **subsequent same-shape connectors converge to a few days.** **Do not buy Composio/Arcade/Pipedream/WorkOS** (US cloud token stores; enterprise-gated self-host) [10][11][12][13] and **do not buy Merge Agent Handler** (it *is* the L3 control plane you intend to own). The one defensible buy-to-save-code option is an OSS self-hostable MCP gateway (**IBM ContextForge**, Apache-2.0) [9] to federate upstreams — evaluate it as an accelerator, but it does not replace the vault.

---

## The three-layer thesis

| Layer | What it is | Verdict | Why |
|---|---|---|---|
| **L1 — Auth / token plumbing** | Per-user OAuth vault, refresh, scoping, connection mgmt | **BUILD** (buy = Nango self-host, optional) | Stores third-party OAuth tokens → must be EU/self-hosted (gate #1). FastMCP already ships the storage + encryption primitives you'd reuse. |
| **L2 — Tool / API surface** | The actual read tools per service | **BUILD thin read tools over vendor REST (default)** — or self-host a **pinned/allow-listed OSS MCP**; vendor official-MCP-proxy is a **gated exception only** | Building read-only tools keeps AC8 *structural*. Slack/HubSpot/Granola official MCPs all ship **write** tools [1][4], so proxying them makes AC8 config-enforced — avoid unless no REST/self-host path exists, and then allow-list reads with a tested filter. |
| **L3 — Governance control plane** | Identity, per-user authz, audit, allow-listing, DLP, rate-limit, egress | **BUILD** | This is your differentiator, it lives on the data path (US SaaS fails gate #1), and you already have the spine (`AuditMiddleware`). |

The load-bearing insight: your existing **hop-1 identity is reusable as the vault key**, and **hop-2 becomes per-connector** — shared service credential for some (Drive-SA, HubSpot private-app token), per-user OAuth for others (Slack DMs, Granola personal notes). That is the whole architecture.

---

## Gating-filter pass — what was eliminated before scoring

**Filter #1 (EU self-host / data residency) and #2 (dual auth in one platform) applied first.** Each residency/self-host status is sourced below.

| Eliminated | Reason (sourced) |
|---|---|
| **Composio** | Self-serve plans are **managed-only**: credentials stored on Composio's cloud; self-host is **Enterprise-sales VPC/on-prem only**, no self-serve EU region [10]. The MIT repo is client SDKs. (Verdict: *confirmed, as of 2026-07-03*.) |
| **Arcade.dev** | Execution Engine (token vault + executor) is a **closed-source binary** (Docker); self-host that controls data residency is **Enterprise-only**, default routes through Arcade Cloud [11]. Duplicates the L3 you're building. |
| **Pipedream Connect** | Runs **fully managed on AWS `us-east-1`**, **no self-hosting option**; OAuth grants encrypted at rest but the token store + proxied data stay in US [12]. (Confirmed.) *(An unverified rumor of a Workday acquisition circa Jan 2026 is **not load-bearing** — elimination stands on residency regardless; dropped from the reasoning.)* |
| **WorkOS (Pipes/Vault)** | A real per-user token vault, launched **Dec 2025**, but **US-hosted with no EU region GA today** [13]. Regional hosting is *reported on the roadmap* and a **BYOK Vault** (customer-held keys, AWS/Azure/GCP KMS) already exists [13a] — so soften, don't overstate. **Elimination stands on data-at-rest-in-US today (gate #1)**; flip to "contender" if EU ships. **⚠ may be stale — re-verify EU hosting at build.** |
| **OpenInt** | Product pivot/abandonment; product domain returned HTTP 402; self-host + EU unverifiable (re-verify). |
| **Supaglue** | Repo **archived read-only (reported 2024-03-10)**; team went to Stripe [14]. Unmaintained token store = disqualifying. *(Archive date not independently re-confirmed here — re-verify.)* |
| **Aptible** | Wrong category (hosting/compliance PaaS); does not store/refresh third-party OAuth tokens. |
| **Merge Unified API** | Survives gates (EU region) but **wrong shape**: Common-Model normalization strips the raw provider fields/scopes a governance/allow-list layer must operate on; no Slack, no Granola. |

**Survivors** (compared below): a pure **BUILD** on FastMCP; **Nango** (self-host) [6][7]; **Klavis** (OSS Docker MCP servers) [8]; **IBM ContextForge** (OSS gateway) [9]; **MintMCP** (EU-region SaaS gateway); **Paragon** (EU cloud / enterprise self-host); **Merge Agent Handler** (EU/enterprise — a strategic-overlap warning); and the three **official first-party MCP servers** as *gated-fallback* L2 endpoints only.

---

## Decision matrix (survivors)

Hosting region pinned per row (gate #1). "Vendor-hosted (US)" = tool-call content transits the vendor's US MCP cloud.

| Option | Layers | Self-host / EU region | Per-user + shared auth | MCP | Slack / HubSpot / Granola | Governance | Pricing | Integ. effort | Lock-in |
|---|---|---|---|---|---|---|---|---|---|
| **BUILD on FastMCP** (recommended L1+L2+L3) | L1+L2+L3 | ✅ self-host, **EU** (your Railway `europe-west4`) | ✅ both (vault + keep Drive-SA) | native | build thin read tools via vendor REST | **you own it; AC8 stays structural** | $0 (your infra) | ~1 mo first vault; 1–2 wk first per-user connector | **lowest** |
| **Nango** (self-host) | L1 (+L2 proxy) | ✅ free docker-compose, **EU**, `NANGO_ENCRYPTION_KEY` you hold [6][7] | ✅ per-user connId + fixed connId | via proxy | Slack ✅ / HubSpot ✅ / **Granola** (community provider) | audit, rate-limit | **$0** self-host free tier (auth + credentials) [7] | medium (REST proxy; **Node + Python SDKs exist** [6a]) | low |
| **IBM ContextForge** (gateway) | L1-fwd+L2+L3-lite | ✅ **Apache-2.0**, `pip`/Docker, **EU** [9] | ✅ upstream OAuth (`X-Upstream-Authorization`) + shared | federates any MCP | ✅/✅/✅ (by **proxying** their official MCPs — inherits write tools; allow-list at the virtual server) | allow-list (virtual servers), authz, audit, rate-limit | **$0** | low | low |
| **Klavis** (OSS servers) | L1+L2 | ✅ Docker, **EU**, token from env (`SLACK_BOT_TOKEN`, HubSpot `AUTH_DATA`) [8] | ✅ env-injected shared + optional cloud OAuth | both | ✅/✅/**✗** | thin (bring your own) | $0 self-host | low | low |
| **MintMCP** (SaaS gateway) | L1+L2+L3 | ⚠️ **EU-region SaaS**; self-host on request (enterprise) | ✅ | proxies MCPs | ✅/✅/✅ | allow-list, authz, audit, rate-limit | undisclosed enterprise | medium | medium |
| **Paragon (ActionKit)** | L1+L2+L3-partial | ⚠️ **EU cloud**; full self-host **Enterprise-only** (K8s/Helm) | ✅ | both | ✅/✅/**✗** | authz, allow-list, logs | sales-gated | medium | high |
| **Merge Agent Handler** | L1+L2+L3 | ⚠️ **EU region**; on-prem enterprise (unverified) | ✅ | both | ✅/✅/**✗** | **allow-list, DLP, audit** | Free/$1,000-mo/$10-user | medium | **high — competes with your L3** |
| **Official Slack / HubSpot / Granola remote MCP** | L2 (upstream) | ❌ **vendor-hosted, US** (`mcp.slack.com` [4], `mcp.hubspot.com` US [2], `mcp.granola.ai` on US AWS [3]) — **gated fallback only** | per-user OAuth 2.1 (HubSpot also shared via REST) | endpoints | first-party (**ship write tools** — must allow-list reads) [1][4] | per-user perms; **AC8 becomes config-enforced** | free w/ plan | low | low |

**Klavis license note:** the repo's LICENSE file indicates **MIT** while some third-party writeups say Apache-2.0 [8] — **⚠ verify license at build.** ContextForge is Apache-2.0 (confirmed) [9].

**L2 residency framing.** Default to **EU-resident execution**: self-host an OSS MCP (Klavis/ContextForge) or build thin read tools in your own EU Railway infra, so only the *unavoidable* raw vendor API call leaves the region. **Vendor-remote-MCP-proxy is the fallback** where no self-host path exists — it additionally routes tool-call *content* through the vendor's US MCP cloud. For first-party services the incremental residency delta is small (you hit Slack/HubSpot/Granola infra the moment you use them at all), so the *governance* argument (AC8 structural vs. config-enforced), not residency, is what makes build-thin-read the default.

---

## The per-user data-hop design, mapped onto your codebase

Today you have **two hops that never mix**: hop-1 (`auth/provider.py` `GoogleProvider`/`OAuthProxy`, identity only) and hop-2 (`gdrive/credentials.py`, one fixed read-only SA). Adding per-user services introduces a **genuinely new third hop** — the server acting as an *outbound* OAuth 2.1 **client** to each third party, per user. This is additive; shared-credential connectors keep hop-2 unchanged.

**Vault key = hop-1 identity, but keyed on `sub`, not email.** Your `audit.py` correctly gates on the `email` claim (`_gate_email` never falls back to `sub`). The vault must key on the **stable `sub`** — the MCP authorization spec (2025-06-18) prohibits token passthrough ("MCP servers MUST NOT accept tokens not issued for them, and MUST NOT pass through the client's token downstream") [15], so you mint/hold a *separate* per-connector token per `(sub, connector)`. Email is reassignable and must not key long-lived tokens.

**Where it drops in — the `register(app, **deps)` seam.** `toolsets/base.py` already defines `register(app, **deps)`; `server.py:build_app` already threads a scoped client into `drive.register(app, client=client, ...)`. The per-user pattern is identical, with a token accessor as the injected dep:

```python
# server.py (sketch) — additive; the auth front and gate are untouched
vault = TokenVault(store=make_store(settings))          # reuse auth/store.py primitives
slack.register(app, get_token=vault.accessor("slack"))  # per-user OAuth connector, read-only tools only
hubspot.register(app, client=HubSpotClient(settings.hubspot_private_app_token))  # shared SA-style, REST
```

- **Shared-credential connectors** (HubSpot CRM): `per_user_required=false` — HubSpot's REST CRM API accepts a **single non-expiring private-app Bearer token** scoped read-only (`crm.objects.contacts.read`, …), account-scoped [1]. This *is* the Drive-SA shape; no vault, no new auth. Note: the *official* `mcp.hubspot.com` is OAuth-2.1-only and ships **read AND write** tools [1][2], so use REST for the shared path; if you ever proxy the MCP you **must** allow-list read tools. **⚠ verify at build:** confirm the REST read scopes cover every object type you need — the official MCP path notably **does not support custom objects**, and your REST scope set must be checked against the same object coverage.
- **Per-user connectors** (Slack DMs, Granola personal notes): the connector's tool calls `get_token(sub)`, which runs/reuses an auth-code+PKCE flow, stores encrypted tokens keyed by `sub`, and refreshes near expiry.

**Storage: you already have it.** `auth/store.py` builds `FileTreeStore` + `FernetEncryptionWrapper` on the Railway volume with a fixed `STORAGE_ENCRYPTION_KEY` (amendment A1). The vault reuses this exact `AsyncKeyValue` store — tokens stay in EU on your volume. Single Railway instance ⇒ an in-process `anyio` per-key refresh lock suffices today; `RedisStore` + distributed lock is deferred until you scale horizontally.

**Governance stays where it is.** `AuditMiddleware.on_call_tool` already fires per tool call regardless of connector. Extend its one JSON line (`{ts,user,tool,args_summary,outcome,duration_ms}`) with `connector_id` + downstream `connection/subject` id (never the token). The org-domain gate keeps running unchanged in front of every new tool.

**Hard rule: never let Claude.ai web connect to a vendor MCP directly.** If you register `mcp.slack.com` as its own Claude.ai connector, your `AuditMiddleware` gate and audit line **never run** — *and* you inherit its write tools ungoverned. Every upstream must be **built as thin read tools** or (fallback) **proxied behind your FastMCP front** (directly, or via an OSS gateway like ContextForge) with a tested read-only allow-list, so the gate + audit still fire.

---

## Governance control-plane: the multi-connector security surface

Aggregating N services behind one agent changes the threat model. The live risks (not theoretical):

- **Prompt injection (live, high).** Every connector returns attacker-influenceable *content* (a Drive doc, an inbound Slack DM, a HubSpot note, a Granola transcript) the model may read as instruction. Containment = keep everything read-only so an injected instruction has no action to hijack.
- **Cross-connector exfil (the marquee multi-connector risk).** Injected text in connector A steers the agent to read connector B and route it out. Today it's blunted **only** because every tool is read-only — this goes live the instant any mutating/egress tool (a Slack "post", a URL-fetch) is added. **Read-only-by-construction (AC8) is the single load-bearing control** — which is *precisely why* L2 defaults to build-thin-read (schema has no write tool) rather than proxying a vendor MCP (schema inherits write tools; AC8 downgraded to an allow-list you must never misconfigure).
- **Confused deputy (worse with each per-user connector).** Each per-user OAuth connector makes you a deputy. The MCP spec mandate [15]: per-client consent stored server-side and checked *before* forwarding, exact `redirect_uri` matching, single-use `state` set only after consent, RFC 8707 audience validation, and never pass hop-1 downstream. Verify whether FastMCP 3.4.2's `OAuthProxy` already implements per-client consent (`⚠ verify at build`, per your convention).
- **Token theft (concentration risk).** Moving from one SA to N×M refresh tokens makes the vault a high-value target. Mitigate with the existing Fernet-at-rest, fixed key in secret store, short-lived access tokens, never-log-tokens, revoke+purge on offboarding.
- **Refresh races** (the #1 hand-rolled-vault bug): single-use rotating refresh tokens can lock a user out under concurrency. **Do not assume rotation is always on** — **Slack refresh-token rotation is opt-in per app configuration** [4]; enable it deliberately and handle rotation, and note Google needs `access_type=offline&prompt=consent`. Mitigate with a per-key lock + refresh-ahead margin regardless.
- **SSRF / egress** and **session hijacking**: egress proxy (Smokescreen) + block link-local/metadata ranges; CSPRNG session IDs bound to `sub`.
- **Tool poisoning / rug-pull: LOW today** (your connectors are first-party via `register`). Becomes live only if you federate third-party MCP servers — which the gateway/proxy fallback path does, so pin/hash/scan upstream tool schemas (and re-check them on every upstream update) if you go that way.

**Governance capabilities to build (all in-house, all cheap for one org):** per-user/per-connector authz; audit extended with connector id + subject; tool allow-listing + read-only enforcement in the `register` seam; DLP/redaction on **Microsoft Presidio** (OSS, self-hostable — a US DLP SaaS on the data path fails gate #1); per-user/per-connector rate limiting; egress control. The only legitimate **buy** here is **KMS/secret management for the Fernet key** — it guards a key without moving user *data* offshore.

---

## Granola verdict — conditional / blocked on residency, not on API

**Granola has a real public API and an official MCP — the integration is technically possible** (confirmed *high, as of 2026-07-03*): a read-only REST API (`public-api.granola.ai/v1`, `Authorization: Bearer grn_…`, Business+ plans) **and** an official remote MCP (`mcp.granola.ai/mcp`, browser OAuth 2.0 + Dynamic Client Registration, **per-user only** — "no API key or service account access method for MCP") [3][3a]. Granola is the clearest proof your **dual-auth requirement is mandatory**: unlike Drive/HubSpot, its MCP cannot be a shared connector.

**Correction on the REST key — it is NOT a shared/service token.** The `grn_` **Personal API key is per-user**: each Business+ workspace member mints their **own** key from Settings → API, scoped to that user's own (My Notes) + shared notes [3][3a]. So the REST path does **not** avoid per-user token management — it still requires the vault. The **only** team/admin-shared Granola credential is the separate **Enterprise API** (Enterprise plan, admin-gated scopes). Net: **Granola has no cheap shared-token path below Enterprise** — it is *not* a HubSpot-shaped shared-token connector, and adopting it (via REST or MCP) means per-user vault work.

**And it trips gate #1.** Granola is **US-only** — all data stored on AWS servers in the United States; no EU/UK regional data residency offered; GDPR handled via DPA/SCCs; no self-host of the official API/MCP [3]. (Granola's **2026-03-25** $125M raise / enterprise pivot [16] does not change residency — **⚠ re-verify residency at build**, as the enterprise tier may add regions.)

**Recommendation: WAIT / conditional.** Treat Granola as a governance-decision connector, not an engineering one. The data already lives in Granola's US cloud regardless of how you read it, so reading it does not *worsen* residency — but adopting it commits the org to US processing under DPA/SCCs, which contradicts the deliberate EU posture. Do **not** build it in Phase 1. Revisit only after an explicit, documented residency sign-off. **If approved, integrate via the REST API's per-user `grn_` key stored in the vault** (headless-friendly, but per-user — budget vault work, not a cheap shared token) rather than the interactive per-user MCP, and build thin read tools behind your gate. Only if the org lands on the **Enterprise plan** does a single admin-shared credential (the Enterprise API) become available. No aggregator shortcuts Granola (absent from Composio/Klavis/Merge/Paragon catalogs; Nango has only a community provider).

---

## Section B — Effort, complexity, and the phased roadmap

Connector #2 is **marginal, not greenfield**: auth + hosting are solved once (your PRD's whole premise). Effort splits by *auth shape*, not by service.

### Phased roadmap

| Phase | Scope | Effort | Notes |
|---|---|---|---|
| **0 — Governance extension** | Extend `AuditMiddleware` audit line with `connector_id` + downstream subject; codify read-only allow-listing in the `register` seam; scope inventory | **~2–3 days** | Pure in-house; no new auth. Do this first so every later connector inherits it. |
| **1 — HubSpot (shared, MARGINAL)** | New `toolsets/hubspot.py` on the REST CRM API with a read-only **private-app token** (Drive-SA shape, `per_user_required=false`); tools + tests | **~3–5 days** | No vault, no OAuth. Thin read tools = AC8 stays structural. Proves multi-connector governance end-to-end. |
| **2 — Build the per-user OAuth vault (the new hop)** | Per-connector OAuth client config, auth-init + callback route, encrypted store keyed on `sub` (reuse `auth/store.py`), lifecycle/refresh manager, per-key lock, connection-management tool, consent-before-forward | **~1 month** to production-grade | The genuinely new work. Uses `authlib` + `httpx` + existing Fernet store — all already in-stack. |
| **3 — Slack (first per-user connector)** | `toolsets/slack.py` over the vault; **build thin read tools** via user token over the Slack Web API (default). Proxying `mcp.slack.com` is a **gated fallback only** — it ships write tools [4], so it requires a tested read-only allow-list | **~1–2 weeks** on top of Phase 2 | First per-user connector carries the provider-specific tail: Slack **refresh-token rotation is opt-in** [4], scope negotiation, pagination/rate-limits. Slack DMs *force* per-user OAuth (shared bot token can't read private DMs unless invited; org-wide Discovery API is Enterprise-Grid/compliance-only). |
| **4 — Hardening** | Revocation/offboarding purge + provider revoke, refresh-race grace window, DLP (Presidio) on responses, egress proxy, rate limits | **~1–2 weeks** | Defense-in-depth; largely reusable across connectors. |
| **5 — Granola** | *Conditional on residency sign-off only.* If approved, per-user `grn_` REST key in the vault (per-user, not shared) — see verdict | **~3–5 days** (if approved, on top of the vault) | Not a cheap shared-token connector; needs the vault. |

**Total to a production dual-auth vault + governance wrap: ~1 month of focused engineering, plus ~1–2 weeks for the first per-user connector and a few days for each subsequent same-shape one.** Multi-instance (RedisStore + distributed lock) is **deferrable** — a single Railway volume + `FileTreeStore` is fine today.

### Complexity / risk ledger

| Dimension | Risk | Mitigation |
|---|---|---|
| **Operational** | Vault is stateful; refresh correctness; Fernet key must stay fixed (A1) — losing it bricks all connections, leaking it exposes all users | Reuse existing store; key in Railway secret/KMS; per-key refresh lock + refresh-ahead margin; never rotate key without re-encrypt |
| **Security** | Concentrated token store; confused-deputy per connector; cross-connector exfil if read-only ever breaks | **Read-only-by-construction (build thin read tools) as the primary control**; per-client consent; per-user authz caps blast radius to the caller's own access; extend audit |
| **Governance posture** | Proxying a vendor MCP downgrades AC8 from structural to allow-list-enforced | Default to build-thin-read/REST or pinned OSS MCP; vendor-MCP-proxy only as a gated exception with a mandatory, tested read-only allow-list |
| **Lock-in** | Buying a US SaaS vault (Composio/Arcade/Pipedream/WorkOS) or Merge Agent Handler locks in your differentiator on foreign infra | Build L1+L3; if you buy L2, prefer **OSS** (Klavis/ContextForge) over a proprietary gateway |
| **Buy-side ops** | Nango self-host adds Postgres+Redis+Node alongside FastMCP; free tier is auth+credentials only (syncs/webhooks/MCP are Enterprise — **⚠ re-verify free-tier scope at build**) | Only adopt if connector count explodes; integrate via REST proxy + `get-connection-credentials` (Node **and** Python SDKs exist) [6a] |

### The concrete buy/build split

- **BUILD (L2, default):** thin read-only tools over each vendor's REST API (Slack Web API, HubSpot CRM, Granola REST) — you keep AC8 *structural*. Where you'd rather not re-implement an API, self-host an **OSS MCP** (Klavis / IBM ContextForge, Apache-2.0, EU) and **pin + read-only-allow-list its tool schema at load**. **Vendor official-MCP-proxy is a gated exception**, permitted only where no REST/self-host path exists and only with a mandatory, tested read-only allow-list — because Slack/HubSpot/Granola MCPs ship write tools [1][4] and proxying downgrades AC8. (ContextForge caveat: young, adds Postgres/Redis, partially overlaps your in-house L3 — **⚠ re-verify maturity at build**.)
- **BUILD (L1):** the per-user OAuth vault, on FastMCP primitives, in EU on your Railway volume. (Nango self-hosted is the credible *fallback* buy — free, EU, key-you-hold [6][7] — if you'd rather not own OAuth refresh mechanics.)
- **BUILD (L3):** everything governance. Explicitly **decline Merge Agent Handler / Composio / Arcade** — adopting them means buying and locking into the exact control plane you set out to own.

---

## Decision + immediate next steps

**Decision:** *Build the tool surface as thin read-only tools over vendor REST (or a self-hosted, pinned/allow-listed OSS MCP), keeping AC8 structural; build the token vault and the governance control plane in-house; keep every upstream behind your FastMCP gate; treat vendor official-MCP-proxy as a gated exception only.* Ship a **shared-token connector first (HubSpot CRM)** to prove the marginal-cost thesis, then invest the one real month in the per-user OAuth vault (Slack, ~1–2 weeks on top). Hold Granola pending a residency decision.

**Spike list (each is `⚠ verify-at-build`, per your convention):**
1. **FastMCP `OAuthProxy` per-client consent** — does 3.4.2 already implement consent-before-forwarding + exact `redirect_uri` + single-use state? Determines how much confused-deputy defense you write vs. inherit.
2. **HubSpot private-app read-only token** — spike `toolsets/hubspot.py` against the REST CRM API end-to-end through the existing gate + audit; confirm `per_user_required=false` holds and that read scopes cover every object type (custom objects included, which the official MCP omits) [1][2].
3. **Vault refresh race** — prototype the `(sub, connector)` store on `FileTreeStore`/Fernet with an `anyio` per-key lock; **enable Slack refresh-token rotation** [4] and force two concurrent refreshes; confirm no lockout.
4. **Build-thin-read vs. gated-proxy for Slack** — default: spike a direct read-only Slack Web-API build over the vault (AC8 structural). Only if that proves disproportionate, evaluate proxying `mcp.slack.com` behind FastMCP **with a tested read-only allow-list** that filters out send/react/canvas write tools [4][5]; the deciding criterion is **AC8 posture (structural vs. config-enforced)**, not effort parity.
5. **ContextForge accelerator eval** — stand up IBM ContextForge on a Railway EU service, register your Drive FastMCP + one upstream, and test a read-only "virtual server" allow-list [9]. Decide gateway-vs-direct-build before Phase 3. **⚠ re-verify project maturity.**
6. **Granola residency memo** — one-page US-processing/DPA-SCC decision for the founder; note the `grn_` key is per-user (vault work) and only Enterprise API is shared [3]. No code until signed.

---

## Sources

*All URLs accessed 2026-07-03. Time-sensitive items date-stamped; roadmap items flagged **⚠ may be stale — re-verify at build**.*

1. HubSpot — "Remote HubSpot MCP server is now generally available" (GA **2026-04-13**; adds read **and** write across contacts/companies/deals/tickets/line-items/products + activities): https://developers.hubspot.com/changelog/remote-hubspot-mcp-server-is-now-generally-available
2. HubSpot — "Integrate AI tools with the remote HubSpot MCP server" (`https://mcp.hubspot.com`, OAuth 2.1 + PKCE, HubSpot-hosted): https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-the-remote-hubspot-mcp-server ; product page: https://developers.hubspot.com/mcp
3. Granola — API & residency docs (`public-api.granola.ai/v1`; `grn_` **Personal key is per-user**, generated per Business+ member; Enterprise API is the admin/team credential; MCP is per-user OAuth only; US-only data residency): https://docs.granola.ai/introduction
3a. Scalekit — "Granola MCP vs Granola API for AI Agents (2026)" (per-user Personal key vs. Enterprise API distinction; MCP has no service-account path): https://www.scalekit.com/blog/granola-mcp-vs-api
4. Slack — "Slack MCP server: Overview" (ships **send message, canvas create/manage, react** and other **write** tools; refresh-token rotation is opt-in per app): https://docs.slack.dev/ai/slack-mcp-server/
5. Slack — "New Slack MCP Server tools released" (**2026-05-13**): https://docs.slack.dev/changelog/2026/05/13/new-mcp-tools/
6. Nango — GitHub (open-source integration platform; `NANGO_ENCRYPTION_KEY` self-held; self-host guide): https://github.com/NangoHQ/nango ; self-hosting: https://nango.dev/docs/guides/platform/self-hosting
6a. Nango — Python integration/SDK reference (contradicts any "no Python SDK" claim): https://dlthub.com/context/source/nango
7. Nango — "Free self-hosting configuration" (free edition keeps auth + credentials on your infra; Enterprise self-host runs full platform): https://docs.nango.dev/guides/self-hosting/free-self-hosting/configuration
8. Klavis — GitHub (OSS Docker MCP servers; env-injected tokens; **LICENSE indicates MIT — ⚠ verify**): https://github.com/Klavis-AI/klavis
9. IBM ContextForge — GitHub (AI gateway/registry/proxy; **Apache-2.0**; federate/virtualize/allow-list MCPs): https://github.com/IBM/mcp-context-forge ; docs: https://ibm.github.io/mcp-context-forge/
10. Composio — Enterprise page (self-host is Enterprise VPC/on-prem only; self-serve plans store credentials on Composio cloud): https://composio.dev/enterprise ; on-prem/self-host discussion: https://github.com/ComposioHQ/composio/issues/291
11. Arcade — Hosting/deployment docs (**closed-source engine binary**; self-host controlling residency is Enterprise-only; default routes via Arcade Cloud): https://docs.arcade.dev/home/hosting-overview ; https://docs.arcade.dev/en/guides/deployment-hosting/arcade-cloud
12. Pipedream — "Privacy and Security" (**fully managed on AWS `us-east-1`, no self-hosting**): https://pipedream.com/docs/privacy-and-security ; region confirmation: https://pipedream.com/community/t/in-what-aws-region-do-pipedream-wofkflows-run/1019
13. WorkOS — "Data residency for enterprise SaaS" (Vault/Pipes launched **Dec 2025**; US-hosted, no EU region GA today; regional hosting reported on roadmap — **⚠ may be stale**): https://workos.com/blog/data-residency-for-enterprise-saas
13a. WorkOS — "Bring Your Own Key (BYOK) — Vault" (customer-managed keys via AWS/Azure/GCP KMS): https://workos.com/docs/vault/byok
14. GitHub — repository-archiving reference (Supaglue repo reported archived read-only 2024-03-10; team went to Stripe — **archive date not independently re-confirmed here, re-verify**): https://docs.github.com/en/repositories/archiving-a-github-repository/archiving-repositories
15. MCP authorization specification, 2025-06-18 (token-passthrough prohibition; MCP server acts as OAuth client to upstreams; RFC 8707 audience validation; confused-deputy guidance): https://modelcontextprotocol.io/docs/tutorials/security/authorization ; explainer: https://auth0.com/blog/mcp-specs-update-all-about-auth/
16. TechCrunch — "Granola raises $125M... expands from meeting notetaker to enterprise AI app" (**2026-03-25**): https://techcrunch.com/2026/03/25/granola-raises-125m-hits-1-5b-valuation-as-it-expands-from-meeting-notetaker-to-enterprise-ai-app/
