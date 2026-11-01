#!/bin/bash
# Ideal-Umbrella rules for Claude Code cloud sessions.
# Paste into the cloud environment's setup script (claude.ai/code -> environment settings).
# Cloud sessions don't read your local ~/.claude/CLAUDE.md, so this writes it inside the session.
mkdir -p ~/.claude
cat > ~/.claude/CLAUDE.md <<'EOF'
# Side sessions and subagents
- Write full details to a file; reply with a gist of at most 5 lines plus the file's path.
- When you brief a side session or subagent, ask it for exactly that, and to update the task's resume point if it changed anything.
- Once a side session you started has finished and you have checked its result, archive it (standing request from the user, 2026-10-19). Leave it if it is still working, waiting for the user, or has an open pull request.

# Long chats and restarts
- At a step boundary, if the context is over 150k tokens: write a resume point (state, decisions and why, open items, file paths) to the task's progress file, then offer a fresh session whose brief points to that file.
- At the end of each task that changed something, update the task's resume point (replace it, don't append), so a restart or a fresh chat loses at most the task in progress.
- Keep decisions in files, not only in the chat.
- Save what the code cannot tell the next session in notes/learnings.md when the repo has it: a choice and why under decided; an approach dropped and why under tried and ruled out; a bug's cause found after failed attempts, or the user correcting how something is done here, under watch out.
- In a cloud session the machine is discarded when the session ends: commit and push the progress file before offering the fresh session.
EOF
exit 0
