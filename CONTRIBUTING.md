# Contributing

Ideal-Umbrella is small on purpose: settings, one rule file, one hook, installers and measurement scripts. These rules come from the review rounds in `research/` and keep it that way.

## Every change
- **A failing test first.** A behaviour change or a bug fix starts with a test that fails on the old code; say in the PR that you saw it fail.
- **Fix the class, not the instance.** Name the bug class in one searchable sentence, search the whole repository for the same pattern, and list every hit with file:line and a verdict (fixed, or why not). `research/review-findings-main-*.md` show the format.
- **Check the three classes that keep coming back:**
  - *neighbour of a previous fix*: a guard or handler that covers one twin or one path but not the other (install and uninstall, `install.py` and `add_to_repo.py`, Windows and POSIX);
  - *halfway state*: a write that fails part way and leaves something the install record does not describe;
  - *absent is not empty*: a missing, meaningful key defaulted to its empty value.
- **Stdlib only** in everything that ships (`config/`, `hooks/`, `scripts/`). `tiktoken` is for `keyline/` only; `pytest` and `pyflakes` are for development only.
- **Run a script that reads user files with `python -I`** and treat those files as untrusted: a transcript, note or settings file that is not UTF-8, not the expected shape or nested too deep for `json` is a one-line message, never a traceback. `tests/test_source_rules.py` checks the rules it can see in the source.
- **Windows and Ubuntu both pass.** Paths, encodings and symlinks differ; CI runs both.
- **User files are written whole or not at all** (temp file beside it, then rename), backed up before they are replaced, and recorded in the install record before the next write, as `config/install.py` does.
- **Docs move with the code.** Update `README.md` and `CHANGELOG.md` in the same PR. Text that copies another file is tested against it (`tests/test_docs_match_source.py`); extend that test when you add a copy.
- **Every number in the README names the script and command that produced it**, and a measurement worth tracking gets a line in `research/measurements.jsonl` (`scripts/ledger.py`).
- **Resume points** live in `research/*-progress.md` (replace the resume point, don't append). Notes in `notes/` or `plans/`, the folders the keyline hook watches, follow the keyline format (`keyline/README.md`).

## Before you push
Run every command in README "Tests" (pyflakes, pytest, the keyline suite, the JSON checks). CI runs the same list.

## Pull requests
Use the template: what changed, which class it fixes, the commands you actually ran, and which docs you touched. Merges use a merge commit.
