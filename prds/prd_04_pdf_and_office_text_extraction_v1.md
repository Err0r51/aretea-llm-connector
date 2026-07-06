# PRD 5: PDF & MS Office text extraction v1

> **Status:** Active — Last refreshed: 2026-07-06

_Follows PRD 2 (`prd_01_…`, the read-only Drive connector). That connector reads Google-native Docs /
Sheets / Slides and plain-text files, but returns a **placeholder** for every other binary — so the
PDFs and MS Office documents that make up most of a real corpus are unreadable. This PRD closes that
gap by adding **in-process text extraction** for text-layer PDF and modern OOXML Office files, behind
the **identical** two-hop auth front and drive boundary — no new auth, no new scope, no mutation.
Header is "PRD 5" continuing the repo's sequence (root `prd-1` draft = 1, `prd_01_…` = "PRD 2",
`prd_02_…` = "PRD 3", `prd_03_…` = "PRD 4")._

## Problem

`drive_read_file` degrades every non-Google, non-text file to a single stated placeholder —
`"[binary — not text-extracted in v1]"` (`aretea_drive_mcp/gdrive/client.py` `_read_regular`,
`BINARY_PLACEHOLDER`). That covers, by construction, the **majority of an actual business corpus**:
PDFs (contracts, reports, scanned-then-OCR'd exports, board decks saved to PDF) and MS Office files
(`.docx` proposals, `.xlsx` models, `.pptx` decks). A curated AI-visible Shared Drive that Claude
can *search* but cannot *read* is a thin capability — a user asking "what does the Q3 board deck
say?" gets a placeholder, not an answer, and has no signal that the content exists but is
unextracted versus genuinely empty.

This was an accepted, explicit cut in the v1 connector — the `drive_read_file` docstring calls binary
extraction "a v1 fast-follow" (`aretea_drive_mcp/toolsets/drive.py`) — deferred so v1 could ship the
auth + boundary + governance spine first. That spine is now built and deployed (PRD 2). The
fast-follow is the highest-leverage next increment to the connector's actual usefulness, and it is
**self-contained**: it changes what one already-scoped, already-boundary-checked read path returns,
and touches no auth, no storage, and no tool schema.

## Goals

- **Read the documents that dominate a real corpus.** `drive_read_file` returns usable text for
  text-layer **PDF** and modern **`.docx` / `.xlsx` / `.pptx`** at basic fidelity — the same
  "basic-fidelity text, no layout" bar already set for Docs / Sheets / Slides.
- **Change nothing about the security model.** Extraction runs *after* the existing `assert_in_drive`
  boundary gate, over bytes fetched with the existing read-only `get_media`; no new scope, no
  mutation, no new auth hop. The read-only-by-construction posture (`prd_01_…` AC8) and the drive
  wall (`prd_01_…` AC10) are preserved unchanged.
- **Never crash, never lie.** Every un-extractable case (scanned/no-text-layer PDF, legacy format,
  encrypted, corrupt, oversized) returns a **stated** placeholder that names *why*, following the
  existing never-silent pattern (`prd_01_…` AC11). Boundary / permission errors still **raise**.
- **Bound resource use on the single worker.** A new **input-size guard** refuses oversized files
  *before* downloading them, so a large or malicious file cannot OOM the single-process container.

## Non-Goals

- **OCR for scanned / image-only PDFs.** A PDF with no text layer returns a stated placeholder; we do
  **not** rasterize-and-OCR it here. OCR is a categorically larger lift — it means either a heavy
  in-container engine (Tesseract: large image, native deps, friction with Railway's Metal builder) or
  a cloud OCR API (**data egress** — which collides with the EU-residency posture the org already
  flags for Granola in PRD 4). Deferred to its own PRD; surfaced in `BACKLOG.md`.
- **Legacy OLE binary formats (`.doc` / `.xls` / `.ppt`).** The pre-2007 binary formats need
  LibreOffice-headless or `antiword`-class tooling (heavy container weight) and are rare in a modern
  curated drive. They return a stated "legacy format unsupported" placeholder. Revisit only if the
  corpus proves to contain them.
- **Images, audio, video, archives.** No extraction; unchanged binary placeholder.
- **High-fidelity structure.** No page layout, positioning, embedded images, charts, drawing
  objects, comments, tracked changes, or speaker notes — mirrors the existing Docs/Sheets/Slides
  "text only" bar. Tables are flattened to text.
- **Any write / mutation capability.** No create/update/delete/share tool enters the schema —
  `prd_01_…` AC8 is preserved as the load-bearing safety control. In particular, the
  Drive-side "convert to a Google Doc then export" trick is **rejected** (see Decisions).

## Design

### Decisions (locked)

- **In-process extraction only — download bytes, parse locally.** `files.get_media` → raw bytes →
  format parser, all inside the process. _Rationale:_ the tempting alternative — have Drive convert a
  `.docx`/`.pdf` into a Google Doc and `files.export` it as text — is **off the table by the security
  model, not by preference**: `files.copy` with conversion is a **mutation** (breaks `prd_01_…` AC8's
  no-mutation-by-construction), and any scratch/staging drive to hold the conversion would require a
  **write scope** on the service account (breaks `prd_01_…` AC9's readonly-only, no-delegation). Local
  parsing is the only path consistent with both invariants.
- **Dispatch sits inside `_read_regular`, after the boundary gate.** `read_file` already calls
  `get_metadata` first, which runs `assert_in_drive` before any content is fetched
  (`client.py`). Extraction is reached only past that gate, so **the drive-boundary story is
  unchanged** — no new boundary surface. `_read_regular` is refactored from a 2-way branch
  (text vs. placeholder) into a **mime → extractor dispatch**.
- **Per-format pure-ish Python libraries, not an umbrella extractor.**
  - text-layer PDF → **`pypdf`** (BSD).
  - `.docx` → **`python-docx`** (paragraphs + tables).
  - `.xlsx` → **`openpyxl`** with `data_only=True` (cell **values, not formulas** — mirrors the
    existing Sheets `UNFORMATTED_VALUE` choice).
  - `.pptx` → **`python-pptx`** (per-slide shape text — mirrors the existing Slides text-walk).

  _Rationale:_ rejected `markitdown` / `unstructured` / Apache Tika — `unstructured` drags native
  deps (poppler, etc.), Tika needs a JVM in the image, and both fight the Metal builder and this
  codebase's minimal/auditable taste. Rejected **PyMuPDF/`fitz`** despite better quality: it is
  **AGPL**, a licensing problem for a proprietary hosted service.
- **`pypdf` + `openpyxl` are pure-Python; `python-docx` / `python-pptx` pull `lxml` (and `python-pptx`
  pulls `Pillow`).** These ship manylinux wheels, so no build toolchain is needed — but wheel
  resolution on `python3.12-slim-trixie` under `uv sync --frozen` is a `⚠ verify at build` item
  (Railway Metal builder). No `RUN --mount`, no `apt install` expected.
- **Input-size guard is a hard invariant.** Before downloading, compare the file's `size` (already in
  `FILE_FIELDS`) against a new `MAX_INPUT_BYTES` and refuse oversized files with a stated placeholder
  — **no bytes fetched**. If `size` is absent/None, **fail safe** (refuse with a stated placeholder)
  rather than download an unbounded blob. _Rationale:_ today only *output* is capped (`max_read_chars`)
  and Google refuses oversized *exports* (the 10 MB Doc placeholder); `get_media` on a binary has **no
  backstop**, and the container is **single-process, single-worker**, so an unbounded download + parse
  expansion can OOM it.
- **Decompression-bomb ceiling for OOXML.** `.docx/.xlsx/.pptx` are ZIP containers; `openpyxl` /
  `python-docx` / `python-pptx` will inflate a bomb. Enforce a max **uncompressed** size and refuse
  over the ceiling with a stated placeholder. _Note:_ this ceiling **cannot** key off the metadata
  `size` (that is the *compressed* zip size) — it must be enforced **inside the extractor while
  reading archive entries**. It is the one guard that lives in the parse, not the pre-download
  dispatcher.
- **Graceful degradation matches the existing pattern; permission/boundary errors still raise.**
  Scanned/no-text-layer PDF, encrypted file, corrupt file, legacy format, oversized, decompression
  bomb → **stated placeholder that names the reason**, never a crash. A Drive `HttpError` that is a
  permission/boundary failure (403/404) during `get_media` **must still propagate** — degradation must
  not mask a real access failure (this is the direct analogue of `_is_export_size_error` narrowly
  matching only `exportSizeLimitExceeded`, never a bare 403).
- **Output flows through the existing truncation.** Extracted text is returned as `content` and
  truncated by the existing `truncate()` / `max_read_chars` with the explicit note — never-silent
  (`prd_01_…` AC11) is inherited for free.

### Design details

**Dispatch shape.** `_read_regular(file_id, mime)` becomes a lookup over a `mime → extractor`
registry. Text MIMEs (`_is_text_mime`) keep today's `get_media` + UTF-8 (`errors="replace"`) path.
The new registry entries:

| MIME | Extractor | Output at basic fidelity |
|---|---|---|
| `application/pdf` | `pypdf` | concatenated page text; no-text-layer → stated placeholder |
| `…wordprocessingml.document` (`.docx`) | `python-docx` | paragraphs + table cell text, in document order |
| `…spreadsheetml.sheet` (`.xlsx`) | `openpyxl` (`data_only=True`, `read_only=True`) | per-sheet `# <title>` header + tab-joined value rows |
| `…presentationml.presentation` (`.pptx`) | `python-pptx` | `--- Slide N ---` header + shape text runs |

Anything not in the registry and not `_is_text_mime` → unchanged `BINARY_PLACEHOLDER`. Legacy OLE
MIMEs (`application/msword`, `application/vnd.ms-excel`, `application/vnd.ms-powerpoint`) map to a
distinct **legacy-unsupported** placeholder so the reason is legible.

**Extractors are pure `bytes → str` functions**, defined in a new module (e.g.
`gdrive/extract.py`), taking the downloaded blob and returning text (or raising a narrow
`ExtractionError` the dispatcher converts to a stated placeholder). They do **not** touch the Drive
client, the network, or the event loop — which is what makes them unit-testable against fixtures
without mocking Google (see Acceptance criteria). The one exception to "pure parse": the OOXML
decompression-bomb ceiling is enforced *within* these functions as they read archive entries (it
cannot live in the pre-download dispatcher — see Decisions). The blocking download + parse continue
to run inside the existing `anyio.to_thread.run_sync` offload in `read_file`'s `_extract`.

**New config** (`config.py`, env-loaded, validated at boot like the rest):
- `max_input_bytes: int` — refuse-before-download ceiling. Proposed default **52_428_800 (50 MiB)**;
  tunable per deploy.
- `max_uncompressed_bytes: int` — OOXML inflate ceiling. Proposed default **314_572_800 (300 MiB)**.

Both are proposals to confirm against the container's real memory headroom on Railway.

**Placeholder taxonomy** (each a distinct, stated string, in the never-silent spirit):
`[binary — not text-extracted]` (unhandled type, unchanged), `[PDF has no extractable text layer —
likely scanned; OCR not supported]`, `[legacy Office format (.doc/.xls/.ppt) unsupported — re-save as
.docx/.xlsx/.pptx]`, `[file is encrypted / password-protected — cannot extract]`, `[file appears
corrupt — could not parse]`, `[file exceeds the NN-MB extraction size limit — not downloaded]`.

**Known-limitation to document in code + tool docstring:** `openpyxl` `data_only=True` returns a
cell's **cached** value only if the app that wrote the file saved one; a spreadsheet generated
programmatically and never opened in Excel yields `None` for formula cells. This is inherent to
reading values without a formula engine (the same trade already accepted for Google Sheets).

**Tool-surface change:** `drive_read_file`'s docstring is updated to state the new supported set and
the placeholder reasons. **No new tool, no new parameter is required** for the core feature (an
optional PDF `page_range`, analogous to Sheets' `cell_range`, is a Phase 3 enhancement — see Open
questions). The served schema still contains only the three read tools.

## Phasing

Each phase is independently shippable and leaves the connector releasable.

1. **Extraction framework + PDF.** Refactor `_read_regular` into the dispatch; add `gdrive/extract.py`
   with the `bytes → str` contract and `ExtractionError`; add `max_input_bytes` + the input-size guard
   and the placeholder taxonomy; implement the `pypdf` text-layer path (incl. no-text-layer + encrypted
   + corrupt degradation). _Exit:_ AC1, AC5–AC7, AC9, AC11–AC13, AC15 green; a text-layer PDF reads
   end-to-end.
2. **OOXML trio.** Add `python-docx` / `openpyxl` / `python-pptx` extractors and the
   `max_uncompressed_bytes` decompression-bomb ceiling; legacy-OLE placeholder mapping. _Exit:_
   AC2–AC4, AC8, AC10 green.
3. **(Optional) PDF `page_range`.** Add a `page_range` parameter to `drive_read_file` for paging large
   PDFs, mirroring `sheet`/`cell_range`. _Exit:_ paging AC (to be written) green. Cut if not needed.

## Observability

- One structured log line per extraction outcome (reuse `structlog`), naming the branch taken
  (`pdf_text`, `docx`, `no_text_layer`, `oversize_refused`, `decompression_bomb_refused`,
  `legacy_unsupported`, `encrypted`, `corrupt`) and the file id — so the mix of what a real corpus
  actually contains, and how often extraction degrades, is visible in Railway logs. No file **content**
  is ever logged (consistent with the existing audit-line rule). The existing per-call audit line
  (`prd_01_…` AC12) is unchanged.

## Acceptance criteria

- [x] **AC1** — Given a text-layer PDF fixture, When `drive_read_file` reads it, Then it returns the
      page text at basic fidelity. _(test: unit, fixture)_
- [x] **AC2** — Given a `.docx` fixture with paragraphs and a table, When read, Then it returns the
      paragraph and table-cell text in document order. _(test: unit, fixture)_
- [x] **AC3** — Given an `.xlsx` fixture, When read, Then it returns cell **values** (never formula
      strings), per sheet. _(test: unit, fixture)_
- [x] **AC4** — Given a `.pptx` fixture, When read, Then it returns per-slide text. _(test: unit,
      fixture)_
- [x] **AC5** — Given a file whose `size` exceeds `max_input_bytes`, When read, Then it returns the
      stated over-size placeholder and **`get_media` is never called** (no bytes downloaded). _(test:
      unit, monkeypatch harness — assert the download is not invoked)_
- [x] **AC6** — Given a target whose metadata `size` is absent/None, When read, Then it **fails safe**
      (stated placeholder, no unbounded download). _(test: unit, monkeypatch harness)_
- [x] **AC7** — Given a scanned / no-text-layer PDF fixture, When read, Then it returns the stated
      "no extractable text / OCR not supported" placeholder, not a crash. _(test: unit, fixture)_
- [x] **AC8** — Given a legacy `.doc` / `.xls` / `.ppt` MIME, When read, Then it returns the stated
      "legacy format unsupported" placeholder. _(test: unit)_
- [x] **AC9** — Given an encrypted or corrupt fixture, When read, Then it returns the matching stated
      placeholder, not a crash. _(test: unit, fixtures)_
- [x] **AC10** — Given a crafted decompression-bomb OOXML fixture, When read, Then extraction is
      refused within the `max_uncompressed_bytes` ceiling (no OOM). _(test: unit, fixture)_
- [x] **AC11** — Given a file whose `driveId` ≠ the AI-Visible drive, When targeted, Then it still
      **raises** `DriveBoundaryError` before any download or extraction (boundary invariant
      preserved). _(test: unit, monkeypatch harness)_
- [x] **AC12** — Given extracted text longer than `max_read_chars`, When read, Then output is
      truncated with the explicit note and `truncated: true` (never silent). _(test: unit)_
- [x] **AC13** — Given the served tool schema, When inspected, Then it still contains **only** the
      three read tools — no mutation tool added (`prd_01_…` AC8 preserved). _(test: unit)_
- [ ] **AC14** — Given a real text-layer PDF in the AI-Visible drive, When Claude reads it live, Then
      it receives the document's text at basic fidelity. _(test: integration/e2e — live, no mock)_
- [x] **AC15** — Given a permission/boundary `HttpError` (403/404) raised by `get_media`, When read,
      Then it **propagates (refuses)** and is **not** swallowed into a placeholder. _(test: unit,
      monkeypatch harness)_

## Open questions

- **OCR strategy for scanned PDFs** — in-container Tesseract vs. cloud OCR vs. permanently
  out-of-scope. Blocked on the same EU-residency / egress constraint as Granola (PRD 4). _Surfaced in
  `BACKLOG.md`._ _(architecturally significant)_
- **`max_input_bytes` / `max_uncompressed_bytes` defaults** — confirm against the container's actual
  memory headroom on Railway `europe-west4`; the 50 MiB / 300 MiB figures are proposals.
- **PDF `page_range` paging (Phase 3)** — worth building now, or defer until a real oversized-PDF
  case appears? Truncation already degrades safely without it.
- **Resource-limit policy as a cross-connector concern** — the input-size guard is the first
  per-connector resource limit; future connectors (PRD 4) will want the same. Keep it connector-local
  for now or lift into the governance layer? _Candidate for `BACKLOG.md` if it recurs._

## References

- `prds/prd_01_aretea_drive_mcp_connector_read_only_v1.md` — the read-only Drive connector (AC8/AC9/
  AC10/AC11 invariants this PRD preserves; the `_read_regular` / `BINARY_PLACEHOLDER` this PRD
  replaces).
- `aretea_drive_mcp/gdrive/client.py` — `_read_regular`, `_is_text_mime`, `FILE_FIELDS`,
  `assert_in_drive`, `_is_export_size_error` (the degradation pattern this PRD mirrors).
- `aretea_drive_mcp/toolsets/drive.py` — `drive_read_file` docstring naming binary extraction "a v1
  fast-follow".
- `docs/ARCHITECTURE.md` — the two-hop design and the concurrency/offload model the extractors run
  under.
- `prds/prd_03_multi_service_connectors_and_governance_layer_v1.md` (PRD 4) — the EU-residency /
  egress posture that constrains any future OCR decision.
