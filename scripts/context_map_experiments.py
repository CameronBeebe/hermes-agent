"""Small reproducible ablations; not connected to the live context engine."""
import json
from pathlib import Path

from scripts import context_map as m
from scripts.context_preview import private_write


class SessionClient(m.Client):
    """Persistent authorization ledger, sequential use only; base caps unchanged."""
    def __init__(self, key, ledger, transport=None, *, max_requests=35, max_input_tokens=500000):
        super().__init__(key, transport)
        self.ledger = Path(ledger)
        self.max_requests = min(max_requests, 35)
        self.max_input_tokens = min(max_input_tokens, 500000)

    def ask(self, state, qs):
        lock = self.ledger.with_suffix(".lock")
        with lock.open("x"):
            try:
                return self._accounted_ask(state, qs)
            finally:
                lock.unlink()

    def _accounted_ask(self, state, qs):
        records = json.loads(self.ledger.read_text(encoding="utf-8-sig")) if self.ledger.exists() else []
        payload = json.dumps({"model": "jev-latest", "state": json.dumps(state, ensure_ascii=False),
                              "questions": qs}, ensure_ascii=False, allow_nan=False).encode()
        reservation = len(payload) + 4096 + 64 * len(qs)
        if len(records) >= self.max_requests:
            raise ValueError("session_request_budget")
        accounted = sum(r.get("usage", {}).get("input_tokens", r["reserved_tokens"]) for r in records)
        if accounted + reservation > self.max_input_tokens:
            raise ValueError("session_token_budget")
        records.append({"status": "pending", "reserved_tokens": reservation})
        self._save(records)
        before = len(self.receipts)
        try:
            return super().ask(state, qs)
        finally:
            if len(self.receipts) > before:
                records[-1] = dict(self.receipts[-1], session_request=len(records))
            else:
                records.pop()  # Base admission refusal made no request.
            self._save(records)

    def _save(self, records):
        private_write(self.ledger, json.dumps(records, indent=2))



def metrics(rows, required, irrelevant):
    """Oracle spans are disjoint; irrelevant is explicit, not all non-oracle prose."""
    result = m.span_metrics(rows, required)
    selected = [r for r in rows if r["selected"]]
    def overlap(spans):
        return sum(max(0, min(r["end"], s["end"]) - max(r["start"], s["start"]))
                   for r in selected for s in spans)
    def category(row):
        reasons = row["reasons"]
        if "choice_top_k" in reasons:
            return "ranking"
        if any(k in reasons for k in ("direct", "prerequisite", "exception", "instruction", "second_pass_dependency")):
            return "positive"
        if row["status"] == "unavailable":
            return "unavailable"
        if "ambiguous" in reasons or "second_pass_ambiguous" in reasons:
            return "uncertain"
        if any(k.startswith(("neighbor_of:", "verified_neighbor:")) for k in reasons):
            return "neighbor_only"
        return "uncertain"
    result.update(required_chars=sum(s["end"] - s["start"] for s in required),
                  required_chars_retained=overlap(required),
                  irrelevant_chars=sum(s["end"] - s["start"] for s in irrelevant),
                  irrelevant_retained_chars=overlap(irrelevant),
                  nonrequired_retained_chars=result["selected_chars"] - overlap(required))
    for label in ("positive", "neighbor_only", "unavailable", "uncertain", "ranking"):
        result[label + "_retained_chars"] = sum(r["end"] - r["start"] for r in selected if category(r) == label)
    result["miss_details"] = [{"name": s["name"], "missing_ranges": [
        [max(r["start"], s["start"]), min(r["end"], s["end"])] for r in rows
        if not r["selected"] and r["end"] > s["start"] and r["start"] < s["end"]]}
        for s in required if s["name"] in result["misses"]]
    return result


def run_case(case, output, client, size=700, batch_regions=12):
    """Freeze the oracle on disk BEFORE any classification; never send labels."""
    output = Path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / "oracle.json").write_text(json.dumps(case, indent=2), encoding="utf-8")
    record = {"name": case["name"], "source_chars": len(case["text"]), "variants": {}}
    for mode in ("heading", "window"):
        for enriched in (False, True):
            name = mode + ("-enriched" if enriched else "-direct")
            result = m.map_source(case["path"], case["text"], case["task"], case["intent"], client,
                                  mode=mode, enriched=enriched, second_pass=enriched, size=size, batch_regions=batch_regions)
            first = result.get("first_pass", {"retained": result["retained"]})
            first_rows = [{**r, "selected": r["id"] in first["retained"],
                           "reasons": [s for s in r["reasons"] if not s.startswith("second_pass")]} for r in result["regions"]]
            result["first_metrics"] = metrics(first_rows, case["required_spans"], case["irrelevant_spans"])
            result["metrics"] = metrics(result["regions"], case["required_spans"], case["irrelevant_spans"])
            m.save_report(output / name, result, labeled=True)
            record["variants"][name] = {k: result[k] for k in ("first_metrics", "metrics", "errors", "receipts", "second_pass")}
            (output / "results.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def aggregate(records, stage="first_metrics"):
    totals = {}
    for record in records:
        for name, variant in record["variants"].items():
            row = totals.setdefault(name, {"cases": 0, "source_chars": 0, "covered_spans": 0})
            row["cases"] += 1
            row["source_chars"] += record["source_chars"]
            values = variant[stage]
            row["covered_spans"] += values["required_spans"] - len(values["misses"])
            for key, value in values.items():
                if key.endswith("chars") or key in {"required_spans", "required_chars_retained"}:
                    row[key] = row.get(key, 0) + value
    return totals


def verify_neighbors(result, client):
    """Opt-in comparison: verify directed adjacency, never prune other reasons."""
    rows = result["regions"]
    pairs = [(anchor, rows[j]) for i, anchor in enumerate(rows)
             if (anchor["scores"] or {}).get("neighbor", 0) >= .8
             for j in (i - 1, i + 1) if 0 <= j < len(rows)]
    if not pairs:
        result["neighbor_verification"] = {"status": "not_needed"}
        return
    # No original source or model-provided metadata crosses the boundary unmasked.
    safe: dict = {k: m.redact_copy(result[k], client.key)[0] for k in ("source", "task", "declared_intent", "path")}
    safe["regions"] = [{"id": r["id"], "start": r["start"], "end": r["end"],
                        "text": safe["source"][r["start"]:r["end"]]} for r in rows]
    qs = {a["id"] + "." + c["id"]: {"type": "noul", "instructions": m.GUARD +
          f"Task: {json.dumps(safe['task'])}. Intent: {json.dumps(safe['declared_intent'])}. "
          f"Anchor {a['id']} chars [{a['start']},{a['end']}); Candidate {c['id']} chars [{c['start']},{c['end']}). "
          "Does this specific adjacent Candidate provide a continuation, referent, definition or qualification "
          "needed to interpret task-relevant evidence in this Anchor? Judge this directed pair, not some remote "
          "dependency. Physical proximity or shared topic alone is NOT sufficient."} for a, c in pairs}
    try:
        response = m.validate(client.ask(safe, qs), qs)
    except (ValueError, m.httpx.HTTPError, KeyError, TypeError):
        result["neighbor_verification"] = {"status": "unavailable", "warning": "Original conservative neighbor retention unchanged"}
        return
    for row in rows:
        row["reasons"] = [r for r in row["reasons"] if not r.startswith("neighbor_of:")]
    for anchor, candidate in pairs:
        p = response["answers"][anchor["id"] + "." + candidate["id"]]["noul"]
        candidate.setdefault("neighbor_pair_scores", {})[anchor["id"]] = p
        if p > .2:
            label = "verified_neighbor:" if p >= .8 else "uncertain_neighbor:"
            candidate["reasons"].append(label + anchor["id"])
    for row in rows:
        row["selected"] = bool(row["reasons"])
    result.update(m.finalize(rows))
    result["neighbor_verification"] = {"status": "scored", "answers": response["answers"], "model": response["model"], "usage": response["usage"]}


def run_choice_case(case, output, client, top_k=3, size=700, batch_regions=12):
    """Two same-region follow-up arms; never overwrite historical factorial results."""
    output = Path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / "oracle.json").write_text(json.dumps(case, indent=2), encoding="utf-8")
    record = {"name": case["name"], "source_chars": len(case["text"]), "variants": {}}
    for arm, name in [("independent-noul", "heading-direct-followup"),
                      ("choice-exists", f"heading-choice-exists-k{top_k}")]:
        result = m.map_source(case["path"], case["text"], case["task"], case["intent"], client,
                              mode="heading", enriched=False, size=size, batch_regions=batch_regions,
                              arm=arm, top_k=top_k)
        result["corpus"] = "public" if case.get("source_url") else "synthetic" if "synthetic" in case.get("source", "").lower() else "unknown"
        result["metrics"] = metrics(result["regions"], case["required_spans"], case["irrelevant_spans"])
        result["first_metrics"] = result["metrics"]
        m.save_report(output / name, result, labeled=True)
        record["variants"][name] = {k: result[k] for k in
                                    ("first_metrics", "metrics", "errors", "receipts", "second_pass")}
        record["variants"][name].update({k: result[k] for k in
                                        ("existence", "choice_answer", "top_k") if k in result})
        (output / "results.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ledger", type=Path, help="Reuse SAME ledger for every invocation in the authorized session")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-export", action="store_true")
    parser.add_argument("--batch-regions", type=int, choices=range(1, 13), default=12, help="Reduce batch size when long questions hit the existing payload cap")
    parser.add_argument("--comparison", choices=["factorial", "choice-exists"], default="factorial")
    parser.add_argument("--top-k", type=int, choices=range(1, 97), default=3)
    args = parser.parse_args(argv)
    if args.live and (not args.allow_export or args.ledger is None):
        parser.error("live requires --allow-export and --ledger")
    key = m.profile_key() if args.live else ""
    if args.live and not key:
        parser.error("missing scoped TypeSafe credential")
    limits = {"max_requests": 12, "max_input_tokens": 100000} if args.comparison == "choice-exists" else {}
    client = SessionClient(key, args.ledger, **limits) if args.live else m.OfflineClient("")
    runner = run_choice_case if args.comparison == "choice-exists" else run_case
    options = {"top_k": args.top_k} if args.comparison == "choice-exists" else {}
    record = runner(json.loads(args.case.read_text(encoding="utf-8-sig")), args.output, client,
                    batch_regions=args.batch_regions, **options)
    print(json.dumps({"output": str(args.output), "requests": client.requests, "input_tokens": client.input_tokens,
                      "output_tokens": client.output_tokens, "reserved_tokens": client.reserved}))
    return int(args.live and any(v["errors"] for v in record["variants"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
