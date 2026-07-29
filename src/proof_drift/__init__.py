"""proof-to-code-drift — fail the build when the proof stops matching the code.

Formal proofs rot the moment a constant changes in the implementation and not in the specification.
Nothing in a normal CI run notices: the proof still compiles, the tests still pass, and the theorem
now describes a system you no longer ship.

Four jobs: **drift** (a bound constant whose values disagree), **vacuity** (a theorem padded with a
conjunct that is trivially true), **docstring** (prose claiming more than the statement proves),
and **coverage** (something the tool could not read — reported, never skipped).

CLEAN: CI tooling that reports. Implements no filed apparatus.
"""
from __future__ import annotations

__version__ = "0.1.0"

from .checks import (
    Finding,
    Report,
    check_docstring,
    check_drift,
    check_source,
    check_vacuity,
)
from .extract import Constant, extract_code_constants, extract_proof_constants

__all__ = [
    "check_drift", "check_vacuity", "check_docstring", "check_source",
    "Finding", "Report", "Constant", "extract_proof_constants", "extract_code_constants",
    "__version__",
]
