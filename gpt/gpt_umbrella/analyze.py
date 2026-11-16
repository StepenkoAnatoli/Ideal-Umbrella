"""Read Codex JSONL rollouts and saved Responses JSON. Never emit chat text."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from .usage import KEYS, normalize, enrich, estimate


def discover(paths, latest=None):
    files = set()
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file():
            files.add(p.resolve())
        elif p.is_dir():
            files.update(x.resolve() for x in p.rglob("*.jsonl") if not x.is_symlink())
        else:
            raise ValueError(f"not a file or directory: {p}")
    ordered = sorted(files, key=lambda p: (p.stat().st_mtime_ns, str(p)), reverse=True)
    if latest is not None:
        if latest <= 0:
            raise ValueError("latest must be positive")
        ordered = ordered[:latest]
    if not ordered:
        raise ValueError("no transcripts found")
    return ordered


def rows(path, warnings):
    with path.open(encoding="utf-8-sig") as stream:
        if path.suffix == ".json":
            value = json.load(stream)
            yield value
            return
        for line in stream:
            try:
                yield json.loads(line)
            except (ValueError, RecursionError):
                warnings["malformed_json_lines"] += 1


def analyze(files, rates=None):
    if rates is not None and not isinstance(rates, dict):
        raise ValueError("rates must be an object keyed by model ID")
    warnings, tools, commands = Counter(), defaultdict(Counter), Counter()
    responses, legacy, summaries, seen_outputs, seen_calls = {}, {}, {}, set(), set()
    sessions_with_records = set()
    for path in files:
        model, session = "unknown", str(path)
        legacy_models = set()
        cumulative, last, window = None, None, None
        calls, local_ids, compactions, usage_records = {}, set(), 0, 0
        for event in rows(path, warnings):
            if not isinstance(event, dict):
                warnings["non_object_events"] += 1
                continue
            kind, p = event.get("type"), event.get("payload")
            p = p if isinstance(p, dict) else {}
            if kind == "session_meta":
                if isinstance(p.get("id"), str) and p["id"]:
                    session = p["id"]
                else:
                    warnings["invalid_session_metadata"] += 1
            if kind == "turn_context":
                model = p.get("model") if isinstance(p.get("model"), str) and p["model"] else "unknown"
            if kind == "compacted" or (kind == "event_msg" and p.get("type") == "context_compacted"):
                compactions += 1
                last, window = None, None
            raw, identity = None, None
            if kind == "token_usage_record":
                raw, identity = p.get("usage"), p.get("response_id")
                usage_records += 1
            elif kind == "response" or ("usage" in event and "output" in event):
                raw, identity = event.get("usage"), event.get("id")
                model = event.get("model") if isinstance(event.get("model"), str) and event["model"] else "unknown"
            if raw is not None:
                try:
                    u = normalize(raw)
                    if not isinstance(identity, str) or not identity:
                        warnings["usage_records_without_response_id_skipped"] += 1
                    else:
                        old = responses.get(identity)
                        # Final streaming counts replace earlier partial counts; don't sum them.
                        if old and any(u[k] < old[1][k] for k in KEYS):
                            warnings["non_monotonic_duplicate_usage"] += 1
                        elif not old or any(u[k] > old[1][k] for k in KEYS):
                            responses[identity] = (model, u)
                        local_ids.add(identity)
                except (ValueError, TypeError, AttributeError):
                    warnings["invalid_usage_records"] += 1
            if kind == "event_msg" and p.get("type") == "token_count":
                info = p.get("info")
                if isinstance(info, dict):
                    try:
                        candidate = normalize(info.get("total_token_usage"))
                        if cumulative and candidate["input"] < cumulative["input"]:
                            warnings["cumulative_counter_reset_totals_may_be_incomplete"] += 1
                        cumulative = candidate
                        legacy_models.add(model)
                        last = normalize(info.get("last_token_usage"))
                        value = info.get("model_context_window")
                        window = value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
                    except (ValueError, TypeError, AttributeError):
                        warnings["invalid_token_count_events"] += 1
            if kind != "response_item":
                continue
            item_kind, call_id = p.get("type"), p.get("call_id")
            if item_kind in ("function_call", "custom_tool_call", "function_call_output", "custom_tool_call_output"):
                if not isinstance(call_id, str) or not call_id:
                    warnings["invalid_tool_call_ids"] += 1
                    continue
            if item_kind in ("function_call", "custom_tool_call"):
                name = p.get("name", "unknown")
                if not isinstance(name, str):
                    name = "unknown"
                calls[call_id] = name
                if call_id and call_id not in seen_calls:
                    seen_calls.add(call_id)
                    tools[name]["calls"] += 1
                    args = p.get("arguments") or p.get("input")
                    try:
                        args = json.loads(args) if isinstance(args, str) else args
                    except ValueError:
                        args = None
                    # Hash only: reports cannot reveal commands, paths, secrets or prompt text.
                    cmd = (args.get("cmd") or args.get("command")) if isinstance(args, dict) else None
                    if isinstance(cmd, str):
                        digest = hashlib.sha256((str(session) + "\0" + cmd).encode()).hexdigest()[:16]
                        commands[digest] += 1
            elif item_kind in ("function_call_output", "custom_tool_call_output") and call_id not in seen_outputs:
                if not call_id:
                    continue
                seen_outputs.add(call_id)
                name = calls.get(call_id, "unmatched_output")
                output = p.get("output", "")
                size = len(output) if isinstance(output, str) else len(json.dumps(output))
                tools[name]["output_characters"] += size
                tools[name]["largest_output_characters"] = max(size, tools[name]["largest_output_characters"])
                tools[name]["outputs_over_12000_characters"] += int(size > 12000)
        if not local_ids and cumulative:
            legacy_model = model
            if len(legacy_models) > 1:
                legacy_model = "unknown (mixed legacy models)"
                warnings["mixed_model_legacy_totals_not_attributed"] += 1
            # Repeated copies of the same legacy session count once; use largest known total.
            previous = legacy.get(session)
            if not previous or cumulative["input"] + cumulative["output"] > sum(previous[1][k] for k in ("input", "output")):
                legacy[session] = (legacy_model, cumulative)
        elif cumulative and local_ids:
            if any(sum(responses[i][1][key] for i in local_ids) != cumulative[key] for key in KEYS):
                warnings["record_totals_differ_from_session_counter"] += 1
        if usage_records and not local_ids:
            warnings["no_valid_response_records_using_legacy_if_available"] += 1
        summary = {"session": str(session), "model": model, "response_records": len(local_ids),
                   "last_context_estimate": last["input"] + last["output"] if last else None,
                   "context_window": window, "compactions": compactions}
        summaries[session] = summary
        if local_ids:
            sessions_with_records.add(session)
            legacy.pop(session, None)
    for session in sessions_with_records:
        legacy.pop(session, None)
    totals, by_model = Counter(), defaultdict(Counter)
    for model, u in [*responses.values(), *legacy.values()]:
        totals.update(u)
        by_model[model].update(u)
    total_values = {k: totals[k] for k in KEYS}
    if not responses and not legacy:
        warnings["no_supported_usage_found"] += 1
    result = {"schema_version": 1, "files": len(files), "sessions": len(summaries),
              "response_records": len(responses), "legacy_session_totals": len(legacy),
              "usage": enrich(total_values), "by_model": {m: enrich({k: u[k] for k in KEYS}) for m, u in by_model.items()},
              "tools": dict(sorted(tools.items(), key=lambda x: x[1]["output_characters"], reverse=True)),
              "repeated_commands": [{"fingerprint": key, "occurrences": n} for key, n in commands.most_common(20) if n > 1],
              "session_details": list(summaries.values()), "warnings": dict(warnings),
              "notes": ["Cached/write input and reasoning output are subsets, not extra tokens.",
                        "Tool output sizes are characters, not tokens. Repeats may be necessary polling.",
                        "No subscription quota conversion or measured savings is inferred.",
                        "JSONL is version-dependent; legacy totals cannot deduplicate shared fork history.",
                        "Command fingerprints hide literal text but are not anonymization against guessing."]}
    if rates is not None:
        estimates = {}
        for model, u in by_model.items():
            try:
                if model.startswith("unknown"):
                    raise ValueError("model attribution unavailable")
                estimates[model] = {"usd": estimate(u, rates.get(model, {}))}
            except ValueError as error:
                estimates[model] = {"unavailable": str(error)}
        result["api_list_price_estimates"] = estimates
    return result


def compare(before, after):
    """Only normalize comparable measured responses; not a causal savings claim."""
    if before.get("legacy_session_totals") or after.get("legacy_session_totals"):
        raise ValueError("comparison needs per-response records in both reports")
    b, a = before["response_records"], after["response_records"]
    if not b or not a:
        raise ValueError("comparison needs nonempty reports")
    metrics, totals = {}, {}
    for key in ("input", "cached", "write", "ordinary_input", "output", "reasoning"):
        old, new = before["usage"][key] / b, after["usage"][key] / a
        metrics[key + "_per_response"] = {"before": round(old, 2), "after": round(new, 2),
                                          "change_percent": round((new / old - 1) * 100, 2) if old else None}
        old_total, new_total = before["usage"][key], after["usage"][key]
        totals[key] = {"before": old_total, "after": new_total,
                       "change_percent": round((new_total / old_total - 1) * 100, 2) if old_total else None}
    warnings = []
    if before.get("warnings") or after.get("warnings"):
        warnings.append("Input reports contain accounting/coverage warnings; inspect them before interpreting changes.")
    if set(before.get("by_model", {})) != set(after.get("by_model", {})):
        warnings.append("The model sets differ.")
    return {"totals": totals, "response_counts": {"before": b, "after": a}, "metrics": metrics, "warnings": warnings,
            "note": "Descriptive comparison only. Total work can rise even if average response size falls. Match task, model, tools, quality, and cache warmth before attributing a change to Umbrella."}
