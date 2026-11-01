"""Text that repeats another file must match it.

1. `config/cloud-setup.sh` holds a copy of `config/CLAUDE.md` in a heredoc, plus one
   cloud-only line. An edit to one and not the other used to leave cloud sessions on old rules.
2. Every path README "Contents" names exists, so a rename cannot leave a dead entry.
3. The README table repeats the deny list and the two numeric keys of
   `config/user-settings.json`.
4. Every command README "Tests" lists is a step in `.github/workflows/ci.yml`.
5. README "Security model of the hook" repeats the hook timeout and three limits of
   `hooks/context_check.py`.
6. The fixed load in README "Biggest costs still left" cites a line of
   `research/measurements.jsonl` and states that line's number.

Each check is a function over text, and a test feeds it a drifted copy to show it catches the
drift, so a parser that silently finds nothing cannot pass.
"""
import json
import re

from conftest import ROOT, load_module

CLOUD_LINE = ("- In a cloud session the machine is discarded when the session ends: commit and "
              "push the progress file before offering the fresh session.\n")
PATH_SUFFIXES = (".py", ".md", ".json", ".sh", ".txt", ".yml", ".jsonl", "/")


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8").replace("\r\n", "\n")


def section(markdown, heading):
    """The body under `## heading`, up to the next `## ` heading or the end."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", markdown, re.M | re.S)
    assert match, f"README has no '## {heading}' section"
    return match.group(1)


def heredoc_body(script):
    match = re.search(r"<<'EOF'\n(.*?)^EOF$", script, re.M | re.S)
    assert match, "no <<'EOF' heredoc in the script"
    return match.group(1)


def cloud_drift(script, rules):
    """None when the heredoc is the rules plus the cloud-only line, else what differs."""
    body = heredoc_body(script)
    expected = rules + CLOUD_LINE
    if body == expected:
        return None
    return f"heredoc differs from config/CLAUDE.md + cloud line:\n{body!r}\n!=\n{expected!r}"


def contents_paths(markdown):
    """Paths in README "Contents": a backticked token with no space that ends in a known
    suffix. A name without a slash is resolved inside the folder the bullet starts with."""
    paths = []
    for line in section(markdown, "Contents").splitlines():
        tokens = re.findall(r"`([^`\s]+)`", line)
        if not line.startswith("- ") or not tokens:
            continue
        folder = tokens[0] if tokens[0].endswith("/") else ""
        for token in tokens:
            if not token.endswith(PATH_SUFFIXES):
                continue
            paths.append(token if "/" in token.rstrip("/") or token == folder else folder + token)
    return paths


def missing_contents_paths(markdown, root):
    return [path for path in contents_paths(markdown) if not (root / path).exists()]


def readme_settings(markdown):
    """The deny list and the two numeric keys as the README table states them."""
    table = section(markdown, "What is applied to every session")
    deny = re.search(r"Never-used tools dropped: ([^(]+?) \(", table)
    keys = dict(re.findall(r"`(autoCompactWindow|skillListingBudgetFraction): ([\d.]+)`", table))
    return {
        "deny": [name.strip() for name in deny.group(1).split(",")] if deny else None,
        "autoCompactWindow": int(keys["autoCompactWindow"]) if "autoCompactWindow" in keys else None,
        "skillListingBudgetFraction": (float(keys["skillListingBudgetFraction"])
                                       if "skillListingBudgetFraction" in keys else None),
    }


def settings_drift(markdown, settings):
    stated = readme_settings(markdown)
    actual = {
        "deny": settings["permissions"]["deny"],
        "autoCompactWindow": settings["autoCompactWindow"],
        "skillListingBudgetFraction": settings["skillListingBudgetFraction"],
    }
    return {key: (stated[key], actual[key]) for key in actual if stated[key] != actual[key]}


def readme_test_commands(markdown):
    block = re.search(r"```bash\n(.*?)```", section(markdown, "Tests"), re.S)
    assert block, "README 'Tests' has no bash block"
    return [line.strip() for line in block.group(1).splitlines() if line.strip()]


def commands_not_in_ci(markdown, workflow):
    steps = {line.strip()[len("run: "):].strip() if line.strip().startswith("run: ")
             else line.strip() for line in workflow.splitlines()}
    return [command for command in readme_test_commands(markdown) if command not in steps]


def test_cloud_setup_holds_the_rules_and_the_cloud_line():
    assert cloud_drift(read("config/cloud-setup.sh"), read("config/CLAUDE.md")) is None


def test_cloud_drift_is_caught():
    rules = read("config/CLAUDE.md")
    script = read("config/cloud-setup.sh")
    assert cloud_drift(script, rules + "- A new rule only the template has.\n")
    assert cloud_drift(script.replace(CLOUD_LINE, ""), rules)


def test_readme_contents_paths_exist():
    readme = read("README.md")
    assert len(contents_paths(readme)) >= 10
    assert missing_contents_paths(readme, ROOT) == []


def test_a_renamed_contents_path_is_caught():
    readme = read("README.md").replace("`verify-tokens.py`", "`verify_tokens.py`")
    assert missing_contents_paths(readme, ROOT) == ["config/verify_tokens.py"]


def test_readme_settings_match_user_settings():
    settings = json.loads(read("config/user-settings.json"))
    assert settings_drift(read("README.md"), settings) == {}


def test_settings_drift_is_caught():
    settings = json.loads(read("config/user-settings.json"))
    settings["permissions"]["deny"].append("Monitor")
    settings["autoCompactWindow"] = 200000
    assert set(settings_drift(read("README.md"), settings)) == {"deny", "autoCompactWindow"}
    readme = read("README.md").replace("`skillListingBudgetFraction: 0.005`", "a small budget")
    assert "skillListingBudgetFraction" in settings_drift(readme, json.loads(read("config/user-settings.json")))


def test_readme_test_commands_run_in_ci():
    readme = read("README.md")
    assert len(readme_test_commands(readme)) >= 2
    assert commands_not_in_ci(readme, read(".github/workflows/ci.yml")) == []


def test_a_command_ci_does_not_run_is_caught():
    workflow = read(".github/workflows/ci.yml").replace("python -I keyline/tests/run_tests.py", "true")
    assert commands_not_in_ci(read("README.md"), workflow) == ["python -I keyline/tests/run_tests.py"]


def security_drift(markdown, settings_files, hook):
    """What README "Security model of the hook" states that the sources do not."""
    match = re.search(r"^### Security model of the hook\n(.*?)(?=^#{2,3} |\Z)", markdown, re.M | re.S)
    assert match, "README has no '### Security model of the hook' section"
    text = match.group(1)
    stated = {
        "timeout": re.search(r"has a (\d+) s timeout", text),
        "tail_mb": re.search(r"last (\d+) MB of the transcript", text),
        "state_days": re.search(r"removed after (\d+) days", text),
        "log_mb": re.search(r"capped at about (\d+) MB", text),
    }
    stated = {key: int(match.group(1)) if match else None for key, match in stated.items()}
    timeouts = {entry["timeout"] for settings in settings_files
                for group in settings["hooks"]["UserPromptSubmit"] for entry in group["hooks"]}
    actual = {
        "timeout": timeouts.pop() if len(timeouts) == 1 else sorted(timeouts),
        "tail_mb": hook.TAIL_BYTES // (1024 * 1024),
        "state_days": hook.STATE_MAX_AGE // (24 * 3600),
        "log_mb": hook.LOG_MAX_BYTES // (1024 * 1024),
    }
    return {key: (stated[key], actual[key]) for key in actual if stated[key] != actual[key]}


def hook_sources():
    settings = [json.loads(read(name)) for name in
                ("config/user-settings.json", "config/repo-settings.json", ".claude/settings.json")]
    return settings, load_module("context_check_docs", "hooks/context_check.py")


def test_security_model_matches_the_hook():
    settings, hook = hook_sources()
    assert security_drift(read("README.md"), settings, hook) == {}


def test_security_model_drift_is_caught():
    settings, hook = hook_sources()
    settings[1]["hooks"]["UserPromptSubmit"][0]["hooks"][0]["timeout"] = 30
    readme = read("README.md").replace("removed after 30 days", "removed after a while")
    assert set(security_drift(readme, settings, hook)) == {"timeout", "state_days"}


def fixed_load_drift(markdown, ledger_text):
    """None when the bold fixed-load number cites a ledger line holding the same number."""
    text = section(markdown, "Biggest costs still left")
    match = re.search(r"Fixed load of a new session is \*\*([\d,]+) tokens\*\*.*?"
                      r"`research/measurements\.jsonl` line (\d+)", text)
    if not match:
        return "the fixed-load line cites no line of research/measurements.jsonl"
    stated, number = int(match.group(1).replace(",", "")), int(match.group(2))
    rows = ledger_text.split("\n")   # newlines only, as ledger.py and editors count lines
    if not 1 <= number <= len(rows):
        return f"research/measurements.jsonl has no line {number}"
    actual = json.loads(rows[number - 1]).get("fixed_tokens")
    return None if actual == stated else f"README says {stated}, line {number} says {actual}"


def test_readme_fixed_load_cites_the_ledger():
    assert fixed_load_drift(read("README.md"), read("research/measurements.jsonl")) is None


def test_fixed_load_drift_is_caught():
    readme, ledger = read("README.md"), read("research/measurements.jsonl")
    assert fixed_load_drift(readme.replace("**71,396 tokens**", "**70,000 tokens**"), ledger)
    assert fixed_load_drift(readme, ledger.replace("71396", "70000"))
    assert fixed_load_drift(readme.replace("measurements.jsonl` line 1", "measurements.jsonl` line 9"), ledger)


def test_fixed_load_line_numbers_count_newlines_only():
    # Review 1, finding 4: a U+2028 kept raw in a note is not a line break for the ledger, an
    # editor or `sed -n N p`, so it must not shift the line the README cites.
    readme = read("README.md").replace("measurements.jsonl` line 1", "measurements.jsonl` line 2")
    ledger = '{"date": "2026-10-01", "tools": 3, "note": "a\u2028b"}\n' + read("research/measurements.jsonl")
    assert fixed_load_drift(readme, ledger) is None
