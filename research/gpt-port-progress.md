# GPT port checkpoint

objective: publish GPT/Codex adaptation with beginner onboarding and preview; activate the local installation
decided: gpt/ owns Codex runtime|docs|tests; root Claude installer stays separate; no GPT savings claim
changed: gpt/ v0.1.2; beginner README; docs/reference.md; assets/preview; root README|CHANGELOG; integration|docs tests
checked: first revision all GitHub CI jobs passed; GPT46|bridge and rules92|keyline36 pass; onboarding docs15 and clean-home install/report/hook/uninstall flow pass; preview and links checked
open: root Windows3.14 pytest has 1 timing failure|20 oversized-ID setup errors, reproduced on unchanged main; effectiveness needs matched tasks
publication: feat/gpt-codex-umbrella; PR#41 targets main; beginner guide and preview included
local: runtime updated to v0.1.2; verification passes; all parsed configuration and hook definitions preserved; backups retained outside repo
CI: existing root workflow invokes the GPT suite through pytest on Python3.11+; no workflow-file changes
next: review PR#41 and latest CI before merge; follow-up effectiveness benchmark remains separate
