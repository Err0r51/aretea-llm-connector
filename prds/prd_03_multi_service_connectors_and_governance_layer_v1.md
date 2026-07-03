# PRD 4: Multi-service connectors & governance layer v1

> **Status:** 🚧 Draft (WIP — NOT final, not approved) — Last refreshed: 2026-07-03
>
> ⚠ **Work in progress.** This is an unreviewed draft derived from the build-vs-buy study
> (`docs/2026-07-03-connector-build-vs-buy-research.md`). Scope, phasing, effort estimates, and the
> buy/build calls are **provisional and pending sign-off** — nothing in "Decisions" is locked until
> reviewed. Open blockers before this can move to `Active`: the Granola residency decision and the
> FastMCP `OAuthProxy` per-client-consent spike (see Open questions).

_Follows PRD 3 (`prd_02_…`, CI/CD). PRD 2 shipped the first connector (Drive, read-only) behind two
decoupled auth hops; PRD 3 shipped the pipeline that ships it. This PRD delivers **connector #2+**:
adding Slack / HubSpot / (later) Granola behind the **identical auth front**, plus the **per-user
data hop** and the **governance control plane** those services require. The decision here is grounded
in a sourced build-vs-buy study — `docs/2026-07-03-connector-build-vs-buy-research.md` — which this
PRD summarizes; read it for the evidence and citations. The *how* (the new hop, the vault module,
the register-seam wiring) will land in `docs/ARCHITECTURE.md` at implementation. Header is "PRD 4"
continuing the sequence (root `prd-1` draft = 1, `prd_01_…` = "PRD 2", `prd_02_…` = "PRD 3")._

## Problem

The connector reaches exactly **one** corpus — a single Google Shared Drive, read through **one
shared service account**. The org's other systems of record — **Slack**, **HubSpot**, meeting notes
(**Granola**) — are unreachable from Claude, so answering a cross-system question means leaving the
governed connector and using each vendor's own AI surface: **ungoverned, unaudited, no org-domain
gate, no read-only guarantee.**

The current two-hop design deliberately grants users **zero data scopes** and reads through one
shared credential — an accepted **all-or-nothing** data model (PRD 2, FR2′). It has **no way to
represent per-user access**. Some of the target services are meaningfully per-person: a user's own
Slack DMs / private channels, or their own meeting notes, **cannot** be a single shared credential —
Slack won't return private DMs to a shared bot token, and Granola's API key is minted **per user**.
There is today **no per-user token store, no outbound third-party OAuth client, and no per-user
authorization** — the whole per-user shape is missing.

Governance today is **thin and Drive-specific**: one org-domain gate + one audit line +
read-only-by-construction (PRD 2 AC8/AC12). There is **no control plane spanning multiple
connectors** — no connector-aware audit, no cross-connector tool allow-listing, no per-user /
per-connector authorization, no DLP or egress control. Aggregating N services behind **one** agent
endpoint materially changes the threat model — **cross-connector exfiltration**, **confused-deputy
per user**, **token concentration** — and none of that is addressed by the Drive-only design.

This is the **first of several connectors** (CLAUDE.md names Slack/HubSpot/Granola as next). The
pattern set here — per-user vault + governance wrap — is **reused per service**, so it must be
designed once and made marginal-cost, not bespoke.

## Goals

- **Query more org systems through the same governed front.** HubSpot first, then Slack, run behind
  the *same* org gate, the *same* audit, and the *same* read-only guarantee as Drive.
- **Support both auth shapes in one server:** a **shared/service credential** (Drive-SA, HubSpot
  private-app token) **and per-user OAuth** (Slack; later Granola), keyed on the caller's stable
  identity.
- **A governance control plane across every connector:** connector-aware audit, read-only
  enforcement + tool allow-listing in the `register` seam, per-user/per-connector authorization, and
  a path to DLP/egress control.
- **Data stays EU-resident / self-hosted.** All third-party OAuth tokens and proxied data remain on
  our infra (Railway `europe-west4`); **no US SaaS on the data path.**
- **Read-only stays *structural*, not configuration-enforced.** No write/mutation tool enters the
  schema for any connector — PRD 2's AC8 posture is preserved as the load-bearing safety control.
- **Marginal-cost connectors.** Auth + hosting are solved once; connector #3+ of an already-built
  auth shape is a few days, not a re-solve.

## Non-Goals

- **Buying a managed integration/auth platform for the data path** — **Composio, Arcade.dev,
  Pipedream Connect, WorkOS Vault, Merge Agent Handler.** Each either stores tokens/data on **US**
  infra (fails EU residency) or **duplicates the L3 governance layer we intend to own**. Eliminated
  in Design; revisit only if a credible EU self-host ships. Self-hostable OSS plumbing (Nango
  self-host, IBM ContextForge, Klavis) stays a *possible accelerator*, not a data-path dependency.
- **Unified-API normalization** (Merge Unified API): the Common-Model abstraction strips the raw
  provider fields/scopes a governance/allow-list layer must operate on. → not this PRD.
- **Any write/mutation tool** (post a Slack message, edit a HubSpot record). Read-only stays
  structural, exactly as PRD 2. → out of scope by construction.
- **Connecting a vendor's official remote MCP directly to Claude.ai** (`mcp.slack.com`,
  `mcp.hubspot.com`, `mcp.granola.ai`) as its own connector — that **bypasses our gate + audit** and
  imports the vendor's **write** tools. → forbidden; if an upstream MCP is used at all it is
  **proxied behind our FastMCP front with a read-only allow-list** (fallback path only, see Design).
- **Granola in v1.** Blocked on an EU-residency decision (Granola is **US-only**) and its API key is
  **per-user, not shared** (needs the vault). → Phase 5, conditional on a signed residency memo.
- **Horizontal scale / multi-instance token store** (Redis + distributed refresh lock). One Railway
  volume + `FileTreeStore` suffices today. → later "stateless / HA" PRD (inherited from PRD 3).
- **Full DLP/redaction + egress proxy as a v1 blocker.** Deferred to the hardening phase
  (Microsoft **Presidio**, OSS, self-hosted — a US DLP SaaS on the data path fails residency). →
  Phase 4.

## Design

### Decisions (locked) (NEEDS SIGN-OFF)

- **Three separable layers, not a monolithic buy.** Score every option by which layer(s) it covers:
  **L1** auth/token plumbing (per-user OAuth vault, refresh, scoping), **L2** the tool/API surface,
  **L3** the governance control plane. **No single platform survives both gating filters (EU
  self-host + dual per-user/shared auth) *and* covers all three named services**, so this is not a
  buy-one-thing decision — **build the layers that are the moat + the residency risk; buy only
  optional self-hostable OSS plumbing.**
- **Gating filters applied first — eliminations.** Ruled out on EU-residency / self-host or on
  competing-with-L3: **Composio** (self-serve managed-only; self-host is Enterprise VPC),
  **Arcade.dev** (closed-source engine, US cloud default), **Pipedream Connect** (managed AWS
  `us-east-1`, no self-host), **WorkOS Vault** (US-hosted, no EU GA today — BYOK exists; re-verify if
  EU ships), **Merge Agent Handler** (EU region but it *is* the L3 control plane we set out to own).
  Survivors: **build-on-FastMCP** (recommended), **Nango self-host** (optional L1 fallback), **IBM
  ContextForge / Klavis** (optional OSS L2), the **official vendor MCPs** (gated L2 fallback only).
- **L1 vault = BUILD on primitives we already run.** A per-user, per-connector OAuth token vault
  reusing `auth/store.py` (`FileTreeStore` + `FernetEncryptionWrapper` on the Railway volume, fixed
  `STORAGE_ENCRYPTION_KEY` / amendment A1) + `authlib` + `httpx`. **Nango self-hosted** (free, EU,
  key-you-hold) is the credible *fallback buy* if we'd rather not own refresh mechanics — but the
  default is build, because the store + encryption are already in-stack.
- **Vault key = the stable `sub` claim, never email.** `audit.py` correctly gates on `email`
  (`_gate_email` never falls back to `sub`); the **vault keys long-lived tokens on `sub`** (email is
  reassignable). Per the **MCP authorization spec (2025-06-18)** there is **no token passthrough** —
  the server acts as an *outbound OAuth client*, mints/holds a **separate token per `(sub,
  connector)`**, and **never forwards the hop-1 bearer token downstream**.
- **L2 default = build thin read-only tools over each vendor's REST API.** HubSpot CRM via a shared
  read-only **private-app token** (the Drive-SA shape); Slack via **per-user user tokens** over the
  Web API; Granola (if approved) via the **per-user `grn_` REST key**. Building read tools keeps
  read-only **structural** — no write tool ever enters the schema. Where re-implementing an API is
  undesirable, self-host an **OSS MCP** (Klavis / IBM ContextForge, Apache-2.0, EU) and **pin/hash +
  read-only-allow-list its tool schema at load**.
- **Vendor official-MCP-proxy = gated exception only (the AC8 posture rule).** Slack's official MCP
  ships send-message / react / canvas **write** tools; HubSpot's GA MCP is full CRM **read + write**;
  Granola's MCP is per-user OAuth only. **Proxying any of them imports write tools and downgrades AC8
  from by-construction to configuration-enforced** — one allow-list mistake from breaking
  cross-connector containment. Permitted **only** where no REST/self-host path exists, **only** behind
  a mandatory, tested read-only allow-list, and **always behind our FastMCP gate** (never wired
  directly to Claude.ai).
- **L3 governance = BUILD, extending the existing spine.** `AuditMiddleware.on_call_tool` already
  fires per tool call in front of *every* connector. Extend its one JSON line with `connector_id` +
  downstream subject/connection id (**never the token, never content**). Codify read-only enforcement
  + tool allow-listing in the `register` seam. **Per-user/per-connector authorization** caps blast
  radius to the caller's *own* downstream access. DLP (Presidio) + egress proxy land in hardening.
  The only legitimate **buy** here is **KMS/secret management for the Fernet key** — it guards a key
  without moving user *data* offshore.
- **Drops into `register(app, **deps)` additively.** Shared-credential connectors keep hop-2
  unchanged (inject a scoped client, as `drive.register(app, client=…)` does today). Per-user
  connectors inject a **token accessor** — `vault.accessor("slack")` — that runs/reuses an
  auth-code + PKCE flow, stores encrypted tokens keyed on `sub`, and refreshes near expiry. **The
  auth front and org gate are untouched.**
- **Storage & concurrency.** Reuse the existing `AsyncKeyValue` store. Single Railway instance ⇒ an
  in-process `anyio` **per-key refresh lock** + refresh-ahead margin is sufficient; `RedisStore` +
  distributed lock is deferred until horizontal scale.
- **Granola = WAIT, conditional on residency.** A real read-only REST API (`public-api.granola.ai`,
  per-user `grn_` key) and an official per-user MCP both exist, so integration is technically
  possible — but Granola is **US-only** (no EU/self-host) and its key is **per-user** (needs the
  vault; only the Enterprise API is admin-shared). Reading it does not *worsen* residency (the data
  already lives in Granola's US cloud) but **adopting it commits the org to US processing under
  DPA/SCCs**, contradicting the deliberate EU posture. **Not v1** — gated on a documented sign-off.

**(PENDING SPIKE) FastMCP `OAuthProxy` per-client consent.** Confirm on FastMCP 3.4.2 whether the
`OAuthProxy` already implements **consent-before-forwarding**, exact `redirect_uri` matching, and
single-use `state` (the confused-deputy defenses the MCP spec mandates for a server acting as an
OAuth client). What it already provides vs. what we must build directly sizes the Phase-2 vault work.

### Design details

The full mechanics — the outbound-OAuth **third hop**, the `TokenVault` module, the auth-init +
callback route, the `register`-seam wiring, and the extended audit line — will be added to
`docs/ARCHITECTURE.md` at implementation (it currently documents only the two-hop v1). Shape:

- **The new third hop.** Hops 1 (identity) and 2 (fixed Drive SA) are unchanged. Per-user services
  add a *new* hop: **the server as an outbound OAuth 2.1 client** to each third party, per user.
  Additive — shared-credential connectors never touch it.
- **`register`-seam sketch** (additive; auth front + gate untouched):

  ```python
  # server.py (sketch)
  vault = TokenVault(store=make_store(settings))            # reuse auth/store.py primitives
  slack.register(app, get_token=vault.accessor("slack"))    # per-user OAuth, read-only tools only
  hubspot.register(app, client=HubSpotClient(settings.hubspot_private_app_token))  # shared, REST
  ```

- **Audit extension.** `AuditMiddleware`'s single JSON line gains `connector_id` + downstream
  subject/connection id; token and content are never logged (unchanged from PRD 2).
- **Multi-connector threat model** (the reason L2 defaults to build-thin-read): **cross-connector
  exfil** is blunted *only* because everything is read-only — it goes live the instant any
  mutating/egress tool is added, which is exactly why proxying a write-tool-bearing vendor MCP is a
  gated exception. See the research note's "Governance control-plane" section for the full surface.

## Phasing

Marginal-first — prove the governance wrap and the shared-token shape before building the vault.

1. **Phase 0 — Governance extension (~2–3 days).** Extend the audit line with `connector_id` +
   downstream subject; codify read-only allow-listing + write-tool rejection in the `register` seam;
   inventory scopes. _Exit:_ a dummy connector's call emits the extended line, and an attempt to
   register a write tool is rejected.
2. **Phase 1 — HubSpot (shared, MARGINAL) (~3–5 days).** `toolsets/hubspot.py` over the REST CRM API
   with a read-only private-app token (Drive-SA shape; `per_user_required=false`) + tools + tests.
   _Exit:_ a governed HubSpot read works end-to-end through the gate + audit; **no vault**.
3. **Phase 2 — Per-user OAuth vault (~1 month to production-grade).** Per-connector OAuth client
   config, auth-init + callback route, encrypted store keyed on `sub`, refresh manager + per-key
   lock, a connection-management tool, consent-before-forward. _Exit:_ a user can connect a per-user
   provider; tokens persist encrypted and refresh without lockout.
4. **Phase 3 — Slack (first per-user connector) (~1–2 weeks on the vault).** `toolsets/slack.py` thin
   read tools over the Slack Web API via the vault; enable Slack refresh-token **rotation** (opt-in).
   _Exit:_ a user reads **their own** Slack; another user cannot see it.
5. **Phase 4 — Hardening (~1–2 weeks).** Offboarding purge + provider revoke, refresh-race grace
   window, DLP (Presidio) on responses, egress proxy, per-user/connector rate limits. _Exit:_
   offboarding purges + revokes a user's tokens; DLP/egress controls are live.
6. **Phase 5 — Granola (conditional, ~3–5 days).** *Only after a signed residency memo.* Per-user
   `grn_` REST key in the vault + thin read tools. _Exit:_ approved, connected, governed read works.

## Acceptance criteria

- [ ] **AC1** — Given the assembled app with every registered connector, When the exposed tool schema
      is inspected, Then no create/update/delete/post/write tool is present (extends PRD 3 AC8 across
      all connectors). _(test: unit)_
- [ ] **AC2** — Given an authenticated caller, When a per-user token is stored or looked up, Then the
      vault key derives from the stable `sub` claim and never from `email`. _(test: unit)_
- [ ] **AC3** — Given a tool calling a downstream third-party API, When it authenticates, Then it uses
      the vault-held per-`(sub, connector)` token and the hop-1 bearer token is never forwarded
      downstream (no token passthrough). _(test: unit)_
- [ ] **AC4** — Given the org-domain gate and a caller outside the allowed domain, When *any*
      connector's tool is invoked, Then `AuditMiddleware` refuses before the tool runs (`denied` /
      `denied_no_email`) — for every connector, not only Drive. _(test: unit)_
- [ ] **AC5** — Given any connector's tool call, When it completes, Then exactly one JSON audit line
      is emitted carrying `connector_id` + downstream subject/connection id, and never the token or
      file contents. _(test: unit)_
- [ ] **AC6** — Given a vendor MCP proxied behind our FastMCP front (fallback path), When its tool
      schema is loaded, Then only read tools pass the allow-list and every write tool is filtered out.
      _(test: unit)_
- [ ] **AC7** — Given no signed Granola residency memo, When the app is assembled, Then no Granola
      tool is registered. _(test: unit)_
- [ ] **AC8** — Given a read-only HubSpot private-app token, When a HubSpot read tool runs through the
      gate + audit, Then governed CRM read data is returned with no vault and no per-user auth.
      _(test: integration — real API, manual)_
- [ ] **AC9** — Given users A and B each connected to a per-user connector, When A invokes it, Then
      only A's downstream tokens/data are reachable and B's are never exposed. _(test: integration —
      real provider, manual)_
- [ ] **AC10** — Given a per-user connection near token expiry with rotation enabled, When two tool
      calls trigger concurrent refresh, Then the per-key lock serializes refresh and neither call is
      locked out. _(test: integration — manual drill)_
- [ ] **AC11** — Given a user with no Slack connection, When they complete the connect flow and then
      run a Slack read tool, Then tokens are stored encrypted keyed on `sub` and their own Slack data
      is returned. _(test: e2e — manual)_
- [ ] **AC12** — Given an offboarded user, When the purge runs, Then all their vault tokens are
      deleted locally and revoked at the provider. _(test: integration — manual)_

## Open questions

- **FastMCP `OAuthProxy` per-client consent** — resolved by the Phase-2 spike (see `(PENDING SPIKE)`);
  determines how much confused-deputy defense we write vs. inherit.
- **Granola residency sign-off** (owner: Frederik) — is US processing under DPA/SCCs acceptable given
  the deliberate EU posture? A one-page memo blocks/unblocks Phase 5. No code until signed.
- **L1 build-vs-buy trigger** (owner: Frederik) — default is build; at what connector count (or
  ops-burden threshold) do we adopt **Nango self-host** instead of owning OAuth refresh mechanics?
- **ContextForge accelerator eval** — stand up IBM ContextForge (EU Railway) and test a read-only
  virtual-server allow-list; decide gateway-vs-direct-build **before Phase 3**.
- **HubSpot scope coverage** (owner: Frederik) — confirm the REST read scopes cover every object type
  needed, including **custom objects** (which the official HubSpot MCP omits).
- **Per-user authorization model** (architecturally significant → surface to `ARCHITECTURE.md` /
  backlog) — is the org-domain gate sufficient, or do we need per-connector allow/deny **per user**?
- **Third-hop auth flow** (architecturally significant) — must be added to `docs/ARCHITECTURE.md` when
  built (the surface-up rule); the doc currently describes only the two-hop v1.

## References

- `prd_01_aretea_drive_mcp_connector_read_only_v1.md` — the read-only connector + two-hop model this
  extends (FR2′, AC8/AC12, the SA data boundary).
- `prd_02_ci_cd_continuous_deployment_v1.md` — the pipeline every new connector inherits.
- `docs/2026-07-03-connector-build-vs-buy-research.md` — the sourced build-vs-buy study (6 research
  lanes + adversarial verification) this PRD summarizes; all vendor claims are cited there.
- `docs/ARCHITECTURE.md` — two-hop design + storage; to be extended with the per-user third hop.
- Load-bearing external sources: **MCP authorization spec 2025-06-18** (token-passthrough prohibition,
  confused-deputy); **HubSpot remote MCP GA 2026-04-13** (read+write); **Slack MCP server** (write
  tools; opt-in refresh rotation); **Granola API & residency** (per-user `grn_`, US-only); **Nango
  self-hosting**; **IBM ContextForge** (Apache-2.0). Full URLs in the research note.
