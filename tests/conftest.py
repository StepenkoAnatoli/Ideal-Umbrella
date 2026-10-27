import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative_path):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def umask_022():
    """Pin the umask for a file-mode test: with the host's own umask the expected mode is
    computed from the same value the code under test reads, and under umask 077 a temp
    file's 0600 already equals it, so the test passes without the fix."""
    old = os.umask(0o022)
    try:
        yield 0o022
    finally:
        os.umask(old)


@pytest.fixture
def usage_breakdown():
    return load_module("usage_breakdown", "scripts/usage_breakdown.py")


@pytest.fixture
def add_to_repo():
    return load_module("add_to_repo", "config/add_to_repo.py")


@pytest.fixture
def context_check():
    return load_module("context_check", "hooks/context_check.py")


@pytest.fixture
def install_module():
    return load_module("install_module", "config/install.py")


def write_jsonl(path, events):
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    return path


def link_or_skip(link, target, target_is_directory=False):
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError:
        pytest.skip("cannot create symlinks here")


def loop_or_skip(link):
    """A symlink that points at itself, or a skip where links cannot be made or the OS does not
    report the loop as ELOOP (Windows)."""
    import errno
    link_or_skip(link, link.name)
    try:
        os.stat(link)
    except OSError as e:
        if e.errno == errno.ELOOP:
            return
    pytest.skip("this OS does not report a symlink loop as ELOOP")


def python_314_pathlib(monkeypatch):
    """pathlib as in Python 3.14: exists() and the is_*() checks say False for a path they
    cannot look at, where 3.13 and earlier raise. They look through os.stat and os.lstat, not
    os.path: on Windows os.path.exists() and the like are C functions that a patched os.stat
    does not reach."""
    import stat
    from pathlib import Path

    def says(path, kind, follow=True):
        try:
            return kind((os.stat if follow else os.lstat)(path).st_mode)
        except (OSError, ValueError):
            return False
    monkeypatch.setattr(Path, "exists", lambda self, *, follow_symlinks=True:
                        says(self, lambda mode: True, follow_symlinks))
    monkeypatch.setattr(Path, "is_file", lambda self, *, follow_symlinks=True:
                        says(self, stat.S_ISREG, follow_symlinks))
    monkeypatch.setattr(Path, "is_dir", lambda self, *, follow_symlinks=True:
                        says(self, stat.S_ISDIR, follow_symlinks))
    monkeypatch.setattr(Path, "is_symlink", lambda self: says(self, stat.S_ISLNK, False))


def refuse_looks_inside(folder, monkeypatch):
    """A folder that lists its names but may not be searched (mode 0444, or root's 0700 seen
    by a user, a sudo install): every look at a path inside it is refused, and so is a look
    that follows a link into it; the folder itself can be listed. Runs as root and on Windows,
    where file modes do not refuse anything."""
    import builtins
    import io
    import pathlib
    import stat
    inside = os.path.normcase(os.fspath(folder)) + os.sep
    real_lstat, real_readlink = os.lstat, os.readlink

    def target(path):
        """Where a look that follows links ends up."""
        for _ in range(40):
            try:
                if not stat.S_ISLNK(real_lstat(path).st_mode):
                    return path
            except OSError:
                return path
            linked = real_readlink(path)
            # Windows: the target of an absolute link reads back as \\?\C:\... or \\?\UNC\...
            if os.name == "nt" and linked.startswith("\\\\?\\"):
                linked = linked[4:]
                if linked.startswith("UNC\\"):
                    linked = "\\" + linked[3:]
            path = os.path.join(os.path.dirname(path), linked)
        return path

    def under(path):
        # normpath: 3.14's glob lists the folder as "folder/", which is allowed.
        return os.path.normcase(os.path.normpath(path)).startswith(inside)

    def wrap(real, follow):
        def look(path, *args, **kwargs):
            if isinstance(path, (str, os.PathLike)):
                path_ = os.fspath(path)
                if under(path_) or (follow and kwargs.get("follow_symlinks", True) and under(target(path_))):
                    raise PermissionError(13, "Permission denied", path_)
            return real(path, *args, **kwargs)
        return look
    for name, follow in (("stat", True), ("lstat", False), ("open", True), ("scandir", True), ("listdir", True)):
        monkeypatch.setattr(os, name, wrap(getattr(os, name), follow))
    monkeypatch.setattr(builtins, "open", wrap(builtins.open, True))
    monkeypatch.setattr(io, "open", wrap(io.open, True))   # pathlib's read_text and read_bytes
    accessor = getattr(pathlib, "_NormalAccessor", None)   # 3.10 pathlib kept its own references
    if accessor is not None:
        for name, follow in (("stat", True), ("lstat", False), ("open", True), ("scandir", True),
                             ("listdir", True)):
            if hasattr(accessor, name):
                monkeypatch.setattr(accessor, name, staticmethod(wrap(getattr(accessor, name), follow)))


def refuse_listing(folder, monkeypatch):
    """A folder that may be searched but not listed (mode 0311, or 0300 seen by its owner's
    group): listing it is refused, and a path inside it can still be looked at. Runs as root
    and on Windows, where file modes do not refuse anything."""
    import pathlib
    refused = os.path.normcase(os.path.normpath(os.fspath(folder)))

    def wrap(real):
        def listing(path=".", *args, **kwargs):
            if isinstance(path, (str, os.PathLike)) and \
                    os.path.normcase(os.path.normpath(os.fspath(path))) == refused:
                raise PermissionError(13, "Permission denied", os.fspath(path))
            return real(path, *args, **kwargs)
        return listing
    for name in ("scandir", "listdir"):
        monkeypatch.setattr(os, name, wrap(getattr(os, name)))
    accessor = getattr(pathlib, "_NormalAccessor", None)   # 3.10 pathlib kept its own references
    if accessor is not None:
        for name in ("scandir", "listdir"):
            if hasattr(accessor, name):
                monkeypatch.setattr(accessor, name, staticmethod(wrap(getattr(accessor, name))))
