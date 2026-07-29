"""Test suite for proof-to-code-drift. Every test plants a defect and asserts the check fires."""
from __future__ import annotations

import json
import os

import pytest

from proof_drift import (
    check_docstring,
    check_drift,
    check_source,
    check_vacuity,
    extract_code_constants,
    extract_proof_constants,
)
from proof_drift.checks import _conjuncts

PROOF = "def MAX_BLOCKS : Nat := 512\ndef WINDOW_SIZE : Nat := 64\nabbrev RETRIES := 3\n"


def _tree(tmp_path, proof: str, code: str, code_name: str = "impl.py"):
    p, c = tmp_path / "proofs", tmp_path / "code"
    p.mkdir(), c.mkdir()
    (p / "Spec.lean").write_text(proof)
    (c / code_name).write_text(code)
    return str(p), str(c)


# ---------------------------------------------------------------- extraction

def test_lean_constants_are_extracted(tmp_path):
    (tmp_path / "S.lean").write_text(PROOF)
    consts, bad = extract_proof_constants(str(tmp_path))
    assert set(consts) == {"MAX_BLOCKS", "WINDOW_SIZE", "RETRIES"}
    assert consts["MAX_BLOCKS"].value == "512"
    assert not bad


def test_coq_and_smt_forms_are_extracted(tmp_path):
    (tmp_path / "S.v").write_text("Definition MAX_DEPTH := 7.\n")
    (tmp_path / "S.smt2").write_text("(define-const BOUND Int 42)\n")
    consts, _ = extract_proof_constants(str(tmp_path))
    assert consts["MAX_DEPTH"].value == "7"
    assert consts["BOUND"].value == "42"


@pytest.mark.parametrize("fname,src,name,val", [
    ("impl.py", "MAX_BLOCKS = 512\n", "MAX_BLOCKS", "512"),
    ("lib.rs", "pub const MAX_BLOCKS: usize = 512;\n", "MAX_BLOCKS", "512"),
    ("h.h", "#define MAX_BLOCKS 512\n", "MAX_BLOCKS", "512"),
    ("m.go", "const MAX_BLOCKS = 512\n", "MAX_BLOCKS", "512"),
    ("a.ts", "export const MAX_BLOCKS = 512;\n", "MAX_BLOCKS", "512"),
])
def test_every_supported_code_form(tmp_path, fname, src, name, val):
    (tmp_path / fname).write_text(src)
    consts, _ = extract_code_constants(str(tmp_path))
    assert consts[name].value == val


def test_lowercase_locals_are_not_collected(tmp_path):
    """Collecting locals produces noise, and noise trains people to ignore the tool."""
    (tmp_path / "impl.py").write_text("tmp = 5\ni = 0\nMAX_BLOCKS = 512\n")
    consts, _ = extract_code_constants(str(tmp_path))
    assert set(consts) == {"MAX_BLOCKS"}


def test_comments_are_ignored(tmp_path):
    (tmp_path / "impl.py").write_text("# MAX_BLOCKS = 999\nMAX_BLOCKS = 512\n")
    consts, _ = extract_code_constants(str(tmp_path))
    assert consts["MAX_BLOCKS"].value == "512"


# ---------------------------------------------------------------- drift

def test_agreeing_constants_pass(tmp_path):
    p, c = _tree(tmp_path, PROOF, "MAX_BLOCKS = 512\nWINDOW_SIZE = 64\n")
    rep = check_drift(p, c)
    assert rep.ok and rep.n_bound == 2


def test_drifted_constant_is_caught(tmp_path):
    p, c = _tree(tmp_path, PROOF, "MAX_BLOCKS = 1024\nWINDOW_SIZE = 64\n")
    rep = check_drift(p, c)
    assert not rep.ok
    d = [f for f in rep.findings if f.kind == "drift"]
    assert len(d) == 1 and d[0].name == "MAX_BLOCKS"
    assert "proof=512 runtime=1024" in d[0].detail


def test_drift_reports_both_sites(tmp_path):
    """A finding without locations is a puzzle rather than a bug report."""
    p, c = _tree(tmp_path, PROOF, "MAX_BLOCKS = 1024\n")
    d = [f for f in check_drift(p, c).findings if f.kind == "drift"][0]
    assert "Spec.lean:1" in d.proof_site
    assert "impl.py:1" in d.code_site


def test_a_proof_only_constant_is_not_drift(tmp_path):
    """RETRIES exists only in the spec. That is not drift; it may be purely specificational."""
    p, c = _tree(tmp_path, PROOF, "MAX_BLOCKS = 512\nWINDOW_SIZE = 64\n")
    rep = check_drift(p, c)
    assert rep.ok
    assert rep.n_proof_constants == 3 and rep.n_bound == 2


def test_binding_nothing_is_reported_not_passed(tmp_path):
    """A run that bound zero pairs has compared nothing. It must not read as agreement."""
    p, c = _tree(tmp_path, PROOF, "unrelated = 1\n")
    rep = check_drift(p, c)
    assert rep.n_bound == 0
    assert rep.ok            # no findings...
    # ...but the CLI refuses to call that a pass. This is now the DEFAULT: exit 2 = ABSTAIN,
    # distinct from 0 (checked, holds) and 1 (checked, fails). Fail-closed, because CI reads
    # the exit code and "compared nothing" must never arrive as a green tick.
    from proof_drift.cli import main
    assert main(["check", "--proofs", p, "--code", c]) == 2
    assert main(["check", "--proofs", p, "--code", c, "--require-bindings"]) == 2
    # Opting out remains possible, but has to be said out loud.
    assert main(["check", "--proofs", p, "--code", c, "--allow-zero-bindings"]) == 0


def test_float_values_compare_numerically(tmp_path):
    p, c = _tree(tmp_path, "def RATIO : Float := 0.50\n", "RATIO = 0.5\n")
    assert check_drift(p, c).ok


# ---------------------------------------------------------------- vacuity

def test_reflexive_conjunct_is_caught():
    f = check_vacuity("theorem padded (a b : Nat) : a + b = b + a ∧ a = a := by sorry")
    assert len(f) == 1 and f[0].name == "padded"
    assert "'a = a'" in f[0].detail


def test_an_honest_theorem_containing_a_substring_is_not_flagged():
    """`a + b = b + a` contains the text 'b = b' across its equals sign. A substring search
    fires on it; this must not. Flagging honest theorems is how a checker gets switched off."""
    assert check_vacuity("theorem honest (a b : Nat) : a + b = b + a := by omega") == []


def test_true_conjunct_is_caught():
    f = check_vacuity("theorem padded (a : Nat) : a > 0 ∧ True := by sorry")
    assert len(f) == 1


def test_reflexive_le_is_caught():
    f = check_vacuity("theorem padded (a b : Nat) : a < b ∧ a ≤ a := by sorry")
    assert len(f) == 1


def test_an_explicit_exemption_marker_suppresses_the_finding():
    src = ("theorem padded (a b : Nat) : a + b = b + a ∧ a = a "
           "-- AUDIT-EXEMPT(trivial-conjunct)\n  := by sorry")
    assert check_vacuity(src) == []


def test_a_lone_proposition_is_never_padding():
    assert check_vacuity("theorem t (a : Nat) : a = a := rfl") == []


def test_conjunct_splitter_drops_the_binder_header():
    parts = _conjuncts("theorem padded (a b : Nat) : a + b = b + a ∧ a = a ")
    assert parts == ["a + b = b + a", "a = a"]


# ---------------------------------------------------------------- docstring

def test_universal_prose_over_a_bounded_statement_is_flagged():
    src = ("/-- For every natural number, the successor is greater. -/\n"
           "theorem succ_gt (n : Fin 8) : n.val < n.val + 1 := by omega\n")
    f = check_docstring(src)
    assert len(f) == 1 and f[0].name == "succ_gt"


def test_matching_prose_and_statement_are_not_flagged():
    src = ("/-- For a bounded index, the successor is greater. -/\n"
           "theorem succ_gt (n : Fin 8) : n.val < n.val + 1 := by omega\n")
    assert check_docstring(src) == []


def test_a_theorem_with_no_docstring_is_not_flagged():
    assert check_docstring("theorem t (n : Fin 8) : n.val = n.val := rfl") == []


# ---------------------------------------------------------------- CLI

def test_cli_selftest_passes():
    from proof_drift.cli import main
    assert main(["selftest"]) == 0


def test_cli_check_exits_nonzero_on_drift(tmp_path, capsys):
    from proof_drift.cli import main
    p, c = _tree(tmp_path, PROOF, "MAX_BLOCKS = 1024\n")
    assert main(["check", "--proofs", p, "--code", c]) == 1
    assert "DRIFT" in capsys.readouterr().out


def test_cli_check_exits_zero_when_bound_and_agreeing(tmp_path):
    from proof_drift.cli import main
    p, c = _tree(tmp_path, PROOF, "MAX_BLOCKS = 512\nWINDOW_SIZE = 64\n")
    assert main(["check", "--proofs", p, "--code", c]) == 0


def test_cli_says_so_when_it_compared_nothing(tmp_path, capsys):
    from proof_drift.cli import main
    p, c = _tree(tmp_path, PROOF, "unrelated = 1\n")
    main(["check", "--proofs", p, "--code", c])
    assert "ZERO constant pairs were bound" in capsys.readouterr().out


def test_cli_json_is_machine_readable(tmp_path, capsys):
    from proof_drift.cli import main
    p, c = _tree(tmp_path, PROOF, "MAX_BLOCKS = 1024\n")
    main(["check", "--proofs", p, "--code", c, "--json"])
    rep = json.loads(capsys.readouterr().out)
    assert rep["ok"] is False and rep["findings"][0]["kind"] == "drift"


def test_cli_source_reports_an_unreadable_file_as_a_finding(tmp_path, capsys):
    """A source the tool could not scan is not a source that passed."""
    from proof_drift.cli import main
    assert main(["source", str(tmp_path / "nope.lean")]) == 1
    assert "UNREAD" in capsys.readouterr().out


def test_cli_source_flags_padding_in_a_real_file(tmp_path, capsys):
    from proof_drift.cli import main
    f = tmp_path / "T.lean"
    f.write_text("theorem padded (a b : Nat) : a + b = b + a ∧ a = a := by sorry\n")
    assert main(["source", str(f)]) == 1
    assert "VACUOUS" in capsys.readouterr().out
