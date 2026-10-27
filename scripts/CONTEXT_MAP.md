# Standalone context-map experiment

This branch adds a CLI experiment, **not** a Hermes tool, compression hook, or live context-dropping policy. It never edits a running conversation/config. No embeddings or generated summaries. It evaluates every bounded candidate against a known task and declared intent, then composes typed signals with a deterministic, inspectable rubric.

## One command (tested environment)

From this worktree:

```bash
bash scripts/context-map-demo.sh --python /Users/sciphi/Projects/hermes-agent-lab/.venv/bin/python --live --allow-export --second-pass --output ignored/context-map-new-run
```

Use a **new** output directory. Remove `--live --allow-export` for an offline artifact/coverage smoke test: no semantic judgments are invented; all regions are unavailable and retained. `--python` uses the existing prepared test environment **read-only**, without pip/uv mutation. Without `--python`, the launcher uses the documented `scripts/run-in-hermes-env` PM workflow in `ignored/context-map-dev-home`; that provisioning path was not exercised here. It deliberately does not use the production home. Shell-supplied `TYPESAFE_API_KEY` can be inherited; standalone module invocation resolves an existing profile scope or loads `get_hermes_home()` with `build_profile_secret_scope`, restores its scope, and never prints the key.

For your own authorized UTF-8 source, run from an activated environment:

```bash
python -m scripts.context_map --file public-manual.md --task 'What is the retention limit?' --intent 'Find the rule, definitions and exceptions' --live --allow-export --second-pass --output ignored/my-map
```

`--mode window --direct-only` selects the baseline. `--size` is a character ceiling (default 700; battery 180). Baseline still asks evidence-readability so missing evidence is not silently treated as irrelevance. The HTML includes source recovery, every retained/omitted region, fixed selection reasons, raw probabilities, ambiguity, errors, exact packet, and usage/latency/model receipts. `source.txt`, `packet.txt`, and `map.json` are companion artifacts. Each individual HTML is self-contained for inspection and includes the complete original source. Reports are local originals, **not safe to publish**: redaction applies only to service copies. Report directories/files use private permissions. Existing output directories are refused.

## Map contract

- Heading mode recognizes Markdown ATX headings and prefers line boundaries within each section; long lines are split at the ceiling. This is deliberately not a full Markdown/parser-based code segmentation engine. Equal-window mode partitions exactly every N Unicode characters, including mid-line splits.
- Character offsets are zero-based half-open; byte offsets reference original UTF-8; lines/columns are one-based (end column exclusive). CRLF is preserved. Every character is covered exactly once, including trailing text and long lines. Source SHA-256 and tests verify exact reconstruction.
- Six independent Noul questions per enriched region: readable evidence, direct evidence, prerequisite/definition, exception/contradiction, legitimate domain instruction, and need-neighbor. Questions explicitly repeat task, intent, path, region ID, line span and offsets: question IDs alone are not model-visible.
- All regions remain in shared state. Up to 12 regions' questions per request (72 enriched); this is exhaustive candidate coverage, not top-K. Source text is evidence, never rubric authority. Source/task/intent/path are redacted before request construction; affected original lines are fully masked while preserving character offsets. This is pattern/key redaction, **not a PII or injection-immunity guarantee**.
- Positive selection threshold is `>= .8`; `.2 < p < .8` on a selection signal or evidence `< .8` retains as ambiguous. Unknown scores retain as unavailable. Direct-only uses direct plus evidence, not the other four signals. Scores are not calibrated probabilities of correctness.
- A neighbor score `>= .8` retains immediate neighbors only, without recursive expansion. Known flaw: the model may confuse remote semantic dependencies with physical adjacency.
- Optional second pass asks, for **each omitted candidate**, whether it supplies a definition/dependency/continuation/qualification needed for the concrete retained packet. At most 48 omitted candidates, one request, never recursive. It can only add, never delete. Ambiguous additions are labeled. First-pass IDs/selected size remain recorded. This is a dependency hypothesis, not an independent correctness certificate.
- The packet is concatenated exact original slices in source order. There are **no invented transition sentences or summaries**. Gaps can produce misleading juxtaposition, so use region metadata; do not blindly substitute this into a live context. Full source is always the recovery route.

## Bounds and failure behavior

Explicit export consent; fixed `https://api.typesafe.ai/v1/systemone`; requested `jev-latest`; actual served model logged. No proxy environment, redirects, retries, provider fallback, or alternate endpoint. Existing `read_assessment` remains unchanged; only its endpoint constant and common secret/redaction utilities are reused.

Hard per-run caps: 30 attempted requests, 300,000 aggregate input tokens using pessimistic UTF-8-byte reservation plus framing allowance before calls, and actual returned usage as an additional stop. Failed attempts keep their reservation. This is a conservative local admission estimate, not a tokenizer/service-billing guarantee. Limits reset on a new invocation; the operator must account across invocations. This development session used 24 real requests total, below the initial 30-request/300k-input authorization.

Request payload <=65,536 bytes; response <=131,072 bytes; <=96 questions/request; source export <=16,384 bytes and <=96 regions; task <=2,000 chars; intent <=1,000 chars. Oversize semantic input is visibly unavailable, never prefix-truncated. HTTP timeouts are 20s; a dedicated one-request subprocess is killed at 35s, also bounding DNS/slow-drip/stalled transport. Key travels over stdin, not argv. Per-request timings include subprocess overhead. Exact question coverage, model identifier, finite probabilities in [0,1] (booleans rejected), and usage types are validated. Invalid batches yield unavailable regions and full recovery, not synthetic success. Live CLI returns nonzero on semantic failure while preserving available artifacts.

## Actual observations

Latest full battery: `ignored/context-map-live-02/index.html` and `battery.json`. Final-code smoke: `ignored/context-map-final-smoke/report.html`. Earlier pre-hard-deadline run: `ignored/context-map-live-01/`.

Served model: **jev-1.14.0** (not the stale catalog alias). Latest battery: **11 requests, 27,115 input / 3,273 output tokens**, 4.3158s summed request latency (0.2925–0.5115s/request including subprocess). Across both battery runs plus final smoke: **24 requests, 60,984 input / 7,303 output tokens**. No semantic service errors occurred.

| Synthetic case | Required-span recall baseline / enriched | Selected chars baseline / enriched |
|---|---:|---:|
| Late exception + definition | 3/3 / 3/3 | 343 / 343 |
| Linked deployment definition + command | 3/3 / 3/3 | 386 / 332 |
| Injected evaluator instruction + retry override | 2/2 / 2/2 | 360 / 156 |
| Boundary-split qualified limit | 1/1 / 1/1 | 403 / 162 |

Total selected characters: **1,492 vs 993** (33.45% fewer); total original source 1,541 chars. Small planted fixtures are not a generalization claim. Heading segmentation and enriched questions change simultaneously, so this is **not a causal signal ablation**. A keep-everything strategy has perfect recall too.

### Misses / negative evidence, not just averages

No planted required-span misses were observed. However:

- **Late-exception map failed to omit anything.** Glossary neighbor=.90 retained the irrelevant dashboard-publicity region; exception neighbor=.87 retained the lunch schedule. All 343 chars survived. These are concrete selection precision misses.
- **Misleading Zeta publicity remained** because exception=.24 crossed the ambiguity band despite direct=.06. Conservative uncertainty handling reduces pruning, sometimes rightly and sometimes wastefully.
- Baseline retained irrelevant tails solely because readability was .74/.77 on boundary fragments. Recall was partly protected by fail-safe retention, not demonstrated semantic discrimination.
- Baseline included the injected evaluator note because it shared windows with needed evidence. Enriched isolated it and gave direct=.02, instruction=.02; the dependency pass gave .03. This is one successful decoy test, **not a prompt-injection security proof**.
- Linked glossary direct=.53 but prerequisite=.93: useful evidence that distinct semantic roles are visible. Nevertheless baseline already retained that definition in a mixed window; no recall gain was established here.
- All three executed recovery calls in the latest battery added **zero regions**. Final smoke also added none. Recovery wiring is exercised with a deterministic fake that actually adds a dependency, but live benefit remains unproven.

Next: separate segmentation from signal effects in a 2×2 ablation; add longer sparse fixtures with a truly missed remote prerequisite and a required boundary continuation; replace broad neighbor retention with explicit adjacent-pair qualification questions. Keep uncertainty/recovery visible rather than tune thresholds to force attractive compression numbers. No live harness integration until useful recall/precision tradeoffs survive harder examples.

## Verification

Tests were written and observed RED before each new implementation slice, then GREEN. Behavioral coverage includes complete segmentation/reconstruction, map composition, unavailable/invalid/missing responses, redaction, per-region question coverage, recovery, request/response/token bounds, deadline handling, scope restoration, inert HTML, original-byte artifacts, CLI export gate and the one-command launcher. Existing assessment regression suites also run. `scripts/check --staged --base HEAD` passed all 13 checks after resolving three lint findings. The repository test runner intentionally uses its own `/var/tmp/hermes-pytest-*` scratch roots even when TMPDIR/basetemp is supplied; no runner modifications were made. All demo artifacts remain under ignored directories; no production state, commits elsewhere, pushes, or PRs are touched.
