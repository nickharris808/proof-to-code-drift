# Contributing to proof-to-code-drift

## The rule that matters most

**Never report a pass for a run that checked nothing.**

A binding tool's worst output is a green tick from a run that bound zero pairs. Every code path
that could print success must first establish that something was actually compared — hence the
bound-pair count in every report and the `--require-bindings` flag for CI.

The same rule applies one level down: a file the tool could not read is a **coverage finding**,
never a silent skip. A constant the tool could not parse is not a constant that agrees.

## The second rule

**This tool reports. It never gates.** A PR that makes it block a deploy or withhold an artifact
changes the artifact's licence classification — see [`CLAIMS-MAP.md`](CLAIMS-MAP.md). CI enforces
this via `check_measure_only.py`.

## Adding an extraction form

1. Add the pattern to `PROOF_PATTERNS` or `CODE_PATTERNS` in `extract.py`, and register the file
   extension.
2. **Be literal.** Match declaration forms you can state precisely. Do not add fuzzy matching,
   name normalisation, or scope inference — an inference that fails silently looks exactly like
   agreement, which is the failure this whole tool exists to prevent.
3. Watch the comment filter. `#` opens a comment in Python and a *preprocessor directive* in C;
   treating `#define` as a comment silently drops every C constant. That bug shipped once here.
4. Add it to the `test_every_supported_code_form` parametrisation.

## Adding a check

Every check needs **both** cases in the test suite: the defect present, and a near-miss that must
*not* fire. The near-miss is the important one.

Concretely: an early version of the vacuity check searched for `X = X` as a substring, which fires
on the perfectly good `a + b = b + a` because the text "b = b" spans its equals sign. Flagging
honest theorems is the fastest way to get a checker switched off, so `check_vacuity` now tests
whole conjuncts and `test_an_honest_theorem_containing_a_substring_is_not_flagged` guards it.

Exemptions must be **explicit markers**, never heuristics. `AUDIT-EXEMPT(trivial-conjunct)` is a
token you have to type. An earlier exemption matched on prose and excused five unrelated theorems
by coincidence.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest -q          # 32 tests
proof-drift selftest         # positive controls for the checks themselves
```
