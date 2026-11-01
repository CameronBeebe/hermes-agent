# Opt-in context preview

A standalone inspection artifact, **not live context filtering**. Nothing replaces `read_file`
results, edits a conversation/system prompt, or changes Hermes configuration. The default preview
uses heading-aware segmentation and direct evidence signals. Enriched signals and dependency
recovery remain explicit alternatives, not recommended defaults.

## Browse saved evidence — one command, no API calls

From the checkout:

```bash
bash scripts/context-preview.sh --report ignored/context-map-factorial
```

The launcher refreshes HTML from saved `map.json` files, prints an available
`http://127.0.0.1:PORT/` URL, opens the browser, and serves until Ctrl-C. Python 3.10+ standard
library only for saved browsing: no installation, credentials, provider calls, CDN, or scripts
in the page. `--python /path/to/prepared/python` chooses an existing interpreter read-only.
`--no-open` prints the URL without launching a browser; `--port 8766` requests a specific port
and fails clearly if occupied; default `--port 0` chooses an available port. `--render-only`
refreshes and exits. Restart the server after regenerating reports: it serves a fixed snapshot.

Only known artifact names under the chosen directory are served. No directory listing, parent
traversal, arbitrary source-path serving, symlink targets, repository root, or runtime state.
The server binds only loopback, checks Host, sets CSP/nosniff/no-store, and serves original text
as `text/plain`. Loopback is **not authentication against other local processes/users**. Local
reports contain original, potentially sensitive source; do not publish them. Choose only report
directories you intend to inspect. Source strings and stored JSON are untrusted data.

## Preview one UTF-8 file — one command

Offline recovery/UX mode (all evidence unavailable and retained; no invented scores):

```bash
bash scripts/context-preview.sh --python "${HERMES_PYTHON:?Use an existing prepared interpreter}" --file public-manual.md --task 'What is the retention limit?' --intent 'Find the rule, definitions and exceptions' --output ignored/my-preview
```

Actual mapping requires the **additional** explicit flags `--live --allow-export`. This exports
masked copies of the complete bounded file, task, intent and basename to TypeSafe. It may incur
provider charges. Use only a file you are authorized to export. The existing profile-scoped
`TYPESAFE_API_KEY` resolver is read-only; keys are not printed. Mapping uses the existing project
`httpx`/redaction utilities, so select a prepared project interpreter; the launcher never installs
or mutates dependencies. Live failures return nonzero after inspection while preserving recovery
artifacts. An existing output directory is refused.

The preview CLI defaults to `--mode heading` and direct-only. Use `--mode window` or `--enriched`
to inspect alternatives. `--second-pass` requires `--enriched`. There is no browser button that
exports data. Saved-report browsing and live mapping are separate operations.

## What to inspect

- **Comparison:** four original arms, first pass versus after recovery, metric definitions,
  source/task/intent per case, synthetic versus public provenance, and clickable alternatives.
  Missing metrics are unavailable, never zero. Original public admission failure is preserved;
  the smaller-batch replacement has its own disclosed table and report.
- **Selected passages:** exact extractive text by default, path and line/column links, explicit
  leading/interior/trailing omission gaps. Source-order navigation distinguishes retained,
  omitted, uncertain and unavailable regions. Uncertainty is not positive evidence.
- **Recovery:** inspect any omitted passage inline or open the complete line-anchored source;
  download exact UTF-8 bytes. No summaries or invented bridges join disjoint excerpts.
- **Audit:** expandable probabilities/reasons, raw input metadata, questions and receipts.
  Older saved maps did not capture exact question payloads; the UI says **unavailable**, rather
  than reconstructing them and pretending they were observed. New maps record masked state and
  attempted question batches; receipts determine whether an attempt reached the provider.
- **Outcomes:** manually designated span coverage is **not task correctness**. Retaining all
  source trivially covers every planted span. Negative neighbor results and recovery with no
  added characters remain visible. Monetary cost is unknown without provider billing data.

Artifacts: `report.html`, `source.html`, `source.txt`, `packet.txt`, `packet-labeled.txt`, `map.json`.
HTML is self-contained CSS with no JavaScript or remote assets; companion source/packet links
require the report directory. `index.html` is the collection landing page (or the single-file
preview). Refresh changes generated HTML/labeled display packets only; original maps, source,
raw packets, scores and receipts remain unchanged. New directories/files are private.

## Map and safety contract

Markdown ATX headings plus a character ceiling (default 700) are not a full parser. Window mode
uses equal-character partitions. Every character is covered exactly once. Character offsets are
zero-based half-open; UTF-8 byte offsets refer to original source; lines/columns are one-based,
end column exclusive. CRLF is preserved in downloads. Rendering validates source slices,
coordinates and packet correspondence, plus SHA-256 and UTF-8 byte offsets when present;
corrupted saved provenance is rejected. Older maps without these optional metadata fields
remain readable; absent fields are not independently verified.

Direct asks readable evidence and concrete task relevance. Enriched adds prerequisite, exception,
instruction and neighbor signals. Positive threshold is `>= .8`; `.2 < p < .8` on active selection
signals or readability `< .8` retains as uncertain. Unknown scores retain as unavailable. Scores
are not calibrated correctness probabilities. Neighbor expansion is immediate/nonrecursive.
Optional recovery evaluates each omitted candidate (at most 48) and can only add, never delete.

Export is fixed to `https://api.typesafe.ai/v1/systemone`, requested model `jev-latest`, served
model in receipts. No proxy environment, redirects, retries, provider fallback or endpoint option.
Source/task/intent/path copies are redacted before questions; changed lines are masked preserving
character offsets. This is pattern/key redaction, **not a PII or injection-immunity guarantee**.
Original local files remain unredacted.

Bounds remain unchanged: 30 attempted requests / 300,000 conservative reserved input tokens per
invocation; 65,536-byte payload, 131,072-byte response, 96 questions/request, source export at most
16,384 bytes and 96 regions, task 2,000 chars, intent 1,000 chars. No prefix truncation to fit.
Dedicated transport process is killed at 35 seconds. Unknown/failed attempts keep reservations.
Admission failures are visible without being confused with successful retention. Historical
artifacts with generic errors retain those errors rather than rewriting the original evidence.

## Experiment evidence and reproduction

[CONTEXT_MAP_RESULTS.md](CONTEXT_MAP_RESULTS.md) explains the frozen synthetic/public corpus,
negative findings and usage. [context-map-results.json](context-map-results.json) preserves the
aggregate, receipts and representative slices; complete source/oracles are in `context_map_cases/`.
The larger saved comparison is `ignored/context-map-factorial`; earlier tiny, confounded runs
are `ignored/context-map-live-01` and `ignored/context-map-live-02`. Those ignored artifacts are
not distributed by git. The viewer can refresh any compatible saved map directory.

For an explicitly authorized four-arm experiment, the existing runner remains available:

```bash
"${HERMES_PYTHON:?Use an existing prepared interpreter}" -m scripts.context_map_experiments --case scripts/context_map_cases/atlas-retention.json --output ignored/new-atlas --ledger ignored/authorized-session-ledger.json --live --allow-export
```

Reuse the **same ledger** across authorized invocations: 35 requests / 500,000 accounted input
tokens, in addition to unchanged per-invocation caps. Do not reset a ledger to evade budgets.
Keep the ledger in a private, trusted parent directory. Updates use private, exclusively
created same-directory temporary files and atomic replacement, never a predictable `.pending`
file. Use one process at a time. After a crash, remove a stale `.lock` only after confirming
no process is using the ledger; preserve the ledger and its pending reservations.
For the public enriched arm, `--batch-regions 6` avoids the original 12-region payload refusal;
this is a disclosed protocol intervention, not a clean replicate. Oracles are saved before
classification and never exported. `context-map-demo.sh` remains the legacy tiny-battery runner.

## TypeSafe semantic_find comparative baseline

[TypeSafe's semantic_find cookbook](https://docs.typesafe.ai/cookbooks/semantic_find) is
prior art for tagged-source retrieval: **one Choice over all IDs plus an independent Noul
answer-exists question in the same request**, with shared document state. Its 218 lines are
pre-split clauses, not arbitrary physical source lines. Choice allows at most 255 options.
This baseline instead uses the existing heading regions (700-character ceiling) for a controlled
comparison; the stricter existing 96-region / 16,384-byte source limits remain in force.

Select `--arm choice-exists --top-k 3` on the existing `context-preview.sh --file ...` workflow.
Heading/direct independent Noul remains the default; Choice cannot combine with window,
enriched signals or dependency recovery. The lower-level `context_map` CLI additionally needs
`--direct-only`. Export still requires **both** `--live --allow-export`; offline mode has no
scores and retains everything for recovery. No embedding/index pipeline or runtime integration.

- **Ranking:** one `where` Choice with `{region_id: null, ...}` criteria. Probabilities sum to
  one and compete across candidates: they are **not independent relevance probabilities**.
  A low value does not imply irrelevance, and a peaked winner cannot establish answer existence.
- **Existence:** a separate `exists` Noul evaluates the whole supplied document, independent of
  the ranking distribution (not a statistical-independence claim). `p <= .2` means model-judged
  **absent**, `p >= .8` **present**, otherwise **uncertain**. These are uncalibrated policy bands,
  not truth labels. Unlike the cookbook's middle label, `.5` is **not evidence of partial coverage**.
- **Selection:** present selects exactly `min(K, number of regions)`, sorted by descending Choice
  mass, ties by original source order. Default K=3, configurable 1–96, not tuned to this corpus.
  No relevance threshold is applied: even zero-mass candidates can fill K. Absent selects no
  packet, but retains every source passage, score, anchor and recovery link. Uncertain or
  unavailable retains the entire source, visibly distinguished from positive evidence.
- **Completeness:** neither existence nor top-K proves that the selected packet contains all
  definitions, prerequisites or exceptions. Known oracle misses are displayed prominently;
  every omitted passage remains inspectable. No automatic exception protection or completeness
  judgment is claimed. A completeness question would be a separate future experiment.
- **Validation:** exact question and option coverage; finite numeric probabilities/confidence
  in [0,1], rejecting booleans; sum within absolute 1e-6 of one (no renormalization); selected
  ID must be a maximal-probability option. Missing/unknown/malformed answers fail the whole
  judgment safely, not defaulting missing options to zero. Actual served model/usage are recorded.

Reproduce the small two-arm comparison with the existing experiment runner:

```bash
"${HERMES_PYTHON:?Use an existing prepared interpreter}" -m scripts.context_map_experiments --comparison choice-exists --top-k 3 --case scripts/context_map_cases/atlas-retention.json --output ignored/new-choice-atlas --ledger ignored/authorized-choice-ledger.json --live --allow-export
```

Use the **same ledger for the entire authorized follow-up**, including retries/invocations.
This comparison enforces a tighter 12-attempt / 100,000 accounted-input-token session cap,
using conservative reservations before requests and actual usage after valid responses. Failed
attempt reservations remain charged. Existing transport/per-invocation limits and factorial
35-request/500,000 session defaults are unchanged. Public direct uses two 12-region batches;
Choice ranks all 13 regions in one request. This difference is disclosed, not hidden.

The contribution here is an inspectable, provenance-preserving comparison against independent
Noul region selection, not invention of semantic search or the Choice+exists technique. The
cookbook example uses `jev-1.12`; our receipts record the actual served version, not that example.
See [CONTEXT_CHOICE_RESULTS.md](CONTEXT_CHOICE_RESULTS.md) and
[context-choice-results.json](context-choice-results.json) for the new run, including recall losses.
Historical factorial maps/results and the heading/direct recommendation are not replaced.

## Verification scope

Canonical `scripts/run_tests.sh` covers rendering, exact source/packet correspondence, Unicode
and CRLF, missing/admission/unavailable states, inert malicious HTML/paths, hyperlinks, offline
refresh, real loopback HTTP traversal/symlink/Host rejection, dynamic ports and launcher subprocesses.
Run `python scripts/check` for repository gates. The original UI revision required no provider
calls; the separate Choice follow-up used the bounded live calls recorded in its results.
Browser DOM/HTTP inspection is not pixel-level visual or assistive-technology verification;
those remain manual checks. No downstream task-quality benefit is established.
