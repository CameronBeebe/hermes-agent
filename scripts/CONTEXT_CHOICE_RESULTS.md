# Choice + answer-exists follow-up

**Outcome:** useful ranking baseline, not a new default. Top-3 reduced retained text and removed
all explicitly irrelevant spans here, but lost three required definitions. Heading/direct
independent Noul preserved all required passages. Answer existence did not detect packet
incompleteness. Historical factorial results and recommendation remain unchanged.

## Prior art and protocol

Credit: [TypeSafe semantic_find](https://docs.typesafe.ai/cookbooks/semantic_find), specifically
one Choice over tagged IDs and a separate Noul answer-exists question in the **same request**.
The cookbook ranks 218 pre-split clauses. We use the existing heading partitions, size 700,
with exact original character/byte/line provenance. This is a local comparative adaptation,
not a novel retrieval algorithm. [Choice response contract](https://docs.typesafe.ai/primitives/choice)
and [API](https://docs.typesafe.ai/api/system-one) were checked before implementation.

Frozen original Atlas, Cinder, Elm and pinned-public-contributor cases, plus a new absent-answer
query over the **unchanged synthetic Atlas source**. Atlas already requires command, remote
prerequisite, day definition and a late HOLD exception; Cinder and Elm likewise require four
separate passages including exceptions. No personal or installed-private content exported.
Oracles were saved before inference and were not sent to the service.

Each case compares fresh heading/direct independent Noul against heading/Choice+exists.
Top-K=3 fixed before the run, no tuning/recovery/completeness calls. Present >=.8; absent <=.2;
otherwise uncertain and retain-all. Uncertainty is not partial coverage. Missing or invalid
answers retain-all as unavailable. Stable source-order ties; exact top-K can include zero-mass
regions. Public direct needs two batches (12 + 1 regions); Choice uses one shared-state request
with two questions over all 13 regions. Synthetic cases need one request per arm.

## Observed results

| Case | Direct coverage | Direct chars / irrelevant chars | Choice coverage | Choice chars / irrelevant chars | Exists Noul |
|---|---:|---:|---:|---:|---:|
| Atlas retention | 4/4 | 1,263 / 597 | 3/4 | 533 / 0 | .99 present |
| Cinder rollout | 4/4 | 790 / 0 | 3/4 | 614 / 0 | .99 present |
| Elm replay | 4/4 | 1,363 / 597 | 3/4 | 581 / 0 | .99 present |
| Public contributor | 6/6 | 5,159 / 2,495 | 6/6 | 1,470 / 0 | .99 present |
| Atlas absent refund question | not applicable | 0 / 0 | not applicable | 0 / 0 | .01 absent |
| **Total** | **18/18** | **8,575 / 3,689** | **15/18** | **3,198 / 0** | — |

Totals computed from saved maps, not hand-estimated. Source is 20,981 characters across five
queries (Atlas text appears twice). Required evidence: 18 spans / 2,880 chars; Choice preserves
2,451 required chars. Direct retains 5,401 chars under uncertainty; Choice selects 3,198 by
**relative ranking**, a separate metric category, not positive independent relevance. No
unavailable results. Absence has no required spans and is not counted as a perfect-recall case.

### Inspectable failures and limits

- Atlas omits `clear-days`, r0005, ranking mass .01: a full UTC day after the close marker,
  excluding the marker day. It retains the HOLD exception (.18) and receipt prerequisite (.04).
- Cinder omits `lane-receipt-definition`, r0004, .02. Elm omits `recoverable-definition`,
  r0005, .01. Both retain their late exception. Four required regions cannot fit a top-three
  packet in these layouts: this is a structural K limitation, not proof the model misranked.
- Public coverage reaches 6/6 with three regions, but only r0008 (.88) and r0007 (.12) have
  nonzero mass. The third is r0000 through source-order tie-breaking. This is not independent
  evidence of r0000's relevance; different partitions/ties can change the result.
- Absent refund query: winner r0000 still gets .64, yet existence is .01 and the packet is
  empty. The source has no monetary refund amount. A winner always exists in a Choice
  distribution; its probability is not proof that the question has an answer.
- No live uncertain-existence outcome occurred. Tests cover .5 → uncertain/retain-all and
  .99 ranking winner with absent existence; those controlled responses are **not empirical
  performance results**. Tests also demonstrate a required exception omitted at K=1.
- No repeat runs, calibration, significance, downstream answer generation or task-quality
  evaluation. No evidence establishes partial coverage from an intermediate Noul value.
  Public success on one pinned file does not justify changing the default. Exceptions are
  not automatically protected: report warnings, known misses and full-source recovery are
  mandatory, not a claim the packet is safe for unattended use.

## Actual usage and artifacts

**11 real requests; 42,991 input / 2,909 output tokens; served `jev-1.14.0`**, requested
`jev-latest`. Summed request latency 6.3806s. No transport/validation/admission failures.
Persistent ledger stayed within 12 requests / 100,000 accounted input tokens, with conservative
pre-request admission and unchanged base limits. Monetary charges are unknown, not zero.

- Committed machine-readable evidence: `scripts/context-choice-results.json` (all new receipts,
  per-case metrics, full Choice distributions, existence values, protocol and aggregate).
- Complete reports: `ignored/context-map-factorial/choice-followup-<case>/`, with separate
  `heading-direct-followup/` and `heading-choice-exists-k3/` maps, questions, masked state,
  originals, anchored omissions and line-linked full recovery. Ignored maps are local only.
- Ledger: `ignored/context-choice-session-ledger.json`.
- Refreshed existing index: http://127.0.0.1:8766/ — new clearly labeled Choice follow-up,
  never substituted into the four original-arm aggregates.
- Example: http://127.0.0.1:8766/choice-followup-atlas-retention/heading-choice-exists-k3/report.html
- Before/after hashes verified **78 historical evidence files unchanged** (maps, originals,
  raw packets, oracles, results and aggregate); only generated views were refreshed.

Canonical `scripts/run_tests.sh`: **153 passed across 10 files**, including **33 Choice tests**;
new validation, arm integration, CLI/metrics/visual labels and explicit-miss display were observed
RED then GREEN. `python scripts/check`: **14 checks passed**, no blocking/advisory health findings;
`git diff --check` clean. Existing assessment, export, nonmutation and preview-server tests pass.
Browser text/DOM and HTTP checks establish readable labels and recovery links, not pixel-level
visual/accessibility review. No config, launcher, agent-context, embedding or provider changes.
