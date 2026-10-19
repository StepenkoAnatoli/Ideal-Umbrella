# Cloud check

## 1. ~/.claude/CLAUDE.md

````markdown
# Side sessions and subagents
- Write full details to a file; reply with a gist of at most 5 lines plus the file's path.
- When you brief a side session or subagent, ask it for exactly that, and to update the task's resume point if it changed anything.
- Once a side session you started has finished and you have checked its result, archive it (standing request from the user, 2026-10-19). Leave it if it is still working, waiting for the user, or has an open pull request.

# Long chats and restarts
- At a step boundary, if the context is over 150k tokens: write a resume point (state, decisions and why, open items, file paths) to the task's progress file, then offer a fresh session whose brief points to that file.
- At the end of each task that changed something, update the task's resume point (replace it, don't append), so a restart or a fresh chat loses at most the task in progress.
- Keep decisions in files, not only in the chat.
- In a cloud session the machine is discarded when the session ends: commit and push the progress file before offering the fresh session.
````

## 2. Environment

- CLAUDE_CODE_REMOTE: `true`
- CLAUDE_CODE_AUTO_COMPACT_WINDOW: `250000`
- `python3 --version`: `Python 3.13.16`

## 3. .claude/settings.json

```json
{
  "autoCompactWindow": 250000,
  "skillListingBudgetFraction": 0.005,
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "shell": "bash",
            "command": "[ \"$CLAUDE_CODE_REMOTE\" = true ] || exit 0; python3 -I \"$CLAUDE_PROJECT_DIR/hooks/context_check.py\"; exit 0",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```
