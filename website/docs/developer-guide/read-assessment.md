# Read assessment (experimental)

Read assessment is an **observational post-read annotation**, not an access gate,
proof of correctness, or a measure of downstream task success. It currently covers
successful text `read_file` calls through the agent's sequential/concurrent tool
executor. It does not change the file result, insert judgments into model messages,
collect private reasoning, or call model tools recursively.

This feature stacks on `feat/read-file-declared-intent` (PR #1). That first feature
requires a brief declared objective; assessment independently compares that
objective, selected user context and the **actual returned excerpt**. Neither
switch implies the other. Core defaults for both assessment and its display are off.

## Enable deliberately

**Enabling exports selected task/context, file paths, intent and file text to
TypeSafe, and saves a redacted copy locally.** Do not enable on personal or
confidential work unless you approve this data flow and the provider's policies.
No configuration or launcher is changed by installing this branch.

In an already activated experimental checkout/profile, after reviewing privacy:

```bash
# Settings, not secrets:
hermes config set agent.read_assessment.provider typesafe
hermes config set agent.read_assessment.model jev-latest
hermes config set agent.read_assessment.enabled true
hermes config set display.read_assessment true

# Independently enable the first PR's objective contract/display if desired:
hermes config set agent.read_file_declared_intent true
hermes config set display.read_file_declared_intent true
```

Supply `TYPESAFE_API_KEY` through the active profile's secret environment or `.env`
(using setup/secret tooling, not config.yaml). It is registered as a secret and
resolved with `agent.secret_scope.get_secret`. An already-running gateway does not
inherit a later shell export: configure/restart **only your experimental gateway**.
There is no fallback to the primary model, OpenRouter, ambient provider routing,
or another endpoint. Provider and model must be selected explicitly.

Assessment settings are read at each completed read; declared-intent schema is
session-static, so start a new session after changing that schema setting.
`hermes config set agent.read_assessment.enabled false` stops future assessments;
`hermes config set display.read_assessment false` only hides labels (export and
local storage continue). Disabling does not cancel an already-started request.

### Classic CLI

With display enabled the live status rail prints, for example:

```text
  ┊ read_file [call_123]: helpful (read assessment)
```

The call ID is explicit, including for multiple concurrent reads of the same tool.
Invalid/control-bearing IDs display a generated assessment ID instead; the private
record retains the original correlation ID. The existing gateway `agent.print`
projection carries the line to the real classic CLI renderer; it is not merely
verbose JSON or an invented callback. Machine-readable/status-suppressed output
stays quiet. This is a status annotation, not a native Desktop/TUI assessment card
or a guaranteed messaging-platform notification.

## Evidence and privacy boundaries

Every request uses JSON-encoded evidence under an `evidence` key, separate from
fixed typed rubric instructions. All task/file/intent strings are untrusted data;
the rubric explicitly says not to follow instructions inside them. This is
injection resistance, **not proof that a classifier cannot be manipulated**.

Selection is deliberately small and deterministic, not a full conversation dump:

| Field | Maximum characters after redaction |
|---|---:|
| Latest text user message (current task proxy) | 2,000 |
| Two preceding text user messages | 750 each |
| Declared intent | 512 |
| Path | 512 |
| Prefix of returned text | 6,000 |

Only `path`, integer `offset`/`limit`, and intent are selected from arguments.
Mechanical metadata includes available truncation, total lines, size, next offset,
error status and binary/image/not-found flags. Evidence is the returned text after
tool transforms, before spill references, subdirectory hints and later turn-budget
trimming; it is not a promise that the primary model receives every assessed byte.
Failed/blocked reads are skipped, not labeled unhelpful.

Each text field records original character count, omitted characters and whether
redaction changed it. Provenance records the selection policy, omitted older and
non-text user messages, excluded roles and unknown arguments. System/developer
instructions, assistant text/reasoning, previous tool outputs, images and future
events are excluded. The latest user message may be a follow-up rather than a full
task specification; missing/ambiguous evidence should reduce the verdict, not be
silently filled in.

Forced Hermes secret-pattern and profile-vault redaction runs **before clipping**,
plus exact removal of the selected TypeSafe key. Existing redaction can preserve
credential prefixes/suffixes. This is not comprehensive PII or secret detection:
ordinary names, private prose, paths and unknown credential formats may remain.
Review evidence locally before enabling external assessment on sensitive work.

Local JSON records live under `$HERMES_HOME/read_assessments/<assessment-id>.json`
(new directory mode 0700, records 0600 on POSIX). Records contain session/call/
assessment IDs, rubric version, provider, requested/resolved model, bounded state,
validated typed answers, token usage, label and fixed reason code. They are separate
from the model conversation. They are not encrypted or automatically pruned;
delete them when no longer needed. A failed save is indicated in visible status
with `not saved`; it never breaks or re-executes a read.

## Rubric `read-v1`

The first adapter uses TypeSafe Jev's documented `POST
https://api.typesafe.ai/v1/systemone` contract: `{model, state, questions}`, Bearer
auth, a string state and three atomic `noul` questions. It validates exact question
IDs/types, finite probabilities in [0,1], safe resolved model identity and
nonnegative integer usage. Unexpected answer fields/types or malformed JSON are
unavailable, not accepted as confidence or rationale. No choice/score adapter is
claimed: this rubric deliberately uses only the documented yes/no primitive.

1. **Evidence:** Is there enough evidence (intelligible task/objective/readable
   excerpt) to judge immediate relevance?
2. **Relevance:** Is the excerpt relevant to the task, with recent user context?
3. **Objective:** Does the excerpt supply information addressing the declared
   read objective?

Deterministic mapping, in order:

- Evidence ≤0.2: `unavailable`, reason `insufficient_evidence`.
- Evidence <0.8: `uncertain`.
- Otherwise relevance ≤0.2 or objective ≤0.2: `unhelpful`.
- Relevance ≥0.8 and objective ≥0.8: `helpful`.
- Relevance ≥0.8 and objective ≥0.5: `partly_helpful`.
- Otherwise: `uncertain`.

Thresholds are a versioned heuristic, not calibrated certainty. Raw probabilities
are retained for inspection. Labels and reason codes are fixed rubric summaries,
**not model-authored explanations**. Missing key/config, transport failure,
malformed output, timeout and capacity exhaustion are `unavailable`, distinct
from an unfavorable judgment and from insufficient evidence.

## Latency, costs and transport

One outbound request (three questions) per successful eligible read. No retries.
The endpoint is fixed HTTPS; redirects and ambient proxy settings are disabled.
Request bytes are capped at 32 KiB, response bytes at 16 KiB; Unicode-heavy evidence
can exceed the byte cap even inside character limits and becomes unavailable.
The HTTP operation timeout is 3 seconds, with an additional 3-second caller wait
bound and at most four outstanding classifier workers process-wide. A timed-out
network operation may finish later but cannot update the saved verdict or display;
its slot stays occupied until it exits. No hard cancellation of DNS/OS sockets is
claimed. Concurrent read results are assessed in call order, so a batch of N reads
can add up to approximately N × 3 seconds plus local preparation/I/O. Reads are
already complete and persisted before assessment starts.

The service can bill each assessment even if the client times out. Token usage is
stored when returned; Hermes's main-model billing counters do not include it.
Consult the current TypeSafe pricing/account limits; no fixed price is assumed.

Official contract: <https://docs.typesafe.ai/api>, primitives:
<https://docs.typesafe.ai/primitives>, models: <https://docs.typesafe.ai/models>.

## Replay and explicit re-score

From this activated checkout (no plugins required):

```bash
# Offline: validate saved answers and recompute read-v1 label, no network/file re-read.
python -m scripts.read_assessment "$HERMES_HOME/read_assessments/RECORD.json"

# Online: explicitly consent to re-export the saved bounded evidence; may cost money.
python -m scripts.read_assessment "$HERMES_HOME/read_assessments/RECORD.json" --rescore --allow-export
```

Both print a JSON result and preserve the original record. They do not re-execute
`read_file`, recover omitted context, or reproduce historical provider weights.
A mutable alias such as `jev-latest` can resolve differently later. Offline replay
with no saved answers is unavailable. The re-score command is an explicit export
operation independent of the live `enabled` flag; inspect saved state first.

## Test the stack without touching production

Use a separate worktree and experimental `HERMES_HOME`/`HERMES_RUNTIME_DIR`, then
`source ./activate` as described in the package-management developer workflow.
Do not repoint a launcher or modify the checkout used by another interactive run.
Build a fresh disposable test interpreter with PM, not raw pip:

```bash
python -m pm.build_env --source . --out .venv --group dev --group test
scripts/run_tests.sh tests/agent/test_read_file_declared_intent.py \
  tests/agent/test_read_file_intent_display.py \
  tests/hermes_cli/test_read_file_intent_progress.py \
  tests/agent/test_read_assessment.py tests/agent/test_read_assessment_typesafe.py \
  tests/gateway/test_read_assessment_display.py tests/scripts/test_read_assessment.py -q
```

Tests use real temp-file reads, sequential/concurrent dispatch and private record
read-back, plus a local HTTP stub. They exercise the gateway-to-classic-CLI status
path and failure cases without exporting real traces. The separate implementation
smoke used only a synthetic `port = 8080` fixture: `jev-latest` resolved to
`jev-1.14.0`, returned 0.98 for each question and label `helpful` (805 input/56 output
tokens, observed 0.327 seconds). That one request establishes contract connectivity,
not accuracy, calibration or production gateway credential readiness.

### Limits

Direct registry/Python calls, `execute_code` RPC reads and provider-native runtimes
that bypass this executor are not assessed. No corpus evaluation, aggregate quality
metric, automatic remediation, main-model feedback, retrospective usefulness
judgment, private-reasoning extraction or factual-correctness guarantee is provided.
