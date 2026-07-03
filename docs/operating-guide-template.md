# CLAUDE.md — Project Operating Guide (Template)

> Drop this file at the root of your repo as `CLAUDE.md`. Fill in the
> `<placeholders>`, delete what doesn't apply, and keep it **concise and living**
> — this file is for codebase-level rules, not for describing current tasks.

## Project

<One-paragraph description: what the product is, who it's for.>

## Tech Stack

- **Backend**: <framework, language, DB, ORM, migration tool>
- **Frontend**: <framework, styling, component library>
- <Other cross-cutting choices: AI provider, auth, hosting, etc.>

## Development

```bash
<command>   # start dependencies (DB, etc.)
<command>   # run backend
<command>   # run frontend
<command>   # run tests
<command>   # run tests with coverage gate (what CI checks)
```

## Project Structure

```
<short annotated tree of the top-level modules — keep it to ~10 lines>
```

## Conventions

- **File naming**: <e.g. kebab-case files, PascalCase components>
- **Module pattern**: <e.g. controller → service → DTO>
- **Database**: <naming, enums, migration format>
- <Add a line whenever a convention crystallizes; delete lines that stop being true>

## Key Files

- `<path>` — complete data model
- `<path>` — core business logic
- `prds/` — PRDs for every major feature (reference before implementing)
- `prds/ROADMAP.md` — one-page living state-of-play
- `prds/BACKLOG.md` — lean list of future ideas (not committed to)
- `prds/ARCHITECTURE.md` — cross-cutting infrastructure capability map (consult before introducing new platform-level infra)
- `prds/TESTING_BACKLOG.md` — living map of remaining test-coverage debt
- `notes/` — dated, append-only research + session logs

---

## Documentation & Workflow

Five artifact types, each with a distinct purpose. **Use the lightest one that
fits** — over-documenting is as bad as under-documenting.

### 1. PRDs — *what to build and why*

- **Location:** `prds/`, numbered (`NN_TITLE.md`)
- **Write one when:** introducing a substantial new feature, a new architecture,
  or a concept that spans multiple files/modules. Rule of thumb: if the work is
  >1 day of implementation or affects multiple subsystems, it needs a PRD.
- **Skip when:** fixing a bug, iterating on existing code, refactoring within an
  established architecture, or doing routine work that follows existing patterns.
- **Lifecycle:** stable. A PRD reflects intent; don't rewrite it when reality
  drifts. If the approach changes, write a new PRD referencing the old one.
- **Must carry a test plan:** every PRD includes an `## Acceptance criteria`
  section written as Given/When/Then scenarios, and **each criterion maps to ≥1
  automated test** (unit / integration / E2E — pick the tier that fits). A PRD's
  implementation is not "done" until its acceptance criteria are green in CI.
  This is the Definition of Done.

#### PRD structure

Every PRD follows the same skeleton. Required sections in **bold**; the rest
are included when they earn their place:

```markdown
# PRD NN: <Title>

> **Status:** Active | Partial | Parked | Shipped — Last refreshed: YYYY-MM-DD
> (for Partial: one line on what shipped vs what's outstanding)

## Problem            ← REQUIRED. What hurts today, for whom, and why now.
                        Concrete symptoms, not solution language. If there's a
                        prior failure/incident/audit that motivated this, cite it.

## Goals              ← REQUIRED. What "done" changes about the world. Short list.

## Non-Goals          ← REQUIRED. What this PRD deliberately does NOT solve.
                        The highest-leverage section for preventing scope creep —
                        write it even when it feels obvious.

## Design             ← The approach. Split into:
   ### Decisions (locked)   — choices already made + one-line rationale each.
                              These are settled; don't re-litigate in implementation.
   ### Design details       — architecture, data model changes, API surface.
                              Depth proportional to risk; link out to notes for research.

## Phasing            ← For multi-step work: numbered phases, each independently
                        shippable, each with its own exit criterion. Phase 1 should
                        usually be "no behavior change" foundations when refactoring.

## Success criteria / Metrics   ← OPTIONAL but strongly recommended for anything
                        with a measurable outcome (perf work, cost work, quality
                        floors): the benchmark/baseline number today, the target,
                        and HOW it will be measured. Without a baseline, "improved"
                        is unfalsifiable.

## Observability      ← OPTIONAL: what logs/metrics/traces let you see it working
                        (or failing) in production.

## Legacy removal checklist  ← OPTIONAL: when replacing an old system, enumerate
                        every consumer of the old path that must migrate. This is
                        what makes "architectural changes must be holistic" checkable.

## Acceptance criteria ← REQUIRED. Given/When/Then scenarios; each maps to ≥1
                        automated test with its tier noted (unit/integration/e2e).
                        This IS the test plan — see Testing rules.

## Open questions     ← REQUIRED (may be empty). Unresolved decisions. Triage per
                        the surface-up rule below; strike through when resolved
                        with date + one-line resolution.

## References         ← Related PRDs, dated notes, external docs.
```

Notes on the required trio at the top: **Problem** without solution language
keeps the PRD honest when the approach changes later (the problem survives; the
design gets superseded). **Non-Goals** is where you record the tempting
adjacent work you're explicitly not doing. If a design choice needs sign-off,
mark the section `(NEEDS SIGN-OFF)` in the heading and resolve it before
implementation starts.

#### PRD lifecycle states

Every PRD is in one of these states. The state determines where it lives and
what's owed:

| State | Meaning | Lives in |
|---|---|---|
| **Active** | In flight; code is being cut | ROADMAP "Now" or "Next" |
| **Partial** | Some phases shipped, others outstanding | ROADMAP "Parked" with `Last refreshed:` date; PRD status header notes what shipped |
| **Parked** | Wanted, design largely valid, not in flight | ROADMAP "Parked" with `Last refreshed:` date |
| **Shipped** | Landed; no known follow-ups outstanding | ROADMAP "Recently landed" |
| **Subsumed** | Superseded by a later PRD; original framing no longer fits | `prds/archive/` with a header pointing at the superseder |
| **Deprecated** | Replaced by a same-number successor | `prds/archive/` |

**Parked + Partial PRDs decay.** Architecture drifts. New decisions land
elsewhere. A PRD written months ago may have a valid premise but an outdated
implementation path. **Before starting code on a Parked or Partial PRD whose
`Last refreshed:` is >30 days old**, do a refresh pass:

1. Re-read the PRD.
2. Survey the codebase for the subsystems it touches — has anything material
   changed since the PRD was written?
3. Write a refresh note: `notes/YYYY-MM-DD-prd-NN-refresh.md` covering what
   still holds, what's outdated, what new framing is needed.
4. **Then** start implementation.

Skipping the refresh produces silent drift.

#### Monthly PRD pulse

Once a month, walk all ROADMAP "Parked" entries. For each: still want it? still
valid premise? what would revive it? does anything intersect current Now/Next
work?

- **Also sweep the testing gates.** Walk `TESTING_BACKLOG.md`'s `🔒 Gated`
  section and test each item's **`Un-gate when`** trigger — *did the blocker
  ship?* Release any whose trigger is now met (move them into P0/P1/P2). This is
  the safety net for the "blocker delivered, nobody noticed" failure mode.
- **Output:** a single dated note `notes/YYYY-MM-DD-prd-pulse.md` listing each
  Parked PRD with its updated `Last refreshed:` date + a one-line "still holds /
  needs refresh / candidate for archive" — and any testing gates released.
- **Cadence:** triggered when a "what next?" question fires and the most recent
  pulse note is >30 days old or missing.
- **Time budget:** ~30 minutes. A freshness check, not a deep audit.

#### Open questions — surface up, don't trap inside the PRD

Every PRD's `## Open questions` section is a list of unresolved decisions. By
default these live *inside* the PRD — fine for small product/UX calls. **But:
open questions that are architecturally significant must also be surfaced in
the higher-level docs**, otherwise the next session has to re-read the PRD to
discover them, and they decay silently like Parked PRDs do.

Triage each open question:

- **Architectural (touches a cross-cutting platform):** lift into
  `ARCHITECTURE.md` — usually as a `**Known inflection point:**` block on the
  affected platform's entry. Include the trigger criterion (what condition
  forces a decision) + a back-link to the PRD.
- **Future-work-shaped (might become its own PRD someday):** lift into
  `BACKLOG.md` as a one-liner with `(open question from PRD NN)` annotation.
- **Small product/UX call:** stays in the PRD. Don't pollute higher-level docs
  with every minor TBD.
- **Resolved:** strike through in the PRD with the resolution date + a one-line
  note. If lifted to ARCHITECTURE.md / BACKLOG, remove the higher-level entry too.

When a PRD is **Shipped**, audit its open questions during the move: lift the
still-open ones up so they don't get buried under "this PRD is done."

#### Test coverage — close the loop on ship

Tests are part of a PRD's scope from the start, not a follow-up. The same
surface-up rule as open questions applies to test debt:

- **Plan it in the PRD.** The acceptance criteria are the test plan. Tier each
  criterion (unit / integration / e2e) as you write it.
- **On ship, audit coverage:** a PRD lands with its own criteria green, but
  substantial work almost always leaves *residual* test debt — adjacent code
  the change touched but didn't fully cover. **Log every such gap as a line in
  `TESTING_BACKLOG.md`** (P0/P1/P2 by risk, with a `(from PRD NN)` annotation)
  before the PRD moves to "Recently landed."
- **Release gates when you ship a blocker.** If the PRD you're shipping is the
  blocker for any `🔒 Gated` testing item, un-gate it in the same audit, and
  add a one-line back-reference in the shipping PRD so the dependency is
  visible from both ends.
- **The backlog is self-feeding and self-draining:** every landing PRD either
  closes its test debt, records it, or releases a gate; every later session
  that picks up a backlog line deletes it when the test lands.

The orchestration: **PRD → acceptance criteria → tests (now) → leftovers →
`TESTING_BACKLOG.md` → "what's next" → tests (later) → line deleted.**

### 2. Dated notes — *point-in-time findings*

- **Location:** `notes/`
- **Filename:** `YYYY-MM-DD-short-kebab-summary.md` (append `-a`/`-b` for
  multiple same-day notes)
- **Write one when:**
  - Returning to the project after a gap and you had to reconstruct the state
    (save a pickup plan)
  - You investigated something genuinely hard to rediscover (non-obvious bug
    root causes, architecture archaeology, surprising behaviour)
  - A work session produced findings that the next person — human or agent —
    will want before touching the same area
- **Skip when:**
  - The task was narrow (bug fix, one-file change, routine iteration)
  - The work is self-evident from the commit message and the code
- **Lifecycle:** **append-only. Never edit after creation.** The date is the
  truth. If things change, write a new note — don't edit the old one.

### 3. Roadmap — *what's next, in one page*

- **Location:** `prds/ROADMAP.md`, with sections: **Now**, **Next**, **Parked**,
  **Recently landed**
- **Update when:** priorities shift, a PRD lands, a track flips state.
- **Don't update for:** every small change. Commit messages are enough.
- **Lifecycle:** living. Kept deliberately short (≤ one page). If detail grows,
  push it into a dated note and link out.

### 4. Backlog — *future ideas, not committed to*

- **Location:** `prds/BACKLOG.md`
- **Add to when:** a useful idea surfaces but isn't ready to commit to.
  One-liner, optional 1-sentence context.
- **Skip when:** the idea is vague, probably won't matter, or the work is small
  enough to just do now.
- **Lifecycle:** living but **lean**. Items graduate to PRDs when committed
  (and get removed from the backlog). Stale items get deleted, not curated
  forever. **Never track implementation status here** — that's the trap
  backlogs fall into.

### 5. CLAUDE.md files — *code-adjacent conventions*

- **Location:** root `CLAUDE.md` (this file), optionally per-package
  (`server/CLAUDE.md`, `web/CLAUDE.md`)
- **Update when:** a convention crystallizes (naming, architecture, forbidden
  patterns) that applies to all future work in that area.
- **Lifecycle:** living, concise. For codebase-level rules, not current tasks.

### How to decide what to write

- **Am I making a narrow, scoped change in an established area?** → Just do the
  work. Commit. Done.
- **Did I have to investigate something hard before starting, and will someone
  need that investigation again?** → Dated note.
- **Am I introducing a new feature / architecture / cross-cutting concept?** →
  PRD, then implement.
- **Has the Now/Next picture shifted?** → One-line roadmap update.
- **Did an idea surface that we might do someday but aren't committing to now?**
  → One-line backlog entry.
- **Did I discover a rule that applies to all future work in this area?** →
  CLAUDE.md line.

If none of these apply, no documentation is needed. **Silence is a valid
output.** Over-documenting routine work creates noise that hides the important
notes.

**One thing the flowchart never makes optional: tests.** The branches above
decide *what docs to write*. Tests ship with the code, every time. "Just do the
work. Commit. Done." means *no extra docs are owed*; it never means *no tests
are owed*.

**When to run this flowchart — actively, at arc-completion, not only when
asked.** The trigger is the close of a substantial arc: a feature/PRD phase
lands, a multi-step investigation wraps, a PR closes a workstream phase, or
you're about to write a session summary. At those moments, proactively walk
every branch above — especially "did this session produce findings the next
person will need?" — and surface the suggestion *before* moving on. Momentum
beats reflection unless the completion-moment check is explicit.

### What NOT to do

- **No long-form "implementation plans" kept as living documents.** They
  silently go stale. Either it's a PRD (stable intent), a dated note
  (point-in-time snapshot), or a short roadmap line.
- **Don't edit old notes.** If a note from 3 weeks ago is wrong, the date makes
  that obvious — that's fine. Write a new one.
- **Don't document trivial work.** Commit messages are the right home for small
  changes.
- **Don't leave non-trivial research trapped in chat transcripts.** If a
  session produced findings worth keeping, save them as a note. Future sessions
  can't read chat history.

---

## Database Migrations

- Migrations live in `<path>` and run via `<tool>` — **never apply migrations
  manually** (no direct SQL against the DB).
- After creating a new migration file, run it and confirm success before
  continuing.
- **Serialization format changes require migrations**: when renaming or
  changing the stored format of data (a node type, a shortcode syntax, stored
  attributes), always write a migration to update existing records in-place.
  Without it, old records fail to parse under the new format.

---

## Rules

### Roadmap / PRD selection (mandatory)

When someone asks "what's next?", "what now?", or any prioritization question:

1. **Read `ROADMAP.md` and `TESTING_BACKLOG.md`** — test-coverage debt is real,
   committed work and belongs in "what's next" alongside feature PRDs — and
   check `notes/` for the most recent PRD-pulse note.
2. **If the pulse is >30 days old or missing, surface this before answering.**
   Don't silently skip the check.
3. **Scan available work in this exact order:**
   - **Now slot** — finish what's named first; only deviate with explicit
     direction.
   - **Active Partial PRDs** — work already in flight lands before new work
     starts.
   - **Testing backlog P0 (security/tenancy)** — committed debt that ranks
     *with* in-flight work, not behind it.
   - **Parked PRDs** — flag any whose `Last refreshed:` is >30 days old as
     "needs refresh first."
   - **ROADMAP "Next" + Testing backlog P1/P2** — only after the above; weigh
     new feature work against testing breadth on equal footing.
4. **Present options in that order with brief annotations** — readiness,
   spine-strengthening vs surface-broadening, estimated size. Don't bias toward
   the shiny-new; that reflex is exactly what buries parked work and test debt.
5. **For Parked work older than 30 days, never start coding without the refresh
   note first.**

### Testing & coverage (mandatory)

**Every code change ships with its tests, in the same change.** New feature,
bug fix, refactor — narrow or large — the matching tests are part of the work,
not a follow-up. This is the project's Definition of Done.

- **Plan tests up front, alongside the design.** A PRD without an
  `## Acceptance criteria` section (Given/When/Then) is incomplete. Each
  criterion maps to ≥1 automated test; the PRD is not "done" until they're
  green in CI.
- **Track remaining coverage debt in `TESTING_BACKLOG.md`** — a living,
  prioritized list (P0 security/tenancy first). When a gap lands a test, delete
  the line; when you spot a new high-value gap, add one.
- **Use the tier that fits the change:**
  - **Unit** — pure logic, transforms, guards, parsers. The cheapest,
    highest-ROI tier — most changes need at least this.
  - **Integration** — anything touching the DB, real migrations, tenancy/auth
    boundaries, external handshakes. Run against a real database (e.g.
    Testcontainers), as its own CI job.
  - **Component/E2E** — full user journeys and surfaces a DOM simulator can't
    faithfully reproduce.
  - For LLM-dependent code, build a **fake provider adapter** seam so it runs
    deterministically with no network or tokens.
- **Bug fixes are red-green.** Ship a test that **fails before the fix and
  passes after**. Demonstrate the red first — a test that passes against the
  unfixed code proves nothing. Never write a test that trivially passes or
  mocks the behavior away; it must exercise the real code path.
- **The coverage ratchet is a floor, not a target.** Configure coverage
  thresholds as **enforce-only** (no auto-update): the coverage run fails if
  coverage drops below the committed floor, and the floor never auto-rises.
  Raise it deliberately: edit the numbers a hair below newly-measured **CI**
  coverage (not local — uncommitted specs inflate local numbers) and commit.
  Adding code without tests lowers coverage and breaks the build. Never edit
  thresholds downward to sneak uncovered code through — add the tests instead.
- **CI enforces this on every PR:** typecheck + unit + coverage ratchet + the
  integration tier. A broken test or a coverage regression is a red build.
  Don't merge red; don't disable a check to go green.
- **Optional but recommended:** a `pre-push` hook that runs the unit suite +
  coverage floor for each workspace whose source changed, so regressions are
  caught before the push reaches CI. Emergency bypass: `git push --no-verify`
  (CI still gates).

### Architectural consistency (mandatory)

- **Follow existing architecture first.** Before implementing any feature,
  study the patterns already in the codebase. Never reimplement an existing
  capability using a different approach (e.g. introducing a localStorage-based
  chat when a server-side chat already exists). Build on top of what exists.
- **Architectural changes require explicit user approval.** If a task seems to
  call for an approach that diverges from the current system, **stop and
  discuss before writing any code**. Present the current architecture, explain
  why a change might be needed, and get explicit confirmation. Never silently
  introduce a parallel implementation.
- **Architectural changes must be holistic.** When a change is approved,
  migrate all related systems to the new approach. Don't leave the old
  architecture in place as legacy unless explicitly decided. Identify all
  consumers of the old pattern and include their migration in the plan.

### Platform consistency (mandatory)

Before introducing any **cross-cutting infrastructure** — a queue, a bus, an
integration surface, a scheduler, a storage layer, an auth flow, a streaming
primitive, a rate-limiter, anything future features will plausibly reuse —
**consult `prds/ARCHITECTURE.md`**.

- **If the capability exists, build on it.** The doc lists what each platform
  is for AND what it is NOT for. Misusing an existing platform for the wrong
  shape of problem is worse than introducing the right tool.
- **If the capability doesn't exist, the doc names the default candidate +
  escalation criterion.** Don't introduce a new infrastructure dependency
  without checking the recorded default — the "Not yet built" section captures
  decisions already weighed.
- **If a session introduces a new platform-level component, update
  `ARCHITECTURE.md` in the same PR** — new entry, "Last reviewed" bump,
  anti-pattern guardrail included. Without the doc update the next session has
  to re-derive.
- **The doc is the index, not the spec.** Each entry points at the PRD (or
  dated note) that owns the contract. ARCHITECTURE.md stays a ~1-page map;
  depth lives in PRDs and code.

### Tenant isolation (mandatory — multi-tenant apps)

Every server route that accepts a resource identifier (`:id`, a body/query id)
MUST verify the resource belongs to the caller's tenant **before** reading,
mutating, or decrypting it. **Auth guards do not do this for you** — proving
who the caller is doesn't prove the `:id` is *theirs*. Passing a user-supplied
id straight into a `WHERE id = ?` lookup is a cross-tenant IDOR.

- **Scope or gate, always.** Pass the caller's tenant id into a query that
  filters by it, or call an ownership gate first. Throw `NotFound` (not
  `Forbidden`) on mismatch. Resources with no direct tenant column gate
  transitively through their parent. Prefer enforcing at the sink (the query),
  not only the controller.
- **The tell is sibling asymmetry** — if neighbouring routes gate and one
  doesn't, that one leaks. New subsystems that read tenant data by id must
  wire the gate from day one (the standing failure mode is a later subsystem
  opting out).
- **Tests ship with it:** a cross-tenant regression test (foreign id →
  NotFound + no side-effect) against a *populated* foreign tenant, on the
  integration tier.

### Provider abstraction (mandatory — if the app calls LLMs)

All LLM calls go through a single **provider adapter** interface, obtained via
one factory. Direct imports of provider SDKs (`@anthropic-ai/sdk`, `openai`,
…) are forbidden outside the adapters directory.

- **Provider-specific features live inside the adapter.** If one provider has
  a capability another doesn't, that provider's adapter can exploit it; the
  rest of the code must still work when it's absent.
- **Tool definitions use JSON Schema** (provider-neutral); serialization stays
  inside the adapter.
- **Streaming events use neutral event types** — never leak provider-specific
  event shapes outside the adapter.
- **Provider selection is config-level** (one env var, one provider per
  environment). No per-call or runtime fallback logic.
- **Re-using an existing SDK client from a new call site is the anti-pattern**
  that creates bypass sites. New agent surfaces route through the adapter; if
  you genuinely can't, stop and discuss (architectural-consistency rule).
- **Model selection convention:** cheap/fast models for extractions and
  classification (cost), frontier models for complex tasks (quality).

### Customer-facing UX must not link to internal planning docs (mandatory)

Customer-facing surfaces (UI pages, setup guides, anything rendered to users)
must **NOT** link to: PRDs, dated notes, ROADMAP/BACKLOG/ARCHITECTURE,
CLAUDE.md files, or raw engineering docs. These leak internal organization
into customer UX and surface in-flight thinking as if it were stable docs.

OK to link: the app's own routes, third-party docs of platforms being
integrated, and a future public documentation site. If you want to link a PRD
from product UI: stop — inline the relevant info in a customer-facing
component instead (preferred: it forces customer language), or split the doc
into customer-facing and developer-facing halves.

### Dev processes (mandatory)

- **Check before touching a dev server.** Before start/stop/restart commands,
  check whether a server is already listening and whose it is
  (`lsof -nP -iTCP:<port> -sTCP:LISTEN`, `ps aux | grep <process>`).
- **Always ask before starting, stopping, or restarting a server.** This is a
  user decision, not an autonomous one. Reason: when the user runs the server,
  logs stream live in their terminal; when an agent starts it in the
  background, the user is debugging blind.
- **If a server runs in watch mode, prefer saving files and letting the
  watcher reload** instead of restarting.
- **Never kill/restart a server the user started** unless explicitly asked.
- **If the user confirms you should start one,** run it in the background,
  track the task id, and immediately tell the user the exact log-tail command
  with the full absolute path.

### Sizing estimates (mandatory — agent-driven development)

**Estimate work in agent-execution units, not human-developer units.**
Human-velocity anchors ("a week of work") are routinely off by 10×–50×.

| Shape of work | Realistic agent time |
|---|---|
| Single small file edit, no research | 1–3 minutes |
| Multi-file edit, established pattern | 5–15 minutes |
| New endpoint/module + UI wiring + typecheck | 15–30 minutes |
| Cross-cutting refactor with research first | 30–90 minutes |
| Substantial new subsystem incl. design conversation | a session (a few hours) |
| PRD-worth design needing user input throughout | spans sessions — gated by design questions, not execution |

- **Break estimates into phases** (research, design conversation, typing,
  verification, follow-up) — each has a different time profile.
- **Distinguish design time (user-gated) from execution time (agent-gated).**
- **Default to minutes, not hours; hours, not days.** If your gut says "a few
  days," challenge it — that's usually a borrowed human anchor.
- **For PRD-worth-it judgments, ignore the time estimate entirely** — use the
  rubric (multiple subsystems / new concept / needs durable explanation).

### General

- Check relevant PRDs in `prds/` before implementing features.
- Never expose sensitive keys in frontend code.
- Use the adapter pattern for provider-specific code (git hosts, AI providers).
- Encrypt stored third-party tokens (e.g. AES-256-GCM).
