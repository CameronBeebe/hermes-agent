# Context-map follow-up: what actually helped

**Direction:** start with heading-aware direct selection and anchored packets; do not make enriched
signals or a recovery pass the default. Broad neighbor expansion made these maps worse. Directed
pair checks repaired that particular precision failure, but did not beat heading/direct overall.
The real public document still retained too much because readability judgments were uncertain.
This is an observational script experiment, not live harness integration.

## Design and frozen oracle

Four same-source arms: heading/direct, heading/enriched, window/direct, window/enriched. All use
700-character ceilings and the original .2/.8 rubric. Enriched first-pass results are reported
separately from dependency recovery. No threshold tuning; no answer-generating model or downstream
task evaluation. Single run per arm, correlated synthetic distractors, no significance claim.

| Case | Characters | Required passages | Layout |
|---|---:|---:|---|
| Atlas retention | 3,741 | 4 | deletion command, remote receipt prerequisite, day definition, late HOLD exception |
| Cinder rollout | 3,865 | 4 | action plus adjacent qualification, remote lane/receipt meaning, late freeze exception |
| Elm replay | 3,841 | 4 | retry command, checksum prerequisite, remote commit definition, late duplicate-seal exception |
| Public contributor guide | 5,793 | 6 | PM preparation/build, fresh-output caveat, runner/isolation, interpreter selection, lock/no-pip workflow |

The public guide was downloaded from the pinned public repository, **not** copied from the installed
private skill. Exact necessary quotes and offsets were manually selected before classification.[1]
The committed `context_map_cases/*.json` contain complete source and required/irrelevant spans;
`run_case` writes the oracle before sending any questions, and never sends oracle labels.

Explicitly irrelevant spans total 11,720 characters. Nonrequired text is **not automatically
irrelevant**: headers and unlabelled contextual prose are counted separately. Retain-all would keep
17,240 characters, including all 11,720 explicitly irrelevant characters, for the same 18/18 recall.

## Programmatically derived first-pass totals

Source total 17,240 characters; oracle 18 passages / 2,880 characters.

| Arm | Whole passages covered | Selected chars | Explicit irrelevant chars retained | Uncertainty-only chars | Unavailable chars |
|---|---:|---:|---:|---:|---:|
| Heading/direct | 18/18 | 7,978 | 3,092 | 4,628 | 0 |
| Heading/enriched | 18/18 | 12,500 | 7,389 | 5,265 | 0 |
| Window/direct | 18/18 | 13,740 | 8,220 | 7,893 | 0 |
| Window/enriched | 18/18 | 14,440 | 8,920 | 5,793 | 0 |

Heading/direct removed 53.72% of source characters while preserving every manually required
passage here. The synthetic subset is more favorable: 2,819/11,447 selected characters (75.37%
removed), 597/9,225 irrelevant characters retained, 12/12 spans. The public case dominates the
remaining failure: heading/direct selects 5,159/5,793, including **all 2,495 labelled irrelevant
characters**. Do not generalize synthetic pruning to arbitrary repository documents.

The public heading/enriched default batch was refused locally: payload 78,369 bytes > 65,536.
That original artifact retains all 5,793 as **unavailable**, not semantic success. The table uses
an explicitly disclosed follow-up of that arm with six regions per batch; same source/oracle,
segmentation and questions. It selected 5,384 characters with no unavailable regions. Original
failure totals remain in JSON. Reduced batching is a protocol intervention, not a clean unchanged
request-level replicate. Other arms did not require it; no security cap was increased.

## Inspectable misses and judgments

There were **no whole-passage or required-character misses** in completed arms. This is not proof
of sufficiency: uncertainty retention contributed heavily. Concrete precision failures:

- **Atlas heading/enriched r0002**, receipt prerequisite: direct=.95, prerequisite=.97,
  neighbor=.84. Its neighboring **r0001 Design assets** has direct=.02, prerequisite=.02,
  exception=.03, instruction=.02, yet is retained solely by `neighbor_of:r0002`.
- **Atlas r0005**, clear-day definition: neighbor=.86 adds Training calendar and Historical
  migration. Neither defines the term or qualifies the deletion rule. This is the actual failure
  motivating the opt-in pair experiment—not an assumed deficiency.
- **Elm heading/direct r0005**, ledger definition: direct=.61, evidence=.97. It survives as
  `ambiguous`, not positive direct evidence. Enriched marks prerequisite=.93, but this establishes
  a different semantic role, **not recall gain**.
- **Public heading/direct r0006**, Agent Loop: evidence=.69, direct=.05. It is retained because
  evidence < .8 despite clear irrelevance to environment setup. r0003 Adding a Tool similarly has
  evidence=.75, direct=.11. This looks like readability/relevance conflation, but the experiment
  does not establish its cause. No threshold was lowered to hide it.
- **Cinder r0001** says: “The permission in the preceding section applies only when the on-call
  operator has confirmed that the queue is empty. If it is nonempty, leave the old workers running
  and request a drain window.” The actual dependency is on r0000's rollout action, not r0002's
  design-assets section. Both required regions were already selected independently.

All original region texts, scores, reasons, line/column/byte offsets and misses are in the local
HTML/JSON maps. Committed results include representative original slices and pair judgments.

## Directed adjacent-pair comparison

Same frozen enriched maps, same oracle and thresholds; only existing broad-neighbor additions
are checked. First implementation supplied full text plus character offsets, without explicitly
labeled region text. Three live calls returned .39–.71 for the pairs and removed nothing. Those
negative artifacts remain under `heading-enriched-pairs/`.

After a regression test proved the missing labeled-region evidence, the next three calls supplied
explicit region IDs and exact masked slices. The result is informative but still exploratory:

| Synthetic case | Broad-neighbor selected / irrelevant | Labeled-pair selected / irrelevant | Required spans |
|---|---:|---:|---:|
| Atlas | 3,123 / 2,457 | 1,263 / 597 | 4/4 → 4/4 |
| Cinder | 1,401 / 611 | 790 / 0 | 4/4 → 4/4 |
| Elm | 2,592 / 1,826 | 1,363 / 597 | 4/4 → 4/4 |
| Total | 7,116 / 4,894 | 3,416 / 1,194 | 12/12 → 12/12 |

**3,700 irrelevant characters removed** with no oracle loss in those comparisons. Cinder's true
action→qualification pair scored .98 and qualification→action .89; qualification→Design assets
scored .01. Atlas receipt→Design assets scored .02 and receipt→Office logistics .01. Office
logistics still remains via its original ambiguity (.73 prerequisite), so the pair pass does not
silently override uncertainty. Heading/direct's 2,819 synthetic characters remain better than
pair-checked enriched's 3,416. No evidence yet that extra calls are worth making by default.

## Recovery, accounting and limitations

Six dependency-recovery requests ran; **zero regions/characters added**, no recovered misses.
There is no live second-pass dependency-recovery gain to claim. Fake-client tests only establish
that the wiring can add one; they are not included as empirical improvement.

This follow-up used **31 new requests**, **164,560 actual input / 12,960 output tokens**, served
**jev-1.14.0**. Summed request latency **13.5491s**, range **0.3238–0.6188s**, including worker
overhead but excluding preparation/test time. No provider error occurred. One payload admission
refusal made no HTTP request. API receipts do not report monetary charges; **spend is unknown**,
not zero, and no price was invented.

Across invocations the persistent ledger records all 31 receipts, including the three unsuccessful
offset-only pair calls. Reservations total 855,101 across six invocations; each invocation stayed
below its unchanged 300,000 reservation cap (160,324; 166,798; 153,257; 154,113; 172,791; 47,818).
Actual session input is below the authorized 500,000 and request count below 35. Failed/unknown
requests retain conservative reservations. Do not reuse a new ledger to evade a session budget.

**Next useful slice:** an anchored heading/direct preview with positive/uncertain/unavailable
provenance and immediate full-source recovery. Before live selection, investigate why intact
public irrelevant prose gets low readability, using held-out documents rather than fixture-tuned
thresholds. Keep directed pair checks optional; recovery currently costs calls without benefit.
Span preservation and selected-size metrics establish neither downstream task improvement nor
statistical significance.

## Artifacts and verification

- Local clickable index: `ignored/context-map-factorial/index.html`.
- Local aggregate: `ignored/context-map-factorial/aggregate.json`; persistent receipts:
  `ignored/context-map-session-ledger.json`.
- Committed aggregate/receipts/examples: `scripts/context-map-results.json`.
- Every map retains `source.txt`, exact `packet.txt`, optional `packet-labeled.txt`, `map.json`,
  `report.html`. The label variant makes disjoint passages visibly disjoint; it is not a security
  boundary and source text is still untrusted.
- Focused runner: 37 tests passed (26 existing + 11 added), including empty/oversize source,
  exact raw/labeled packets, four arms, frozen oracle, usage ledger, reduced batches, pair semantics,
  fail-safe retention and redaction. New behaviors were observed RED then GREEN. Additional
  assessment regressions bring the verified total to **95 passed across seven files**.

## Context-preview UI revision

The recommendation is now an opt-in static inspector. Run
`bash scripts/context-preview.sh --report ignored/context-map-factorial` to open a loopback URL.
The default view is selected source passages with anchored omissions, not raw JSON. Comparison
keeps all four arms, the original public admission error, the disclosed smaller-batch replacement,
and both directed-pair variants. Historical maps lack exact question payloads; this is explicitly
shown as unavailable, never reconstructed as an alleged receipt. New mapping attempts save masked
state/questions. Saved reports can be refreshed with no provider calls.

The aggregate JSON is deliberately preserved rather than rewritten: its 70 KB includes historical
negative evidence and receipts. The UI uses progressive disclosure instead of deleting provenance.
See [CONTEXT_MAP.md](CONTEXT_MAP.md) for the one-file workflow, export consent and server boundary.

## Separate Choice + exists comparison

The [TypeSafe semantic_find follow-up](CONTEXT_CHOICE_RESULTS.md) adds a selectable relative
Choice-ranking + independent answer-exists arm on the same heading regions. It credits the
cookbook and records new results separately: lower retained size, but three required-definition
misses at K=3 despite .99 answer existence. It does **not** replace the original results above
or the heading/direct default. Existence uncertainty is not partial coverage.

## Sources

[1] https://raw.githubusercontent.com/CameronBeebe/hermes-agent/e5f2b15300a3d04978e4c07cc64adc7bcf8e7b1c/skills/autonomous-ai-agents/hermes-agent/references/contributor-guide.md — Public contributor guide, pinned commit
