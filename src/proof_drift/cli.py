"""proof_drift.cli — the command line.

    proof-drift check --proofs DIR --code DIR    bind constants and compare
    proof-drift source FILE...                   vacuity + docstring checks over Lean sources
    proof-drift selftest                         positive controls for the checks themselves

EXIT CODES. Non-zero means findings were reported. That is a reporting convention: this tool
prints what it found and the caller decides what to do with it. It performs no step of admitting
or refusing anything — see CLAIMS-MAP.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .checks import Report, check_drift, check_source

_ICON = {"drift": "DRIFT", "vacuity": "VACUOUS", "docstring": "PROSE", "coverage": "UNREAD"}


def _print(rep: Report, *, quiet: bool = False) -> None:
    if not quiet:
        print(f"  proof constants ... {rep.n_proof_constants}")
        print(f"  code constants .... {rep.n_code_constants}")
        if rep.n_bound:
            print(f"  bound pairs ....... {rep.n_bound}")
        if rep.n_theorems_scanned:
            print(f"  theorems scanned .. {rep.n_theorems_scanned}")
        print()
    for f in rep.findings:
        loc = f.proof_site or ""
        if f.code_site:
            loc = f"{f.proof_site} vs {f.code_site}"
        print(f"  [{_ICON.get(f.kind, f.kind.upper()):>7}] {f.name}")
        print(f"            {f.detail}")
        if loc:
            print(f"            {loc}")


def _cmd_check(a) -> int:
    rep = check_drift(a.proofs, a.code)
    if a.json:
        print(json.dumps(rep.as_dict(), indent=2))
    else:
        print(f"proof-drift: {a.proofs} vs {a.code}\n")
        _print(rep)
        if rep.ok:
            if rep.n_bound == 0:
                # A zero-finding run that bound nothing has checked NOTHING. Saying so is the
                # difference between this tool and a green tick that means "I did not look".
                print("  ABSTAIN -- ZERO constant pairs were bound, so nothing was compared.")
                print("  This is NOT a pass. Binding is by NAME: a constant must appear with the")
                print("  same name on both sides. Check that --proofs and --code point where you")
                print("  think they do, and that the names actually match.")
                print("  If a zero-binding run is legitimate here, pass --allow-zero-bindings.")
            else:
                print(f"  OK -- {rep.n_bound} bound constant(s) agree.")
        else:
            print(f"\n  {len(rep.findings)} finding(s).")
    if rep.findings:
        return 1
    if rep.n_bound == 0 and not a.allow_zero_bindings:
        return 2          # ABSTAIN: distinct from both pass (0) and finding (1)
    return 0


def _cmd_source(a) -> int:
    from .checks import Finding
    total = Report()
    for path in a.files:
        if not os.path.isfile(path):
            # A file we could not read is a COVERAGE finding, not a silent skip.
            total.findings.append(Finding(
                "coverage", path,
                "not a readable file; a source the tool could not scan is not a source that passed"))
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            rep = check_source(fh.read(), path)
        total.findings.extend(rep.findings)
        total.n_theorems_scanned += rep.n_theorems_scanned
    if a.json:
        print(json.dumps(total.as_dict(), indent=2))
    else:
        print(f"proof-drift source: {len(a.files)} file(s)\n")
        _print(total)
        if total.ok:
            print(f"  OK -- {total.n_theorems_scanned} theorem(s) scanned, nothing flagged.")
        else:
            print(f"\n  {len(total.findings)} finding(s) across "
                  f"{total.n_theorems_scanned} theorem(s).")
            print("  Note: `docstring` findings are HEURISTIC -- they mean 'go read this pair', "
                  "not 'this is wrong'.")
    return 1 if total.findings else 0


_DEMO_LEAN = '''
/-- For every natural number, the successor is greater. -/
theorem succ_gt (n : Fin 8) : n.val < n.val + 1 := by omega

/-- A padded theorem: the second conjunct holds by reflexivity. -/
theorem padded (a b : Nat) : a + b = b + a ∧ a = a := by
  constructor
  · omega
  · rfl

theorem honest (a b : Nat) : a + b = b + a := by omega
'''

_DEMO_PROOF = "def MAX_BLOCKS : Nat := 512\ndef WINDOW_SIZE : Nat := 64\n"
_DEMO_CODE_OK = "MAX_BLOCKS = 512\nWINDOW_SIZE = 64\n"
_DEMO_CODE_DRIFT = "MAX_BLOCKS = 1024\nWINDOW_SIZE = 64\n"


def _cmd_selftest(a) -> int:
    """Positive controls. A checker never shown to fire is not a check."""
    import tempfile
    checks = []

    with tempfile.TemporaryDirectory() as td:
        p, c = os.path.join(td, "proofs"), os.path.join(td, "code")
        os.makedirs(p), os.makedirs(c)
        with open(os.path.join(p, "Spec.lean"), "w") as fh:
            fh.write(_DEMO_PROOF)

        with open(os.path.join(c, "impl.py"), "w") as fh:
            fh.write(_DEMO_CODE_OK)
        r = check_drift(p, c)
        checks.append(("agreeing constants pass", r.ok and r.n_bound == 2))

        with open(os.path.join(c, "impl.py"), "w") as fh:
            fh.write(_DEMO_CODE_DRIFT)
        r = check_drift(p, c)
        drift = [f for f in r.findings if f.kind == "drift"]
        checks.append(("drifted constant caught",
                       len(drift) == 1 and drift[0].name == "MAX_BLOCKS"))
        checks.append(("drift reports both sites",
                       bool(drift and drift[0].proof_site and drift[0].code_site)))

        # An empty code tree binds nothing: that must not read as agreement.
        r = check_drift(p, os.path.join(td, "code_empty"))
        checks.append(("binding nothing is reported, not passed", r.n_bound == 0))

    rep = check_source(_DEMO_LEAN, "demo.lean")
    vac = [f for f in rep.findings if f.kind == "vacuity"]
    checks.append(("`a = a` padding caught", len(vac) == 1 and vac[0].name == "padded"))
    checks.append(("honest theorem not flagged", all(f.name != "honest" for f in rep.findings)))
    doc = [f for f in rep.findings if f.kind == "docstring"]
    checks.append(("universal prose over a bounded statement flagged",
                   any(f.name == "succ_gt" for f in doc)))

    bad = 0
    for label, passed in checks:
        print(f"  {'ok  ' if passed else 'FAIL'}  {label}")
        bad += (not passed)
    if bad:
        print(f"\n{bad} positive control(s) failed.")
        return 1
    print("\nselftest passed.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="proof-drift",
        description="fail the build when the proof stops matching the code (measure-only)")
    ap.add_argument("--version", action="version", version=f"proof-to-code-drift {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="bind proof constants to runtime constants and compare")
    c.add_argument("--proofs", required=True, help="directory (or file) of proof sources")
    c.add_argument("--code", required=True, help="directory (or file) of runtime sources")
    # FAIL-CLOSED BY DEFAULT. A run that bound zero pairs compared nothing, and exiting 0 for
    # it hands CI a green tick for work that never happened -- the precise failure this tool
    # exists to catch, committed by the tool itself. Opting OUT is the flag that needs a reason.
    c.add_argument("--allow-zero-bindings", action="store_true",
                   help="exit 0 even when ZERO pairs were bound. Default is to ABSTAIN (exit 2), "
                        "because a run that compared nothing has not passed")
    c.add_argument("--require-bindings", action="store_true",
                   help=argparse.SUPPRESS)   # kept so existing CI invocations keep working
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=_cmd_check)

    s = sub.add_parser("source", help="vacuity + docstring checks over Lean sources")
    s.add_argument("files", nargs="+")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_source)

    t = sub.add_parser("selftest", help="positive controls for the checks themselves")
    t.set_defaults(fn=_cmd_selftest)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
