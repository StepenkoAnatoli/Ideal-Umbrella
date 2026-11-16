# GPT port checkpoint

objective: publish the GPT/Codex adaptation inside Ideal-Umbrella with clear platform boundaries
decided: gpt/ owns Codex runtime|docs|tests; root Claude installer stays separate; no GPT savings claim
changed: gpt/ v0.1.2; README.md; CHANGELOG.md; tests/test_gpt_entrypoint.py; tests/test_docs_match_source.py
checked: GPT 46 tests pass; final CI bridge|integration|docs|source rules 92 pass; pyflakes clean; keyline 36 pass; JSON 4 valid; Unicode output failed before UTF-8 fix
open: root Windows3.14 pytest has 1 timing failure|20 oversized-ID setup errors, reproduced on unchanged main; effectiveness needs matched tasks
publication: feat/gpt-codex-umbrella; draft PR targets main; details in gpt/docs/validation.md
CI: existing root workflow invokes the GPT suite through pytest on Python3.11+; no workflow-file changes
next: review the draft and Windows|Ubuntu CI before merge
