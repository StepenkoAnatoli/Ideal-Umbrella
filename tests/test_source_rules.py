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
   replaced byte becomes) used to end the script with UnicodeEncodeError.
4. A function that calls `glob.glob()` or `glob.iglob()` also calls `glob.escape()`. A user
   folder with `[`, `*` or `?` in its name (`proj[1]`) used to make `usage_breakdown.py` find
   no transcript at all.
5. A test that starts a script of this repository (`[sys.executable, ...]` in `tests/` and
   `keyline/tests/`) passes `-I` right after the interpreter, so the suite runs the scripts
   the way the docs say to run them: `-I` ignores `PYTHON*` variables and the script folder on
   `sys.path`. `tests/test_utf8_output.py` is the exception: it sets `PYTHONIOENCODING` on
   purpose, which `-I` would discard.
"""
import ast

from conftest import ROOT

FOLDERS = ["config", "hooks", "keyline", "scripts"]
TEST_FOLDERS = ["tests", "keyline/tests"]
RUNS_WITHOUT_ISOLATION = {"tests/test_utf8_output.py"}
DECODE_HANDLERS = {"UnicodeDecodeError", "ValueError", "Exception", "BaseException"}


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


def _handles_decode(handler):
    types = handler.type
    if types is None:
        return True
    names = [_name(e) for e in types.elts] if isinstance(types, ast.Tuple) else [_name(types)]
    return any(n in DECODE_HANDLERS for n in names)


def _walk(node, in_function=None, guarded=False):
    """Yield (node, enclosing function name, under a decode-handling try) for every node."""
    yield node, in_function, guarded
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        in_function = node.name
    if isinstance(node, ast.Try):
        body_guarded = guarded or any(_handles_decode(h) for h in node.handlers)
        for child in node.body:
            yield from _walk(child, in_function, body_guarded)
        for child in [*node.handlers, *node.orelse, *node.finalbody]:
            yield from _walk(child, in_function, guarded)
        return
    for child in ast.iter_child_nodes(node):
        yield from _walk(child, in_function, guarded)


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


def test_scripts_that_print_set_utf8_stdout():
    bad = []
    for path, tree in sources():
        nodes = [node for node, _, _ in _walk(tree)]
        prints = [node for node in nodes if _prints_to_stdout(node)]
        if prints and not any(_sets_utf8_stdout(node) for node in nodes):
            bad.append(f"{path.relative_to(ROOT)}:{prints[0].lineno}")
    assert not bad, 'print() without sys.stdout.reconfigure(encoding="utf-8"):\n' + "\n".join(bad)


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


def _starts_script(node):
    return (isinstance(node, ast.List) and node.elts
            and isinstance(node.elts[0], ast.Attribute) and node.elts[0].attr == "executable"
            and _name(node.elts[0].value) == "sys")


def test_tests_start_scripts_with_isolation():
    bad = []
    for folder in TEST_FOLDERS:
        for path in sorted((ROOT / folder).glob("*.py")):
            if path.relative_to(ROOT).as_posix() in RUNS_WITHOUT_ISOLATION:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            for node in ast.walk(tree):
                if not _starts_script(node):
                    continue
                second = node.elts[1] if len(node.elts) > 1 else None
                if not (isinstance(second, ast.Constant) and second.value == "-I"):
                    bad.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not bad, '[sys.executable, ...] without "-I" second:\n' + "\n".join(bad)
