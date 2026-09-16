"""Dependency-free tool schemas for both supported tool contracts."""

from __future__ import annotations

from copy import deepcopy

TOOLS_BASE = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a snapshot-relative file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "List snapshot-relative paths matching a pattern.",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search snapshot text with a Python regular expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": ""},
                },
                "required": ["pattern"],
            },
        },
    },
]

_CAP_NOTE = (
    " If the result starts with [TIME_CAPPED], the search was incomplete "
    "(time budget); narrow the scope (path) or pattern and retry. An empty "
    "result means the scan completed with no matches."
)
TOOLS_V4 = deepcopy(TOOLS_BASE)
for _tool in TOOLS_V4:
    if _tool["function"]["name"] in {"glob", "grep"}:
        _tool["function"]["description"] += _CAP_NOTE

for _tool in TOOLS_V4:
    if _tool["function"]["name"] != "read_file":
        continue
    _function = _tool["function"]
    _function["description"] += (
        " Returns at most max_chars characters starting at offset. If has_more is true, "
        "call again with offset=next_offset to read the rest."
    )
    _properties = _function["parameters"]["properties"]
    _properties["offset"] = {
        "type": "integer",
        "default": 0,
        "description": "Unicode code-point offset to start from",
    }
    _properties["max_chars"] = {
        "type": "integer",
        "minimum": 1,
        "maximum": 8_000,
        "default": 8_000,
    }

for _tool in TOOLS_V4:
    _function = _tool["function"]
    if _function["name"] == "grep":
        _function["description"] += (
            " Each match is `path:line:char_offset:text`. `char_offset` is the Unicode "
            "code-point offset where that line starts; pass it as `offset` to read_file, "
            "or pass `line` to read_file."
        )
    elif _function["name"] == "read_file":
        _function["description"] += " Give either offset or line."
        _function["parameters"]["properties"]["line"] = {
            "type": "integer",
            "minimum": 1,
            "description": (
                "1-based line number to start reading from. Alternative to offset; "
                "do not pass both."
            ),
        }
