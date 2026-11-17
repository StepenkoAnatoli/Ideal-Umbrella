# GPT validation

The adapter has its own tests and does not reuse Claude token or price assumptions.
Run from `gpt/`:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q umbrella.py gpt_umbrella
```

The suite covers usage subsets, response deduplication, legacy counters, malformed input,
privacy of reports, reminder thresholds, compaction, installer rollback, interrupted
transactions, user-edit preservation, and isolated installed execution. Windows-specific
tests run the installed hook through both cmd.exe and PowerShell with paths containing spaces.

From the repository root, `python -m pytest -q tests/test_gpt_entrypoint.py` checks the
separate entry point, platform distinction, deeply nested JSON, and Unicode output paths.
The isolation and README checks failed before integration. The Unicode output check
failed before the CLI configured UTF-8 output; it had returned an encoding error after
successfully writing a report with a non-ANSI filename.

Local validation uses Windows and Python 3.14. The existing root CI also runs GPT's suite
through `tests/test_gpt_entrypoint.py` on Python 3.12+ jobs, including Windows and Ubuntu;
the Python 3.10 job skips GPT execution. Consult the actual run rather than assuming it passed.
Only synthetic fixtures are committed. Local session reports, usage totals, machine paths,
and runtime installation state are excluded.

These checks do not establish savings, task quality, account-wide usage, subscription
quota changes, or support for remote Codex and ordinary ChatGPT chats. A hook must still
be reviewed and trusted on each installation. File verification does not establish trust.

For an effectiveness measurement, compare matching tasks with the same model, effort,
repository state, tool access, and acceptance checks. Record total usage, correctness,
completion time, and cache conditions together. See the [research](gpt-research.md).

## Local integration results — 2026-11-17

- GPT unittest suite: 46 passed; compile check passed.
- Root GPT integration and documentation checks passed; the CI bridge additionally runs
  the complete GPT suite from root pytest.
- Repository pyflakes: clean; keyline standalone suite: 36/36 passed; all tracked JSON valid.
- Full root pytest on Windows/Python 3.14: 2,119 passed, 84 skipped, one timing failure,
  and 20 setup errors. These errors also reproduce on untouched upstream commit
  `415f786cf74828c1a039b0e75d0389321bf2eeed`: long parametrized keyline test names exceed
  Windows' environment-variable limit, and the existing timing test exceeds its limit
  on this machine. No Claude/keyline implementation or existing test was changed.

Baseline reproduction from an untouched upstream checkout:

```powershell
python -m pytest -q tests/test_keyline_check.py::test_extraction_and_hedges_are_linear_on_100_kb tests/test_keyline_check.py::test_many_tokens_sharing_a_run_with_few_lengths_are_looked_up_in_one_walk --tb=short
```

The root workflow uses Python 3.12 on Windows and Python 3.12, 3.13, and 3.14 on Ubuntu
for GPT execution. The baseline result is a local test limitation, not a claim that
the complete repository suite passed locally. Full logs are retained outside the repository.

## Beginner guide and activation check

The first published revision passed the complete GitHub Actions matrix on Ubuntu and
Windows: [run 43978521885](https://github.com/StepenkoAnatoli/Ideal-Umbrella/actions/runs/43978521885).
For the onboarding update, all 15 documentation checks passed. A fresh temporary Codex
home also passed the documented dry-run, install, verify, local usage report, installed-hook
reminder with a synthetic transcript, and uninstall flow. Relative links and heading
anchors were checked; the generated preview was visually reviewed for readable, accurate text.

The existing local installation was updated to v0.1.2 and verified. Its parsed configuration
values and hook definitions remained unchanged. An earlier edited skills block contained
Codex's hook-trust settings; those settings were preserved, and only the obsolete ownership
comments were removed after backing up the original file. This local maintenance is not an
automatic upgrade feature or evidence that a fresh user's hooks are already trusted.
