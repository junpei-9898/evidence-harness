from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from evidence_harness.tools.base import execute_tool_call
from evidence_harness.tools.exclusions import build_exclusion_table
from evidence_harness.tools.v4 import make_executor_v4

Executor = Callable[[Path, str, str], dict]


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("not visible", encoding="utf-8")
    os.symlink(outside, root / "linked")
    return root, outside


@pytest.fixture(params=["base", "v4"])
def executor(request: pytest.FixtureRequest, roots: tuple[Path, Path]) -> Executor:
    root, _ = roots
    if request.param == "base":
        return lambda path, name, arguments: execute_tool_call(path, name, arguments)
    bound = make_executor_v4(build_exclusion_table(root))
    return lambda path, name, arguments: bound(path, name, arguments)


@pytest.mark.parametrize("escape", ["dotdot", "absolute", "symlink"])
@pytest.mark.parametrize("tool", ["read_file", "glob", "grep"])
def test_tools_fail_closed_for_root_escape(
    roots: tuple[Path, Path], executor: Executor, escape: str, tool: str
) -> None:
    root, outside = roots
    values = {
        "dotdot": "../outside/secret.txt",
        "absolute": str(outside / "secret.txt"),
        "symlink": "linked/secret.txt",
    }
    path = values[escape]
    if tool == "read_file":
        arguments = {"path": path}
    elif tool == "glob":
        arguments = {"pattern": path}
    else:
        arguments = {"pattern": "not visible", "path": path}

    result = executor(root, tool, json.dumps(arguments))

    assert result["grounded"] is False
    assert "not visible" not in result["content"]
