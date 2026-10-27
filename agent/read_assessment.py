"""Observational, opt-in read assessments. Never modifies model messages or file results."""
import concurrent.futures
import contextvars
import json
import os
import threading
import uuid

from hermes_constants import get_hermes_home

# Hard cap on outstanding calls, including transports that outlive the caller deadline.
_SLOTS = threading.BoundedSemaphore(4)


def bounded_evaluate(state, model, key, *, wait_seconds=3.0):
    from agent.read_assessment_typesafe import evaluate
    from tools.daemon_pool import DaemonThreadPoolExecutor
    if not _SLOTS.acquire(blocking=False):
        return {"label": "unavailable", "reason": "busy"}
    def run():
        try:
            return evaluate(state, model, key)
        finally:
            _SLOTS.release()
    pool = DaemonThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(contextvars.copy_context().run, run)
        try:
            return future.result(timeout=wait_seconds)
        except concurrent.futures.TimeoutError:
            return {"label": "unavailable", "reason": "timeout"}
    finally:
        pool.shutdown(wait=False)


def _bounded(value, limit):
    from agent.redact import redact_sensitive_text
    from agent.secret_scope import get_secret
    text = value if isinstance(value, str) else ""
    key = get_secret("TYPESAFE_API_KEY")
    scrubbed = text.replace(key, "[REDACTED]") if key else text
    # Redact before clipping so a cut cannot turn a complete credential into an unmatchable prefix.
    safe = redact_sensitive_text(scrubbed, force=True)
    return {"text": safe[:limit], "omitted_chars": max(0, len(safe) - limit),
            "redacted": safe != text, "source_chars": len(text)}


def build_state(messages, args, result):
    parsed = json.loads(result)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("content"), str):
        raise ValueError("unsupported_read_result")
    users = [m["content"] for m in messages if m.get("role") == "user" and isinstance(m.get("content"), str)]
    arguments = {"path": _bounded(args.get("path"), 512)}
    arguments.update({k: args[k] for k in ("offset", "limit") if type(args.get(k)) is int})
    metadata = {k: parsed[k] for k in ("truncated", "total_lines", "file_size", "next_offset",
                "is_binary", "is_image", "not_found") if type(parsed.get(k)) in (int, bool)}
    metadata["error"] = bool(parsed.get("error"))
    return {"evidence": {"current_task": _bounded(users[-1] if users else "", 2000),
            "recent_user_context": [_bounded(text, 750) for text in users[-3:-1]],
            "arguments": arguments, "declared_intent": _bounded(args.get("declared_intent"), 512),
            "result_excerpt": _bounded(parsed["content"], 6000), "result_metadata": metadata},
            "provenance": {"selection": "latest text user message plus two preceding text user messages; excerpt prefix",
                "omitted_user_messages": max(0, len(users) - 3),
                "excluded_roles": ["system", "developer", "assistant", "tool"],
                "non_text_user_messages_omitted": sum(m.get("role") == "user" and not isinstance(m.get("content"), str) for m in messages),
                "unknown_arguments_omitted": len(set(args) - {"path", "offset", "limit", "declared_intent"}),
                "redaction": "forced Hermes secret patterns and profile vault values; not a PII guarantee",
                "scope": "returned text before spill/hints and turn-budget trimming; no future outcomes"}}


def assess_read(agent, messages, ref, result, *, blocked, is_error):
    """Fail-open at the observation boundary, including configuration, disk and UI failures."""
    if ref.name != "read_file" or blocked or is_error:
        return
    try:
        _assess_read(agent, messages, ref, result)
    except Exception:  # health: allow BLE001 -- observational boundary; traceback may expose evidence/secrets
        # Never log exception text: transport/config/renderer errors can embed evidence or credentials.
        return


def _assess_read(agent, messages, ref, result):
    from hermes_cli.config import load_config
    config = load_config()
    settings = (config.get("agent") or {}).get("read_assessment") or {}
    if settings.get("enabled") is not True:
        return
    import httpx
    from agent.secret_scope import get_secret
    record = {"assessment_id": uuid.uuid4().hex, "session_id": agent.session_id,
              "tool_call_id": ref.call_id, "tool": ref.name, "rubric_version": "read-v1",
              "provider": settings.get("provider"), "requested_model": settings.get("model"),
              "model": None, "label": "unavailable", "reason": "assessment_error"}
    try:
        state = build_state(messages, ref.args, result)
        record["state"] = state
        key = get_secret("TYPESAFE_API_KEY")
        if settings.get("provider") != "typesafe" or not settings.get("model"):
            record["reason"] = "invalid_configuration"
        elif not key:
            record["reason"] = "missing_key"
        else:
            record.update(bounded_evaluate(state, settings["model"], key))
    except httpx.TimeoutException:
        record["reason"] = "timeout"
    except httpx.HTTPError:
        record["reason"] = "transport_error"
    except ValueError:
        record["reason"] = "invalid_response"
    except Exception:  # health: allow BLE001 -- classifier failure must not break reads or log secrets
        record["reason"] = "assessment_error"
    try:
        directory = get_hermes_home() / "read_assessments"
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / f'{record["assessment_id"]}.json'
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=True, allow_nan=False)
    except OSError:
        record["persistence"] = "failed"
    if ((config.get("display") or {}).get("read_assessment") is True
            and not getattr(agent, "suppress_status_output", False)):
        import re
        call_id = str(ref.call_id)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", call_id):
            call_id = "assessment-" + record["assessment_id"]
        suffix = " — not saved" if record.get("persistence") == "failed" else ""
        agent._safe_print(f'  ┊ read_file [{call_id}]: {record["label"]} (read assessment){suffix}')
