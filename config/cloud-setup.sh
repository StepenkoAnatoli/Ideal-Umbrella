#!/bin/bash
# Ideal-Umbrella rules for Claude Code cloud sessions.
# Paste into the cloud environment's setup script (claude.ai/code -> environment settings).
# Cloud sessions don't read your local ~/.claude/CLAUDE.md, so this writes the rules inside the
# session: as a marked section of CLAUDE.md in the folder Claude Code reads (CLAUDE_CONFIG_DIR,
# else ~/.claude), the markers config/install.py uses. Text already in the file (from the image
# or an earlier step) stays; a rerun replaces the section. It never fails the setup: it runs in
# a subshell, so its own exits, traps and names end with it, and the setup script around it goes
# on (under set -e too). Noclobber (set -C) from that script would block its writes, so it is off.
(
set +C
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

# Effort
- After 3 failed attempts at one fix, stop and tell me what you tried and the cause you suspect.
- Size the process to the change: a small, clear change goes straight to the build, with no plan or extra review.
- In a cloud session the machine is discarded when the session ends: commit and push the progress file before offering the fresh session.
EOF
)
mkdir -p "$dir" || exit 0
if [ -e "$file" ] && [ ! -f "$file" ]; then
  echo "Ideal-Umbrella: $file is not a file (a folder?); left as it is" >&2
  exit 0
fi
# The new file is built whole beside the real file (a linked CLAUDE.md stays a link) and moved
# over it, so a write cut short (a full disk) leaves the old file as it was, never half a section.
# mktemp makes the temp file new (never one already there) at 0600, so it is never more open than
# the file it copies; it gets that file's mode only once it is whole. In a folder the session may
# not write it goes to TMPDIR instead. Every exit removes it, except the one that names it.
# A link to a file not there yet is written at its target, if that folder exists (busybox
# readlink -f fails on such a link, so it is followed one step by hand).
real=$(readlink -f -- "$file" 2>/dev/null) || {
  real=
  if [ -L "$file" ]; then
    t=$(readlink -- "$file") && case $t in /*) ;; *) t="$dir/$t" ;; esac
    if [ -n "$t" ] && [ ! -e "$t" ] && [ ! -L "$t" ] && p=$(readlink -f -- "${t%/*}" 2>/dev/null) && [ -d "$p" ]; then
      real="$p/${t##*/}"
    fi
  else
    real="$file"
  fi
  if [ -z "$real" ]; then
    echo "Ideal-Umbrella: $file is a link that leads nowhere (a missing folder, or a loop); left as it is" >&2
    exit 0
  fi
}
beside=1
tmp=$(mktemp -- "$real.ideal-umbrella-XXXXXX" 2>/dev/null) || {
  beside=0
  tmp=$(mktemp) || { echo "Ideal-Umbrella: $file not written (no temp file); left as it was" >&2; exit 0; }
}
trap 'rm -f -- "$tmp"' EXIT
fail() { echo "Ideal-Umbrella: $file not written ($1); left as it was" >&2; exit 0; }
if [ -f "$file" ] && [ ! -r "$file" ]; then
  echo "Ideal-Umbrella: $file not written (cannot read it); left as it was" >&2
  exit 0
fi
if [ -f "$file" ]; then
  # The markers are found as config/install.py finds them: whole lines, trailing whitespace (a
  # CRLF line end) ignored, none inside a closed ``` or ~~~ code fence (an example the user
  # wrote); one begin line followed by one end line, or none. Pass 1 finds them, pass 2 copies
  # the file without the old section. Blank lines are copied as written; those around the old
  # section merge into one gap, and the file's text is followed by one blank line, or by the
  # blank lines it already ends with, before the new section.
  lf=0; [ "$(tail -c 1 -- "$file" | od -An -c | tr -d ' ')" = '\n' ] && lf=1
  LC_ALL=C awk -v b="$begin" -v e="$end" -v lf="$lf" '
    function bare(s) { sub(/[ \t\r\f\v]+$/, "", s); return s }
    function lead() { if (pb) printf "\357\273\277"; pb = 0 }
    function blanks(   i) { if (nb) lead(); for (i = 1; i <= nb; i++) print hb[i]; nb = 0 }
    function take(   i) { if (merge && nk > nb) { for (i = 1; i <= nk; i++) hb[i] = kb[i]; nb = nk }; merge = 0 }
    NR == FNR {
      line[FNR] = $0; n = FNR; s = $0
      if (FNR == 1 && substr(s, 1, 3) == "\357\273\277") s = substr(s, 4)
      if (match(s, /^ ? ? ?(```+|~~~+)/)) {
        f++; fl[f] = FNR; fs = substr(s, RSTART, RLENGTH); sub(/^ +/, "", fs)
        fc[f] = substr(fs, 1, 1); flen[f] = length(fs); info = substr(s, RSTART + RLENGTH)
        fclose_[f] = (info ~ /^[ \t\r]*$/); fbad[f] = (fc[f] == "`" && index(info, "`"))
      }
      next
    }
    FNR == 1 { decide()
               # The BOM is held and written before whatever comes first; a file that is only a
               # BOM (no line end) is an empty file with a BOM, so the section follows it at once.
               if (substr($0, 1, 3) == "\357\273\277") { $0 = substr($0, 4); pb = 1
                 if (n == 1 && $0 == "" && !lf) next } }
    FNR == sb { take(); merge = 1; for (i = 1; i <= nb; i++) kb[i] = hb[i]; nk = nb; nb = 0
                lead(); next }
    FNR > sb && FNR <= se { next }
    /^[ \t\r]*$/ { hb[++nb] = $0; next }
    { take(); blanks(); lead(); print; out = 1 }
    END {
      if (NR == FNR) decide()
      take(); if (nb) blanks(); else if (out) print ""
      lead()
    }
    function decide(   i, j, c, L, x, k, nbeg, nend) {
      # Lines inside closed fences (install.py _fenced): an opener with no closer later is text.
      # lg[c, i]: the longest closing fence of character c at fence i or later, so an opener
      # with no closer is skipped at once (linear, as in _fenced).
      lg["`", f + 1] = lg["~", f + 1] = 0
      for (i = f; i >= 1; i--) {
        lg["`", i] = lg["`", i + 1]; lg["~", i] = lg["~", i + 1]
        if (fclose_[i] && flen[i] > lg[fc[i], i]) lg[fc[i], i] = flen[i]
      }
      for (i = 1; i <= f; ) {
        c = fc[i]; L = flen[i]; j = 0
        if (!fbad[i] && lg[c, i + 1] >= L) for (k = i + 1; k <= f; k++) if (fc[k] == c && flen[k] >= L && fclose_[k]) { j = k; break }
        if (!j) { i++; continue }
        for (x = fl[i]; x <= fl[j]; x++) fenced[x] = 1
        i = j + 1
      }
      sb = se = 0; nbeg = nend = 0
      for (i = 1; i <= n; i++) {
        x = bare(line[i]); if (i == 1 && substr(x, 1, 3) == "\357\273\277") x = substr(x, 4)
        if (fenced[i]) continue
        if (x == b) { nbeg++; sb = i }
        else if (x == e) { nend++; se = i }
      }
      if (nbeg != nend || nbeg > 1 || se < sb) exit 3
      if (!nbeg) sb = se = n + 1
    }
  ' "$file" "$file" > "$tmp"
  case $? in
    0) ;;
    3) echo "Ideal-Umbrella: $file has broken or repeated rule markers; left as it is" >&2; exit 0 ;;
    *) fail "cannot write $tmp" ;;
  esac
fi
printf '%s\n%s\n%s\n' "$begin" "$rules" "$end" >> "$tmp" || fail "cannot write $tmp"
if [ -f "$file" ]; then
  # stat -c, not GNU chmod --reference, so busybox keeps the mode too; should stat fail, the
  # file stays at mktemp's 0600, never more open than before.
  mode=$(stat -c %a -- "$real" 2>/dev/null) && chmod "$mode" "$tmp" 2>/dev/null
else
  chmod "$(printf '%o' $((0666 & ~0$(umask))))" "$tmp" 2>/dev/null
fi
# A rename gives the file the runner's owner and splits a hard link from its other names, so a
# file owned by another user or group, or with another name, is written in place instead.
links=$(stat -c %h -- "$real" 2>/dev/null) || links=1
if [ "$beside" = 1 ] && { [ ! -e "$real" ] || { [ -O "$real" ] && [ -G "$real" ] && [ "$links" = 1 ]; }; } \
   && mv -f -- "$tmp" "$real" 2>/dev/null; then exit 0; fi
# No rename (a bind-mounted CLAUDE.md, a folder the session may not write, an owner or a hard
# link to keep): write it in place, as such a file allows. A file that cannot even be opened for
# writing is untouched; should the write itself stop short, the whole new text stays in the temp
# file.
{ : >> "$real"; } 2>/dev/null || fail "cannot write $real"
if cat -- "$tmp" > "$real"; then exit 0; fi
trap - EXIT
echo "Ideal-Umbrella: $file may be cut short; the whole text is in $tmp" >&2
exit 0
) || true
