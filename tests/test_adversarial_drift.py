"""Adversarial regression tests — oracle: no input may produce a confident answer that is wrong.

The headline case here is a tool auditing itself into the very failure it detects: a run that
bound ZERO constant pairs compared nothing, and used to exit 0. CI reads exit codes, not prose,
so a green tick was being handed out for work that never happened.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from proof_drift.cli import main    # noqa: E402


def _tree(tmp_path, proofs: dict, code: dict):
    p, c = tmp_path / "proofs", tmp_path / "code"
    p.mkdir(); c.mkdir()
    for name, body in proofs.items():
        (p / name).write_text(body)
    for name, body in code.items():
        (c / name).write_text(body)
    return str(p), str(c)


# --------------------------------------------------------------- the zero-binding oracle

def test_zero_bindings_abstains_instead_of_passing(tmp_path, capsys):
    """Names that do not match on both sides bind nothing. That is not agreement."""
    p, c = _tree(tmp_path, {"a.lean": "def MAX_BLOCKS : Nat := 512"},
                           {"b.py": "UNRELATED_NAME = 1"})
    rc = main(["check", "--proofs", p, "--code", c])
    out = capsys.readouterr().out
    assert rc == 2, "exit 0 here is a green tick for a comparison that never happened"
    assert "ABSTAIN" in out
    assert "NOT a pass" in out
    assert "by NAME" in out, "it must explain WHY nothing bound"


def test_zero_bindings_can_be_opted_out_of_explicitly(tmp_path):
    p, c = _tree(tmp_path, {"a.lean": "def MAX_BLOCKS : Nat := 512"},
                           {"b.py": "UNRELATED_NAME = 1"})
    rc = main(["check", "--proofs", p, "--code", c, "--allow-zero-bindings"])
    assert rc == 0, "opting out must be possible -- but deliberate"


def test_empty_directories_abstain(tmp_path):
    """The commonest real cause: --proofs/--code pointed at the wrong place entirely."""
    p, c = _tree(tmp_path, {}, {})
    assert main(["check", "--proofs", p, "--code", c]) == 2


# --------------------------------------------------------------- real agreement / real drift

def test_matching_constants_pass(tmp_path):
    p, c = _tree(tmp_path, {"a.lean": "def MAX_BLOCKS : Nat := 512"},
                           {"b.py": "MAX_BLOCKS = 512"})
    assert main(["check", "--proofs", p, "--code", c]) == 0


def test_drifted_constant_is_a_finding(tmp_path):
    p, c = _tree(tmp_path, {"a.lean": "def MAX_BLOCKS : Nat := 512"},
                           {"b.py": "MAX_BLOCKS = 1024"})
    assert main(["check", "--proofs", p, "--code", c]) == 1, "drift outranks everything"


def test_drift_is_reported_even_when_other_pairs_agree(tmp_path):
    """One bad pair among many must not be averaged away into a pass."""
    p, c = _tree(tmp_path,
                 {"a.lean": "def MAX_BLOCKS : Nat := 512\ndef WINDOW : Nat := 64"},
                 {"b.py": "MAX_BLOCKS = 512\nWINDOW = 128"})
    assert main(["check", "--proofs", p, "--code", c]) == 1
