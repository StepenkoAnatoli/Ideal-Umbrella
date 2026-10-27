"""Rules every script in this repository keeps, checked on the source itself.

1. `sys.exit` / `SystemExit` only in `main()` or at module level. A helper that exits cannot
   be caught by a caller's `except Exception` (SystemExit is a BaseException), so the install
   hint of `keyline_lint._tiktoken()` once stopped the whole lint instead of one abbreviation
   size. Helpers raise an Exception; the entry point turns it into a message and an exit code.
2. A text read (`open()` in text mode, `Path.read_text()`) either passes `errors=` or runs
   under a `try` that handles `UnicodeDecodeError` (or `ValueError` / `Exception`, which
   include it). A note, allow file, settings file or transcript that is not UTF-8 is a one-line
   error, never a traceback.
3. A script that prints to stdout sets `sys.stdout.reconfigure(encoding="utf-8")` first. The
   scripts run with -I, which ignores PYTHONUTF8 and PYTHONIOENCODING, so on Windows stdout is
   the ANSI code page: a user text, path, tool name or plugin name outside it (or the U+FFFD a
   replaced byte becomes) used to end the script with UnicodeEncodeError. It also passes
   `errors="backslashreplace"`: a Linux path that is not UTF-8 holds lone surrogates, which no
   encoding prints, and `--verify-only` ended in a traceback on one (review 3 of the graphify
   branch, finding 4).
4. A function that calls `glob.glob()` or `glob.iglob()` also calls `glob.escape()`. A user
   folder with `[`, `*` or `?` in its name (`proj[1]`) used to make `usage_breakdown.py` find
   no transcript at all. The check sees attribute calls (`glob.glob`, `glob.escape`) inside
   one function; `from glob import glob`, a module-level call or `Path.glob` are not covered.
5. A test that starts a script of this repository (`[sys.executable, flags..., script]` in
   `tests/` and `keyline/tests/`) passes `-I` among the leading flags, so the suite runs the
   scripts the way the docs say to run them: `-I` ignores `PYTHON*` variables and the script
   folder on `sys.path`. A module run (`-m`) is not a script of this repository and is not
   checked; `-c code` is. `tests/test_utf8_output.py` is the exception: it sets
   `PYTHONIOENCODING` on purpose, which `-I` would discard.
6. A `json.load()` / `json.loads()` call runs under a `try` that handles `RecursionError` (or
   `Exception` / `BaseException`). A line or file nested a few thousand levels deep (a hand
   edit, a damaged file) raises RecursionError, not ValueError, so `except ValueError` let
   `scripts/ledger.py` end with a traceback (review 1 of the graphify branch, finding 5). The
   hook's `run()` reads stdin outside a `try` on purpose: its `main()` catches every Exception.
7. In `config/`, a function that calls `json.load()` / `json.loads()` also calls
   `_check_json()`. The installers write back what they read; a file nested deeper than
   `json.dumps(indent=2)` can write, or holding a lone surrogate UTF-8 cannot encode, made the
   write fail after the hook and CLAUDE.md were already written (review 2 of the graphify
   branch, findings 6 and 7). Checking right after the read stops the run before any write.
"""
import ast

import pytest

from conftest import ROOT

FOLDERS = ["config", "hooks", "keyline", "scripts"]
TEST_FOLDERS = ["tests", "keyline/tests"]
RUNS_WITHOUT_ISOLATION = {"tests/test_utf8_output.py"}
DECODE_HANDLERS = {"UnicodeDecodeError", "ValueError", "Exception", "BaseException"}
DEPTH_HANDLERS = {"RecursionError", "Exception", "BaseException"}
JSON_READS_CAUGHT_BY_CALLER = {("hooks/context_check.py", "run")}


def sources():
    for folder in FOLDERS:
        for path in sorted((ROOT / folder).glob("*.py")):
            yield path, ast.parse(path.read_text(encoding="utf-8"), str(path))


def _name(node):
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _handles(handler, handled):
    types = handler.type
    if types is None:
        return True
    names = [_name(e) for e in types.elts] if isinstance(types, ast.Tuple) else [_name(types)]
    return any(n in handled for n in names)


def _walk(node, in_function=None, guarded=False, handled=DECODE_HANDLERS):
    """Yield (node, enclosing function name, under a try handling one of `handled`) for every node."""
    yield node, in_function, guarded
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        in_function = node.name
    if isinstance(node, ast.Try):
        body_guarded = guarded or any(_handles(h, handled) for h in node.handlers)
        for child in node.body:
            yield from _walk(child, in_function, body_guarded, handled)
        for child in [*node.handlers, *node.orelse, *node.finalbody]:
            yield from _walk(child, in_function, guarded, handled)
        return
    for child in ast.iter_child_nodes(node):
        yield from _walk(child, in_function, guarded, handled)


def _is_exit(node):
    if isinstance(node, ast.Call) and _name(node.func) == "exit" and isinstance(node.func, ast.Attribute):
        return _name(node.func.value) == "sys"
    if isinstance(node, ast.Raise) and node.exc is not None:
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        return _name(exc) == "SystemExit"
    return False


def _is_text_read(node):
    if not isinstance(node, ast.Call):
        return False
    keywords = {k.arg for k in node.keywords}
    if "errors" in keywords:
        return False
    if isinstance(node.func, ast.Attribute) and node.func.attr == "read_text":
        return True
    if isinstance(node.func, ast.Name) and node.func.id == "open":
        mode = node.args[1] if len(node.args) > 1 else next(
            (k.value for k in node.keywords if k.arg == "mode"), None)
        # Binary and write modes do not decode anything.
        return not (isinstance(mode, ast.Constant) and set("bwax") & set(str(mode.value)))
    return False


def _prints_to_stdout(node):
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"):
        return False
    target = next((k.value for k in node.keywords if k.arg == "file"), None)
    return target is None or (isinstance(target, ast.Attribute) and target.attr == "stdout")


def _sets_utf8_stdout(node):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "reconfigure"
            and any(k.arg == "encoding" and isinstance(k.value, ast.Constant) and k.value.value == "utf-8"
                    for k in node.keywords)
            and any(k.arg == "errors" and isinstance(k.value, ast.Constant) and k.value.value == "backslashreplace"
                    for k in node.keywords))


def test_only_main_exits():
    bad = []
    for path, tree in sources():
        for node, function, _ in _walk(tree):
            if _is_exit(node) and function not in (None, "main"):
                bad.append(f"{path.relative_to(ROOT)}:{node.lineno} in {function}()")
    assert not bad, "sys.exit/SystemExit outside main():\n" + "\n".join(bad)


def test_text_reads_handle_a_decode_error():
    bad = []
    for path, tree in sources():
        for node, function, guarded in _walk(tree):
            if _is_text_read(node) and not guarded:
                bad.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not bad, "text read with no errors= and no UnicodeDecodeError handler:\n" + "\n".join(bad)


def _is_json_read(node):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("load", "loads") and _name(node.func.value) == "json")


def test_json_reads_handle_a_recursion_error():
    bad = []
    for path, tree in sources():
        relative = path.relative_to(ROOT).as_posix()
        for node, function, guarded in _walk(tree, handled=DEPTH_HANDLERS):
            if _is_json_read(node) and not guarded and (relative, function) not in JSON_READS_CAUGHT_BY_CALLER:
                bad.append(f"{relative}:{node.lineno}")
    assert not bad, "json.load/json.loads with no RecursionError handler:\n" + "\n".join(bad)


def unchecked_json_reads(tree):
    """Functions that call json.load/json.loads but not _check_json."""
    bad = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        nodes = list(ast.walk(function))
        reads = [n for n in nodes if _is_json_read(n)]
        if reads and not any(isinstance(n, ast.Call) and _name(n.func) == "_check_json" for n in nodes):
            bad.append((reads[0].lineno, function.name))
    return bad


def test_config_json_reads_are_checked_before_any_write():
    bad = []
    for path in sorted((ROOT / "config").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        bad += [f"{path.relative_to(ROOT).as_posix()}:{line} in {name}()" for line, name in unchecked_json_reads(tree)]
    assert not bad, "json.load/json.loads in config/ without _check_json():\n" + "\n".join(bad)


def test_scripts_that_print_set_utf8_stdout():
    bad = []
    for path, tree in sources():
        nodes = [node for node, _, _ in _walk(tree)]
        prints = [node for node in nodes if _prints_to_stdout(node)]
        if prints and not any(_sets_utf8_stdout(node) for node in nodes):
            bad.append(f"{path.relative_to(ROOT)}:{prints[0].lineno}")
    assert not bad, 'print() without sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace"):\n' + "\n".join(bad)


def _glob_call(node, names):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and _name(node.func.value) == "glob" and node.func.attr in names)


def test_glob_patterns_escape_the_folder():
    bad = []
    for path, tree in sources():
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = [n for n in ast.walk(function) if _glob_call(n, {"glob", "iglob"})]
            if calls and not any(_glob_call(n, {"escape"}) for n in ast.walk(function)):
                bad.append(f"{path.relative_to(ROOT)}:{calls[0].lineno} in {function.name}()")
    assert not bad, "glob.glob() without glob.escape() in the same function:\n" + "\n".join(bad)


TAKES_AN_ARGUMENT = {"-X", "-W"}


def _isolated(node):
    """True when a [sys.executable, flags..., script] list or tuple holds "-I" among its leading
    flags, False when it does not, None when it is not a script run (a -m module run, or
    nothing after the interpreter)."""
    if not (isinstance(node, (ast.List, ast.Tuple)) and node.elts):
        return None
    first = node.elts[0]
    if not (isinstance(first, ast.Attribute) and first.attr == "executable" and _name(first.value) == "sys"):
        return None
    rest = list(node.elts[1:])
    while rest and isinstance(rest[0], ast.Constant) and isinstance(rest[0].value, str) \
            and rest[0].value.startswith("-"):
        flag = rest.pop(0).value
        if flag == "-I":
            return True
        if flag == "-m":
            return None
        if flag == "-c":
            return False
        if flag in TAKES_AN_ARGUMENT and rest:
            rest.pop(0)
    return False if rest else None


def test_tests_start_scripts_with_isolation():
    bad = []
    for folder in TEST_FOLDERS:
        for path in sorted((ROOT / folder).glob("*.py")):
            if path.relative_to(ROOT).as_posix() in RUNS_WITHOUT_ISOLATION:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            for node in ast.walk(tree):
                if _isolated(node) is False:
                    bad.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not bad, '[sys.executable, ...] without "-I" among its flags:\n' + "\n".join(bad)


@pytest.mark.parametrize("code, isolated", [
    ('[sys.executable, "-I", str(p)]', True),
    ('[sys.executable, "-X", "utf8", "-I", str(p)]', True),
    ('[sys.executable, "-I", "-c", code]', True),
    ('[sys.executable, str(p)]', False),
    ('[sys.executable, "-X", "utf8=0", str(p)]', False),
    ('(sys.executable, str(p))', False),
    ('[sys.executable, "-m", "pytest"]', None),
    ('[sys.executable]', None),
])
def test_rule_five_reads_the_leading_flags(code, isolated):
    # "-I" is accepted anywhere among the leading flags; a module run (-m) is not a script of
    # this repository; a tuple counts like a list.
    node = ast.parse(code).body[0].value
    assert _isolated(node) is isolated
