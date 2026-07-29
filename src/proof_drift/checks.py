"""proof_drift.checks — the four jobs.

    drift      a constant the proof depends on has a different value in the runtime source
    vacuity    a theorem padded with a conjunct that is trivially true
    docstring  the prose claims more than the statement proves
    coverage   the tool could not read part of what it was pointed at

The first is the obvious one. The other three exist because a proof can rot without any constant
changing at all.

**Vacuity** is the sharpest. A conjunct like `X = X` is true by reflexivity, so adding it to a
theorem changes nothing about what is proved while making the statement *look* stronger. We found
one of these in our own corpus. It compiled, it was axiom-clean, and it proved slightly less than
its own name suggested.

**Docstring** is the same disease one level up. The prose above a theorem is what people read; the
statement is what Lean checked. When the prose says "for all inputs" and the statement quantifies
over a bounded range, the theorem is fine and the claim is false — and nothing in a normal CI run
compares them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .extract import Constant, extract_code_constants, extract_proof_constants


@dataclass
class Finding:
    kind: str                 # drift | vacuity | docstring | coverage
    name: str
    detail: str
    proof_site: str = ""
    code_site: str = ""

    def as_dict(self) -> dict:
        d = {"kind": self.kind, "name": self.name, "detail": self.detail}
        if self.proof_site:
            d["proof_site"] = self.proof_site
        if self.code_site:
            d["code_site"] = self.code_site
        return d


@dataclass
class Report:
    findings: List[Finding] = field(default_factory=list)
    n_proof_constants: int = 0
    n_code_constants: int = 0
    n_bound: int = 0
    n_theorems_scanned: int = 0
    unparsed: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict:
        return {"ok": self.ok,
                "n_proof_constants": self.n_proof_constants,
                "n_code_constants": self.n_code_constants,
                "n_bound": self.n_bound,
                "n_theorems_scanned": self.n_theorems_scanned,
                "unparsed": self.unparsed,
                "findings": [f.as_dict() for f in self.findings]}


def check_drift(proof_root: str, code_root: str) -> Report:
    """Bind proof constants to runtime constants by name, and compare values.

    Only names present in BOTH are compared. A proof constant with no counterpart is not drift --
    it may be purely specificational -- but the count of bound pairs is reported, because a run
    that bound ZERO pairs has checked nothing and must not read as a pass.
    """
    proof, bad_p = extract_proof_constants(proof_root)
    code, bad_c = extract_code_constants(code_root)
    rep = Report(n_proof_constants=len(proof), n_code_constants=len(code),
                 unparsed=sorted(bad_p + bad_c))

    for name, pc in sorted(proof.items()):
        cc = code.get(name)
        if cc is None:
            continue
        rep.n_bound += 1
        pv, cv = pc.numeric, cc.numeric
        same = (pv == cv) if (pv is not None and cv is not None) else (pc.value == cc.value)
        if not same:
            rep.findings.append(Finding(
                "drift", name,
                f"proof={pc.value} runtime={cc.value}",
                pc.where(), cc.where()))

    for path in rep.unparsed:
        rep.findings.append(Finding(
            "coverage", path,
            "could not be read; a constant the tool could not parse is not a constant that agrees"))
    return rep


# --------------------------------------------------------------------------- vacuity

# A trivial conjunct holds by reflexivity and so adds nothing to what a theorem proves.
#
# These match a WHOLE conjunct, anchored, never a substring. That distinction is load-bearing:
# a substring search for `X = X` fires on the perfectly good `a + b = b + a`, because the text
# "b = b" appears across its equals sign. An earlier version of this check did exactly that and
# flagged an honest theorem, which is the fastest way to get a checker switched off.
_TRIVIAL = [
    re.compile(r"^([A-Za-z_][\w.']*)\s*=\s*\1$"),
    re.compile(r"^([A-Za-z_][\w.']*)\s*(?:≤|<=)\s*\1$"),
    re.compile(r"^([A-Za-z_][\w.']*)\s*(?:→|->)\s*\1$"),
    re.compile(r"^True$"),
]
_CONJ = re.compile(r"∧|/\\\\|\band\b")
_EXEMPT = "AUDIT-EXEMPT(trivial-conjunct)"


def _conjuncts(statement: str) -> List[str]:
    """Split a statement into conjuncts, dropping the `theorem NAME (binders) :` header.

    The header is removed by taking the text after the LAST top-level `:` that precedes the
    proposition -- binders like `(a b : Nat)` contain colons of their own, so a naive first-colon
    split would leave `Nat) : a + b ...` behind.
    """
    body = statement
    depth, cut = 0, -1
    for i, ch in enumerate(body):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            cut = i
    if cut != -1:
        body = body[cut + 1:]
    return [p.strip().strip("()").strip() for p in _CONJ.split(body) if p.strip()]

_THEOREM = re.compile(r"^\s*(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+)?"
                      r"(?:theorem|lemma)\s+(?P<name>[\w.']+)")


def _statement_of(lines: List[str], start: int) -> str:
    """The statement text: from the declaration to `:=` or `by`, whichever ends it."""
    buf = []
    for line in lines[start:start + 40]:
        buf.append(line)
        if ":=" in line or re.search(r"\bby\b", line):
            break
    text = " ".join(buf)
    for stop in (":=", " by "):
        i = text.find(stop)
        if i != -1:
            text = text[:i]
    return text


def check_vacuity(lean_source: str, path: str = "<source>") -> List[Finding]:
    """Flag theorems whose statement contains a trivially-true conjunct.

    An explicit `AUDIT-EXEMPT(trivial-conjunct)` marker on the declaration suppresses a finding.
    A marker is required rather than a heuristic exemption: an earlier version of this check
    excused theorems whose *prose* happened to contain a phrase, which let five unrelated
    theorems through on a coincidence.
    """
    lines = lean_source.splitlines()
    out: List[Finding] = []
    for i, line in enumerate(lines):
        m = _THEOREM.match(line)
        if not m:
            continue
        stmt = _statement_of(lines, i)
        if _EXEMPT in stmt or _EXEMPT in line:
            continue
        parts = _conjuncts(stmt)
        if len(parts) < 2:
            continue          # a lone proposition is the theorem itself, not padding
        flagged = next((p for p in parts if any(pat.match(p) for pat in _TRIVIAL)), None)
        if flagged is not None:
            out.append(Finding(
                "vacuity", m.group("name"),
                f"statement contains the trivially-true conjunct {flagged!r}; it holds by "
                f"reflexivity and proves nothing, while making the theorem look stronger",
                f"{path}:{i + 1}"))
    return out


# --------------------------------------------------------------------------- docstring

# Words whose presence in prose asserts strictly more than a bounded statement delivers.
_UNIVERSAL = re.compile(r"\b(every|all|any|always|never|arbitrary|unbounded|for all)\b", re.I)
_BOUNDED = re.compile(r"\b(Fin\s*\d+|Fin\s+n|< \d+|≤ \d+|<= \d+|BitVec|Vector\s|List\.length)")


def check_docstring(lean_source: str, path: str = "<source>") -> List[Finding]:
    """Flag a docstring that claims universality where the statement is bounded.

    This is a HEURISTIC and it is reported as one. It cannot decide whether prose is faithful; it
    can only point at the pairs a human should read. A finding here means *go look*, not *this is
    wrong* -- which is why the CLI reports docstring findings separately from drift.
    """
    lines = lean_source.splitlines()
    out: List[Finding] = []
    doc: List[str] = []
    doc_open = False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("/--"):
            doc, doc_open = [s], True
            if s.endswith("-/"):
                doc_open = False
            continue
        if doc_open:
            doc.append(s)
            if s.endswith("-/"):
                doc_open = False
            continue
        m = _THEOREM.match(line)
        if not m:
            if s and not s.startswith("--"):
                doc = []
            continue
        if not doc:
            continue
        prose = " ".join(doc)
        stmt = _statement_of(lines, i)
        u = _UNIVERSAL.search(prose)
        if u and _BOUNDED.search(stmt):
            out.append(Finding(
                "docstring", m.group("name"),
                f"prose says {u.group(0)!r} but the statement quantifies over a BOUNDED domain "
                f"-- the theorem may be fine while the claim above it is not",
                f"{path}:{i + 1}"))
        doc = []
    return out


def check_source(lean_source: str, path: str = "<source>") -> Report:
    """Run the source-level checks (vacuity + docstring) over one Lean file."""
    rep = Report()
    rep.n_theorems_scanned = len(_THEOREM.findall(lean_source)) or \
        sum(1 for ln in lean_source.splitlines() if _THEOREM.match(ln))
    rep.findings.extend(check_vacuity(lean_source, path))
    rep.findings.extend(check_docstring(lean_source, path))
    return rep


__all__ = ["Finding", "Report", "check_drift", "check_vacuity", "check_docstring", "check_source"]
