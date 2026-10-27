"""Run from the activated checkout: python -m scripts.read_assessment RECORD.json."""
import argparse
import json
from pathlib import Path


def _rescore(record):
    from agent.read_assessment import bounded_evaluate
    from agent.secret_scope import (
        build_profile_secret_scope, current_secret_scope, get_secret,
        reset_secret_scope, set_secret_scope,
    )
    from hermes_constants import get_hermes_home

    # Embedded callers already own their scope; standalone replay must load its profile
    # without publishing .env values into the shared process environment.
    token = None
    if current_secret_scope() is None:
        home = get_hermes_home()
        token = set_secret_scope(build_profile_secret_scope(home), profile_home=str(home))
    try:
        key = get_secret("TYPESAFE_API_KEY")
        return (bounded_evaluate(record["state"], record["requested_model"], key)
                if key else {"label": "unavailable", "reason": "missing_key"})
    finally:
        if token is not None:
            reset_secret_scope(token)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay read-v1 labels offline, or explicitly re-score saved evidence.")
    parser.add_argument("record", type=Path)
    parser.add_argument("--rescore", action="store_true")
    parser.add_argument("--allow-export", action="store_true", help="Consent to send saved evidence to TypeSafe again")
    args = parser.parse_args(argv)
    if args.rescore and not args.allow_export:
        parser.error("--rescore requires --allow-export (sends saved evidence; may incur charges)")
    from agent.read_assessment_typesafe import validate_and_label
    try:
        with args.record.open("rb") as handle:
            raw = handle.read(131073)
        if len(raw) > 131072:
            raise ValueError("record_limit")
        record = json.loads(raw)
        if record.get("rubric_version") != "read-v1" or record.get("provider") != "typesafe":
            raise ValueError("unsupported_record")
        if args.rescore:
            result = _rescore(record)
        else:
            result = validate_and_label(record) if record.get("answers") else {
                "label": "unavailable", "reason": "no_saved_answers"}
        result.update({k: record.get(k) for k in ("assessment_id", "session_id", "tool_call_id", "rubric_version", "provider")})
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 0
    except Exception:  # health: allow BLE001 -- CLI failure boundary must not echo evidence or credentials
        # Do not echo local evidence, key or remote error bodies to terminal/logs.
        print(json.dumps({"label": "unavailable", "reason": "replay_error"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
