# Backlog

Architecturally-significant open questions surfaced out of PRDs, so they don't decay trapped inside a
single spec (the create-prd surface-up rule). Each links back to its source PRD; resolve there, then
strike through here with the date.

## Open

- **Per-user / per-connector authorization model** — is the org-domain gate (`audit.py`
  `AuditMiddleware`) sufficient across connectors, or do we need per-connector allow/deny **per user**
  once services are per-user? _Source:_ `prds/prd_03_multi_service_connectors_and_governance_layer_v1.md`.
- **The per-user outbound-OAuth "third hop"** — the server-as-OAuth-client flow + `TokenVault` is a
  new cross-cutting auth layer beyond the two-hop v1. Must be written into `docs/ARCHITECTURE.md`
  **when built** (it currently documents only identity + fixed-SA hops). _Source:_
  `prds/prd_03_multi_service_connectors_and_governance_layer_v1.md`.
