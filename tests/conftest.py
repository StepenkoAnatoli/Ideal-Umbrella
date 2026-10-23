import importlib.util
import json
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
