# GPT integration: output encoding review

Class: an isolated Python entry point prints Unicode paths through a Windows ANSI stream,
then reports failure after it has already written the requested output file.

Reproduction: `tests/test_gpt_entrypoint.py::test_output_path_prints_in_utf8_under_isolation`
forced cp1252 output and used an umbrella symbol in the report filename. Observed failure
before the fix; passes after `gpt/gpt_umbrella/cli.py` configures both output streams.

Search: `rg -n -l 'print\(' --glob '*.py' --glob '!tests/**' --glob '!**/tests/**' config hooks scripts keyline gpt`.
The following runtime source hits were checked; line references identify the first print.
Test-fixture print calls are not shipped entry points. Existing source-rule tests enforce
the original runtime's UTF-8 setup. GPT's entry point has its own isolated execution test.

| Source hit | Verdict |
| --- | --- |
| `config/add_to_repo.py:587` | UTF-8 setup at 574; unaffected. |
| `config/install.py:84` | UTF-8 setup in main at 1394; unaffected. |
| `config/uninstall.py:700` | UTF-8 setup at 673; unaffected. |
| `config/verify-tokens.py:65` | UTF-8 setup in main at 83; unaffected. |
| `hooks/context_check.py:127` | UTF-8 setup in main at 367; unaffected. |
| `scripts/ledger.py:191` | UTF-8 setup at 180; unaffected. |
| `scripts/lint_validate.py:53` | UTF-8 setup at 51; unaffected. |
| `scripts/plugin_cost.py:124` | UTF-8 setup at 122; unaffected. |
| `scripts/skill_bill.py:75` | UTF-8 setup in main at 174; unaffected. |
| `scripts/tokentest.py:33` | UTF-8 setup at 5; unaffected. |
| `scripts/toolresult_share.py:97` | UTF-8 setup at 9; unaffected. |
| `scripts/top_waste.py:107` | UTF-8 setup in main at 127; unaffected. |
| `scripts/ttl_whatif.py:140` | UTF-8 setup in main at 157; unaffected. |
| `scripts/unused_tools.py:100` | UTF-8 setup at 96; unaffected. |
| `scripts/usage_breakdown.py:153` | UTF-8 setup in main at 207; unaffected. |
| `scripts/usertext_split.py:41` | UTF-8 setup at 9; unaffected. |
| `scripts/usertext_top.py:40` | UTF-8 setup at 9; unaffected. |
| `keyline/keyline_check.py:1342` | UTF-8 setup at 1337; unaffected. |
| `keyline/keyline_hook.py:58` | UTF-8 setup in main at 179; unaffected. |
| `keyline/keyline_lint.py:278` | UTF-8 setup at 272; unaffected. |
| `keyline/measure.py:32` | UTF-8 setup in main at 75; unaffected. |
| `gpt/gpt_umbrella/cli.py:68` | Fixed: both streams configured at 48; regression test. |
| `gpt/gpt_umbrella/monitor.py:102` | Called through CLI setup; emits ASCII JSON and sanitized ASCII exception class names. |

Recurring classes checked: neighboring stderr now shares stdout's encoding setup; reporting
after a completed write no longer fails for non-ANSI paths; absent/empty settings behavior
remains covered by installer tests. The CLI also handles recursion failures and flattens
multiline error text into a single diagnostic.
