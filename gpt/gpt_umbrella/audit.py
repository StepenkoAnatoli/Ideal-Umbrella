"""Offline inventories and API request advice. No network or credential access."""
import hashlib
import json
from pathlib import Path


def inventory(folder):
    root, result = Path(folder), []
    if not root.is_dir():
        raise ValueError("audit path must be a directory")
    for path in root.rglob("*.md"):
        if path.name not in ("AGENTS.md", "AGENTS.override.md", "SKILL.md"):
            continue
        if path.is_symlink() or any(part in (".git", "node_modules", ".venv") for part in path.relative_to(root).parts):
            continue
        text = path.read_text(encoding="utf-8-sig")
        result.append({"path": str(path.relative_to(root)), "characters": len(text),
                       "kind": "skill" if path.name == "SKILL.md" else "instructions"})
    return {"files": sorted(result, key=lambda x: x["characters"], reverse=True),
            "note": "Source-file sizes, not measured injected context. Scope, enabled state, and skill discovery affect runtime cost."}


def request_audit(requests):
    reports, previous = [], None
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        tools = request.get("tools", [])
        if not isinstance(tools, list) or any(not isinstance(t, dict) for t in tools):
            raise ValueError("tools must be an array of objects")
        def eager_count(items, depth=0):
            if depth > 10 or not isinstance(items, list) or any(not isinstance(t, dict) for t in items):
                raise ValueError("invalid/deeply nested namespace tools")
            return sum(eager_count(t.get("tools", []), depth + 1) if t.get("type") == "namespace" else
                       int(t.get("type") in ("function", "mcp") and not t.get("defer_loading", False)) for t in items)
        eager = eager_count(tools)
        canonical = lambda x: json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        stable = {"instructions": request.get("instructions"), "tools": tools,
                  "reasoning": request.get("reasoning"), "text": request.get("text")}
        digest = hashlib.sha256(canonical(stable).encode()).hexdigest()
        notes = []
        if eager >= 5:
            notes.append("Consider deferred tool search for eligible models; group related functions into small namespaces.")
        if previous:
            changed = [key for key in stable if stable[key] != previous[key]]
            if changed:
                notes.append("Potential prefix changes: " + ", ".join(changed) + ". Inspect actual cache diagnostics; this is not proof of a miss.")
        if "previous_response_id" in request and isinstance(request.get("input"), list) and len(request["input"]) > 1:
            notes.append("Check for replayed history: previous_response_id chaining normally sends only new input.")
        reports.append({"model": request.get("model"), "eager_tools": eager,
                        "tool_schema_characters": len(canonical(tools)), "prefix_settings_fingerprint": digest[:16],
                        "recommendations": notes})
        previous = stable
    return {"requests": reports, "note": "Offline heuristics only. Request contents are never included in this report."}
