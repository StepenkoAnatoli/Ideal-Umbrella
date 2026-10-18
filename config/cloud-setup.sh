#!/bin/bash
# Ideal-Umbrella rules for Claude Code cloud sessions.
# Paste into the cloud environment's setup script (claude.ai/code -> environment settings).
# Cloud sessions don't read your local ~/.claude/CLAUDE.md, so this writes it inside the session.
mkdir -p ~/.claude
cat > ~/.claude/CLAUDE.md <<'EOF'
# Reports from side sessions and subagents
- Write full details to a file; reply with a gist of at most 5 lines plus the file's path.
- When you brief a side session or subagent, ask it for exactly that.

# Long chats
- At a step boundary, if the context is over 150k tokens: write a resume point (state, decisions and why, open items, file paths) to the task's progress file, then offer a fresh session whose brief points to that file.
- Keep decisions in files, not only in the chat.
- In a cloud session the machine is discarded when the session ends: commit and push the progress file before offering the fresh session.
EOF
exit 0
