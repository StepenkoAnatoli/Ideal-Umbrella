"""keyline_lint.py - fail a machine-notes file on markdown furniture and invented abbreviations.

Furniture: a line starting with a bullet ('- ', '* ', '+ '), a numbered item ('1. ', '2) '),
or a header ('# ' to '###### '), or any line containing '**' or a backtick.
Abbreviations: a lowercase ASCII word that is not a single o200k_base token (with its leading
space, as it appears mid-line) AND has the shape of an invented abbreviation:
  - a numeronym (k8s, i18n, a11y), or
  - 2-5 letters with no vowel (rst, xh, mgmt, tmpl), or 4-5 letters with one vowel (alrt, srvc).
Everything else that splits into several tokens is let through, because it is almost always a real
word or a real identifier: long words and compounds (uncommitted, harmlessly, worktree), anything
containing a digit (cp1252, sha256, x2, git hashes such as b07b3b6). Single-token abbreviations
(cfg, env, prod) cost nothing and pass, and so does a plural whose stem is one token (diffs, slugs).
Common developer tool names (mcp, npx, pnpm, venv, pwsh...) are allowed by a built-in list.
Identifiers, paths and capitalised names are skipped.
The single-token word list is built once with tiktoken and cached in cache/.

Project words that are real but split into several tokens (tool names such as 'kubectl') go in a
keyline-allow.txt, one word per line; every keyline-allow.txt in the file's folder or any parent
folder is read.

Usage:
  python keyline_lint.py FILE [FILE ...]
  python keyline_lint.py --allow WORDS.txt FILE ...   extra allow file
  python keyline_lint.py --no-allow FILE ...          ignore keyline-allow.txt files and the built-in list
  python keyline_lint.py --rebuild-cache              rebuild the single-token word list
Exit: 0 clean, 1 findings, 2 usage or read error.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "cache"
WORDS_CACHE = CACHE_DIR / "o200k_single_token_words.txt"
ALLOW_NAME = "keyline-allow.txt"

FURNITURE = [
    (re.compile(r"^\s*[-*+]\s"), "bullet"),
    (re.compile(r"^\s*\d+[.)]\s"), "numbered item"),
    (re.compile(r"^\s*#{1,6}\s"), "header"),
    (re.compile(r"\*\*"), "bold '**'"),
    (re.compile(r"`"), "backtick"),
]

STRIP = "\"'()[]{}<>,;:!?."
VOWELS = set("aeiouy")
NUMERONYM = re.compile(r"[a-z]\d{1,2}[a-z]{1,2}")      # k8s, i18n, a11y, l10n
# Tool, format and product names that are real words in engineering notes but split into tokens.
BUILTIN_ALLOW = set("""
mcp npm npx pnpm pipx venv pwsh zsh fish tsc tsx mjs cjs jsx dbt n8n llm llms gpt vnc ssh scp
chdir rmdir mkdir chmod chown stdin stdout stderr docx xlsx pptx csv tsv httpx grpc
""".split())
# A chunk with any of these is an identifier, path, URL, number or expression: not checked.
IDENT_CHARS = re.compile(r"[/\\_.=@#$%&*+<>|~]")


class TiktokenMissing(ImportError):
    """tiktoken is not installed; str(error) is the install hint.

    An Exception, not SystemExit: token_count() catches it to report "not one token", and the
    entry points (main() here, keyline_hook.py) turn it into one line and an exit code.
    """


def _tiktoken():
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(CACHE_DIR / "tiktoken"))
    try:
        import tiktoken
    except ImportError:
        # The single-token word list is built once from the o200k vocabulary; a fresh clone has
        # no cache/ yet (it is gitignored), so the first run needs tiktoken.
        raise TiktokenMissing("tiktoken is not installed; run: python -m pip install -r "
                              "keyline/requirements.txt (needed once, to build keyline/cache/)") from None
    return tiktoken


def read(path):
    """Read a UTF-8 (optionally BOM-marked) text file; any other encoding is a read error."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    except UnicodeDecodeError as e:
        raise OSError(f"{path} is not UTF-8 ({e.reason} at byte {e.start}); save it as UTF-8") from None


def build_cache():
    tiktoken = _tiktoken()
    enc = tiktoken.get_encoding("o200k_base")
    words = set()
    pat = re.compile(rb"^ [a-z]+$")
    for i in range(enc.n_vocab):
        try:
            b = enc.decode_single_token_bytes(i)
        except KeyError:
            continue
        if pat.match(b):
            words.add(b[1:].decode("ascii"))
    CACHE_DIR.mkdir(exist_ok=True)
    header = (f"# lowercase ASCII words that are one o200k_base token with a leading space; "
              f"built by keyline_lint.py with tiktoken {tiktoken.__version__}; {len(words)} words\n")
    # Whole or not at all: a build cut short (disk full, a killed process) must not leave a
    # short list that the next run would trust.
    fd, tmp = tempfile.mkstemp(prefix=f".{WORDS_CACHE.name}-", dir=CACHE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(header + "\n".join(sorted(words)) + "\n")
        os.replace(tmp, WORDS_CACHE)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return words


def load_words():
    if not WORDS_CACHE.exists():
        return build_cache()
    lines = read(WORDS_CACHE).splitlines()
    words = {w.strip() for w in lines if w.strip() and not w.startswith("#")}
    # The header says how many words the build wrote; fewer means the file was cut short.
    expected = re.search(r"; (\d+) words$", lines[0]) if lines else None
    if expected is None or int(expected.group(1)) != len(words):
        return build_cache()
    return words


def load_allow(path, extra, use_files=True):
    allow = set(BUILTIN_ALLOW) if use_files else set()
    files = list(extra)
    if use_files:
        for d in [Path(path).resolve().parent, *Path(path).resolve().parents]:
            f = d / ALLOW_NAME
            if f.is_file():
                files.append(f)
    for f in files:
        for line in read(f).splitlines():
            w = line.split("#", 1)[0].strip().lower()
            if w:
                allow.add(w)
    return allow


def token_count(word):
    try:
        enc = _tiktoken().get_encoding("o200k_base")
        return len(enc.encode(" " + word))
    except Exception:
        return None


def looks_invented(part, words=frozenset()):
    """True when a multi-token lowercase word has the shape of an invented abbreviation."""
    if NUMERONYM.fullmatch(part):
        return True
    if any(c.isdigit() for c in part):
        return False                  # cp1252, sha256, x2, b07b3b6: identifiers and hashes
    if len(part) >= 6:
        return False                  # uncommitted, harmlessly, worktree: real words, compounds
    if part.endswith("s") and part[:-1] in words:
        return False                  # diffs, slugs, devs: plural of a one-token word
    vowels = sum(c in VOWELS for c in part)
    return vowels == 0 or (len(part) >= 4 and vowels == 1)


def lint_text(text, words, allow):
    """Yield (line_no, message) findings."""
    for no, line in enumerate(text.splitlines(), 1):
        for pat, what in FURNITURE:
            if pat.search(line):
                yield no, f"furniture: {what}"
        for chunk in line.split():
            chunk = chunk.strip(STRIP)
            if not chunk or IDENT_CHARS.search(chunk) or re.search(r"[A-Z]", chunk):
                continue                      # identifier, path, number, CamelCase, name
            if chunk[0].isdigit():
                continue                      # 5xx, 2nd, 30k
            for part in re.findall(r"[a-z0-9]+", chunk):
                if part[0].isdigit() or part in words or part in allow:
                    continue
                if not looks_invented(part, words):
                    continue
                n = token_count(part)
                if n == 1:
                    continue                  # one token after all: the word list is not complete
                size = f"{n} tokens" if n else "not one token"
                yield no, (f"abbreviation: '{part}' is {size} under o200k_base; spell it out, "
                           f"or add it to {ALLOW_NAME} if it is a real name")


def lint_file(path, words=None, extra_allow=(), use_allow_files=True):
    words = load_words() if words is None else words
    allow = load_allow(path, extra_allow, use_allow_files)
    return list(lint_text(read(path), words, allow))


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    extra, use_files, files = [], True, []
    it = iter(argv)
    for a in it:
        if a == "--rebuild-cache":
            try:
                print(f"{len(build_cache())} words -> {WORDS_CACHE}")
            except (TiktokenMissing, OSError) as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
            return 0
        elif a == "--allow":
            extra.append(next(it, None))
        elif a == "--no-allow":
            use_files = False
        elif a.startswith("-"):
            print(__doc__.strip(), file=sys.stderr)
            return 2
        else:
            files.append(a)
    if not files or None in extra:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        words = load_words()
    except (TiktokenMissing, OSError) as e:
        # No cache and no tiktoken, or the cache folder is in the way: one line, like a note
        # that cannot be read.
        print(f"error: {e}", file=sys.stderr)
        return 2
    bad = False
    for path in files:
        try:
            findings = lint_file(path, words, extra, use_files)
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        for no, msg in findings:
            print(f"{path}:{no}: {msg}")
        if findings:
            bad = True
        else:
            print(f"OK {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
