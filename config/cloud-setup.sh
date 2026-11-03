#!/bin/bash
# Ideal-Umbrella rules for Claude Code cloud sessions.
# Paste into the cloud environment's setup script (claude.ai/code -> environment settings).
# Cloud sessions don't read your local ~/.claude/CLAUDE.md, so this writes the rules inside the
# session: as a marked section of CLAUDE.md in the folder Claude Code reads (CLAUDE_CONFIG_DIR,
# else ~/.claude), the markers config/install.py uses. Text already in the file (from the image
# or an earlier step) stays; a rerun replaces the section. It never fails the setup.
dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
file="$dir/CLAUDE.md"
begin='<!-- Ideal-Umbrella rules: begin -->'
end='<!-- Ideal-Umbrella rules: end -->'
rules=$(cat <<'EOF'
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
)
mkdir -p "$dir" || exit 0
# The new file is built whole beside the real file (a linked CLAUDE.md stays a link) and moved
# over it, so a write cut short (a full disk) leaves the old file as it was, never half a section.
real=$(readlink -f -- "$file") || real="$file"
tmp="$real.ideal-umbrella-$$"
fail() { rm -f "$tmp"; echo "Ideal-Umbrella: $file not written ($1); left as it was" >&2; exit 0; }
if [ -f "$file" ]; then
  b=$(grep -cxF -- "$begin" "$file")
  e=$(grep -cxF -- "$end" "$file")
  if [ "$b" != "$e" ] || [ "$b" -gt 1 ]; then
    echo "Ideal-Umbrella: $file has broken or repeated rule markers; left as it is" >&2
    exit 0
  fi
  # Drop the earlier section. Blank lines are held back until the next text line, so the blank
  # lines around the old section merge into one gap and none are left at the end of the file.
  awk -v b="$begin" -v e="$end" '
    $0 == b { skip = 1; keep = blank; blank = 0; merge = 1; next }
    skip { if ($0 == e) skip = 0; next }
    /^[ \t\r]*$/ { blank++; next }
    { n = blank; if (merge && keep > n) n = keep; merge = 0
      for (; n > 0; n--) print ""; blank = 0; print }
  ' "$file" > "$tmp" || fail "cannot write $tmp"
  chmod --reference="$real" "$tmp" 2>/dev/null
else
  : > "$tmp" || fail "cannot write $tmp"
fi
{ if [ -s "$tmp" ]; then printf '\n'; fi; printf '%s\n%s\n%s\n' "$begin" "$rules" "$end"; } >> "$tmp" \
  || fail "cannot write $tmp"
mv -f -- "$tmp" "$real" || fail "cannot replace $real"
exit 0
