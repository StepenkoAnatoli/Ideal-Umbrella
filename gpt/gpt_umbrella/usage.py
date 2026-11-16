"""Normalize OpenAI usage without adding cached/reasoning subsets twice."""
import math

KEYS = ("input", "cached", "write", "write_30m", "write_12h", "output", "reasoning")


def integer(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**63:
        raise ValueError("token counts must be non-negative integers")
    return value


def normalize(raw):
    if not isinstance(raw, dict) or "input_tokens" not in raw or "output_tokens" not in raw:
        raise ValueError("missing input/output token counts")
    details = raw.get("input_tokens_details") or {}
    output = raw.get("output_tokens_details") or {}
    ttl = details.get("cache_write_tokens_details") or {}
    u = dict(zip(KEYS, map(integer, (
        raw["input_tokens"], raw.get("cached_input_tokens", details.get("cached_tokens", 0)),
        raw.get("cache_write_input_tokens", details.get("cache_write_tokens", 0)),
        ttl.get("ttl_30m_tokens", 0), ttl.get("ttl_12h_tokens", 0),
        raw["output_tokens"], raw.get("reasoning_output_tokens", output.get("reasoning_tokens", 0)),
    ))))
    if u["cached"] + u["write"] > u["input"] or u["reasoning"] > u["output"]:
        raise ValueError("usage subsets exceed their total")
    if u["write_30m"] + u["write_12h"] > u["write"]:
        raise ValueError("cache-write lifetime counts exceed write total")
    return u


def enrich(u):
    return {**u, "ordinary_input": u["input"] - u["cached"] - u["write"],
            "total": u["input"] + u["output"],
            "cache_read_fraction": round(u["cached"] / u["input"], 4) if u["input"] else None}


def estimate(u, rates):
    """Caller supplies per-million rates; unknown write TTL needs an explicit rate."""
    if not isinstance(rates, dict):
        raise ValueError("model rates must be an object")
    unknown_writes = u["write"] - u["write_30m"] - u["write_12h"]
    components = {"input": u["input"] - u["cached"] - u["write"],
                  "cached_input": u["cached"], "output": u["output"],
                  "cache_write": unknown_writes, "cache_write_30m": u["write_30m"],
                  "cache_write_12h": u["write_12h"]}
    total = 0.0
    for key, count in components.items():
        if not count:
            continue
        rate = rates.get(key)
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate < 0:
            raise ValueError(f"missing/invalid rate: {key}")
        total += count * rate / 1_000_000
    return round(total, 8)
