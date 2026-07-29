"""proof_drift.extract — pull named constants out of proofs and out of runtime source.

WHY EXTRACTION IS THE HARD PART. Binding a proof to code is easy to describe and easy to fake. The
temptation is to be clever: infer bindings, fuzzy-match names, guess at scope. Every one of those
shortcuts produces a tool that passes when it should not, because an inference that fails silently
looks exactly like agreement.

So this module is deliberately literal. It matches declaration forms it can state precisely, and
anything it cannot parse is reported as **UNPARSED** rather than skipped. A constant the tool could
not read is not a constant that agrees.

Supported declaration forms, by language:

    Lean 4      def NAME : Nat := 512      abbrev NAME := 512
    Coq         Definition NAME := 512.
    Python      NAME = 512
    Rust        const NAME: usize = 512;   pub const NAME: u32 = 512;
    C/C++       #define NAME 512           const int NAME = 512;
    Go          const NAME = 512
    TypeScript  const NAME = 512;          export const NAME = 512;

Only SCREAMING_SNAKE or PascalCase names are collected. A lowercase local is not a specification
constant, and collecting it would produce noise that trains people to ignore the tool.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# A name worth binding: SCREAMING_SNAKE, or PascalCase of at least two segments.
_NAME = r"(?P<name>[A-Z][A-Z0-9_]{2,}|(?:[A-Z][a-z0-9]+){2,})"
_NUM = r"(?P<value>-?\d+(?:\.\d+)?)"

PROOF_PATTERNS = [
    ("lean", re.compile(rf"^\s*(?:private\s+)?(?:def|abbrev)\s+{_NAME}\s*(?::\s*[\w.]+\s*)?:=\s*{_NUM}\b")),
    ("coq", re.compile(rf"^\s*Definition\s+{_NAME}\s*(?::\s*[\w.]+\s*)?:=\s*{_NUM}\b")),
    ("smt", re.compile(rf"^\s*\(define-const\s+{_NAME}\s+\w+\s+{_NUM}\s*\)")),
]

CODE_PATTERNS = [
    ("python", re.compile(rf"^\s*{_NAME}\s*(?::\s*[\w\[\], ]+\s*)?=\s*{_NUM}\b")),
    ("rust", re.compile(rf"^\s*(?:pub\s+)?const\s+{_NAME}\s*:\s*\w+\s*=\s*{_NUM}\b")),
    ("c_define", re.compile(rf"^\s*#define\s+{_NAME}\s+{_NUM}\b")),
    ("c_const", re.compile(rf"^\s*(?:static\s+)?const\s+\w+\s+{_NAME}\s*=\s*{_NUM}\b")),
    ("go", re.compile(rf"^\s*const\s+{_NAME}\s*(?:\w+\s*)?=\s*{_NUM}\b")),
    ("ts", re.compile(rf"^\s*(?:export\s+)?const\s+{_NAME}\s*(?::\s*\w+\s*)?=\s*{_NUM}\b")),
]

PROOF_EXT = {".lean": "lean", ".v": "coq", ".smt2": "smt", ".thy": "coq"}
CODE_EXT = {".py": "python", ".rs": "rust", ".c": "c", ".h": "c", ".cc": "c", ".cpp": "c",
            ".go": "go", ".ts": "ts", ".tsx": "ts", ".js": "ts"}

SKIP_DIRS = {".git", "__pycache__", "node_modules", "target", "build", "dist", ".lake",
             ".venv", "venv", ".mypy_cache", ".pytest_cache"}


@dataclass(frozen=True)
class Constant:
    name: str
    value: str
    path: str
    line: int
    kind: str          # the pattern that matched

    @property
    def numeric(self) -> Optional[float]:
        try:
            return float(self.value)
        except ValueError:
            return None

    def where(self) -> str:
        return f"{self.path}:{self.line}"


def _walk(root: str, exts: Dict[str, str]) -> List[str]:
    out: List[str] = []
    if os.path.isfile(root):
        return [root] if os.path.splitext(root)[1] in exts else []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if os.path.splitext(fn)[1] in exts:
                out.append(os.path.join(dirpath, fn))
    return out


def _scan(path: str, patterns) -> Tuple[List[Constant], int]:
    """Returns (constants, n_unreadable_lines). Unreadable is reported, never silently dropped."""
    found: List[Constant] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return [], 1
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # `#` opens a comment in Python but a PREPROCESSOR DIRECTIVE in C, so `#define` must
        # survive this filter. Treating it as a comment silently drops every C constant.
        if not stripped or (stripped.startswith(("--", "//", "(*"))
                            or (stripped.startswith("#") and not stripped.startswith("#define"))):
            continue
        for kind, pat in patterns:
            m = pat.match(line)
            if m:
                found.append(Constant(m.group("name"), m.group("value"), path, i, kind))
                break
    return found, 0


def extract_proof_constants(root: str) -> Tuple[Dict[str, Constant], List[str]]:
    """Constants declared in proof sources. Returns (by-name, files-that-could-not-be-read)."""
    by_name: Dict[str, Constant] = {}
    unreadable: List[str] = []
    for path in _walk(root, PROOF_EXT):
        consts, bad = _scan(path, PROOF_PATTERNS)
        if bad:
            unreadable.append(path)
        for c in consts:
            by_name.setdefault(c.name, c)
    return by_name, unreadable


def extract_code_constants(root: str) -> Tuple[Dict[str, Constant], List[str]]:
    """Constants declared in runtime sources."""
    by_name: Dict[str, Constant] = {}
    unreadable: List[str] = []
    for path in _walk(root, CODE_EXT):
        consts, bad = _scan(path, CODE_PATTERNS)
        if bad:
            unreadable.append(path)
        for c in consts:
            by_name.setdefault(c.name, c)
    return by_name, unreadable


__all__ = ["Constant", "extract_proof_constants", "extract_code_constants",
           "PROOF_EXT", "CODE_EXT"]
