"""Rules every script in this repository keeps, checked on the source itself.

1. `sys.exit` / `SystemExit` only in `main()` or at module level. A helper that exits cannot
   be caught by a caller's `except Exception` (SystemExit is a BaseException), so the install
   hint of `keyline_lint._tiktoken()` once stopped the whole lint instead of one abbreviation
   size. Helpers raise an Exception; the entry point turns it into a message and an exit code.
2. A text read (`open()` in text mode, `Path.read_text()`) either passes `errors=` or runs
   under a `try` that handles `UnicodeDecodeError` (or `ValueError` / `Exception`, which
   include it). A note, allow file, settings file or transcript that is not UTF-8 is a one-line
   error, never a traceback.
"""
import ast

from conftest import ROOT

FOLDERS = ["config", "hooks", "keyline", "scripts"]
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
