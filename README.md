# proof-to-code-drift

**Someone changed a constant in the implementation. Your proof still compiles.**

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](pyproject.toml)

Four CI jobs that catch the ways a formal proof rots while every check stays green.

**Not yet on PyPI.** The command below is the one that works today. It installs from this repository, pinned to a tag.

```bash
pip install "git+https://github.com/nickharris808/proof-to-code-drift@v0.1.0"
```

`pip install proof-to-code-drift` is the intended command once the name is published. **It 404s today**, which is why it is not the first step above. The tag is pinned rather than `@main` so a reader installs the exact code this README documents.

## Why this exists

A proof binds a *specification* to a *claim*. Nothing binds the specification to the code you
actually ship. So the ordinary failure is silent: someone bumps `MAX_BLOCKS` from 512 to 1024 in
the implementation, the Lean file still says 512, everything compiles, every test passes, and the
theorem now describes a system you no longer run.

Three more ways it rots without any constant changing at all:

| job | what it catches |
|---|---|
| **drift** | a constant the proof depends on has a different value in the runtime source |
| **vacuity** | a theorem padded with a conjunct that is trivially true |
| **docstring** | prose claiming more than the statement proves |
| **coverage** | something the tool could not read — reported, never skipped |

**Vacuity** is the sharpest of these. A conjunct like `a = a` holds by reflexivity, so adding it
changes nothing about what is proved while making the statement *look* stronger. We found one in
our own corpus: it compiled, it was axiom-clean, and it proved slightly less than its name implied.

## Install

**Not yet on PyPI.** The command below is the one that works today. It installs from this repository, pinned to a tag.

```bash
pip install "git+https://github.com/nickharris808/proof-to-code-drift@v0.1.0"
```

`pip install proof-to-code-drift` is the intended command once the name is published. **It 404s today**, which is why it is not the first step above. The tag is pinned rather than `@main` so a reader installs the exact code this README documents.

## 30-second quickstart

```bash
# Do the constants in your proofs match the ones in your code?
proof-drift check --proofs ./theory --code ./src

# Is any theorem padded, or any docstring overclaiming?
proof-drift source theory/*.lean

# Do the checks themselves still fire?
proof-drift selftest
```

## Worked example

```console
$ cat proofs/Cache.lean
def MAX_BLOCKS : Nat := 512
def WINDOW_SIZE : Nat := 64

$ cat src/cache.py
MAX_BLOCKS = 1024
WINDOW_SIZE = 64

$ proof-drift check --proofs proofs --code src
proof-drift: proofs vs src

  proof constants ... 2
  code constants .... 2
  bound pairs ....... 2

  [  DRIFT] MAX_BLOCKS
            proof=512 runtime=1024
            proofs/Cache.lean:1 vs src/cache.py:1

  1 finding(s).
$ echo $?
1
```

And the source-level checks:

```console
$ proof-drift source theory/Padded.lean
  [VACUOUS] padded
            statement contains the trivially-true conjunct 'a = a'; it holds by
            reflexivity and proves nothing, while making the theorem look stronger
            theory/Padded.lean:1
```

## It refuses when it checked nothing

The most dangerous output any binding tool can produce is a green tick from a run that bound zero
pairs — a passing build that compared nothing at all. **That is now a hard abstain, by default:**

```console
$ proof-drift check --proofs proofs --code unrelated/
proof-drift: proofs vs unrelated/

  proof constants ... 1
  code constants .... 1

  ABSTAIN -- ZERO constant pairs were bound, so nothing was compared.
  This is NOT a pass. Binding is by NAME: a constant must appear with the
  same name on both sides. Check that --proofs and --code point where you
  think they do, and that the names actually match.
  If a zero-binding run is legitimate here, pass --allow-zero-bindings.
$ echo $?
2
```

Note both counts are **1** — there were constants on each side. They simply share no name, so
nothing bound. That is the failure mode this catches: it looks like work happened.

This used to exit `0` unless you passed `--require-bindings`, which the README described as
"recommended in CI". **A setting that is recommended for everyone should not be opt-in** — and a
tool whose whole purpose is catching green ticks that mean "I did not look" should not have been
handing one out itself. The default is now fail-closed; opting out is the flag that needs a reason.

| code | meaning |
|---:|---|
| `0` | constants were bound and they agree |
| `1` | a finding — drift, vacuity, docstring overclaim, or unreadable source |
| `2` | **ABSTAIN** — nothing was compared |

## Supported forms

| | forms |
|---|---|
| **Proofs** | Lean 4 (`def`, `abbrev`) · Coq (`Definition`) · SMT-LIB (`define-const`) |
| **Code** | Python · Rust (`const`) · C/C++ (`#define`, `const`) · Go · TypeScript |

Only `SCREAMING_SNAKE` and `PascalCase` names are collected. A lowercase local is not a
specification constant, and collecting it would produce noise that trains people to ignore the tool.

## Honest limits

- **Binding is by name.** A proof constant and a code constant are compared when their names match
  exactly. Renaming one side breaks the binding — and the tool reports that it bound fewer pairs,
  which is the signal to look.
- **A proof-only constant is not drift.** It may be purely specificational. Only names present on
  both sides are compared.
- **`docstring` is a heuristic and is reported as one.** It cannot decide whether prose is
  faithful; it points at pairs a human should read. A finding means *go look*, not *this is wrong*.
- **Extraction is deliberately literal.** Declaration forms that cannot be parsed precisely are
  reported as unreadable rather than guessed at. A constant the tool could not read is not a
  constant that agrees.
- **This is not a proof checker.** It never asks whether your theorem is true — only whether the
  numbers it rests on are still the numbers you ship. Pair it with a real toolchain (see
  [`formal-proof-mcp`](https://github.com/nickharris808/formal-proof-mcp) for the axiom audit that catches `sorry`).

## The commercial edition

This tool **reports**. It does not gate.

Advisory-by-default is the deliberate posture: the exit code is a reporting convention, and the
caller decides what to do with it. Wiring a failed check so that it **blocks a deploy** is the
step this package does not perform — see [`CLAIMS-MAP.md`](CLAIMS-MAP.md).

The gate corpus, the lowering pipeline, and the certificate-issuing faucet are the licensed
offering. **Reading is free. Enforcing is licensed.**

## Licence

Apache-2.0 · **CLEAN** — CI tooling that reports; implements no filed apparatus.

<!-- HONEST-SCOPE -->
## Honest scope — what a passing run proves, and what it does not

The two halves are inseparable. A tool that states only the first half is marketing.

**It proves:**

- whether constants your proofs depend on still hold the same values in your runtime source, bound BY NAME
- whether a theorem is padded with a trivially-true conjunct
- whether a docstring claims more than its statement proves (a heuristic, reported as one)

**It does NOT prove:**

- that your proof is TRUE — it never looks at the proof, only at the numbers it rests on
- that a clean run means agreement, if zero pairs bound. That case ABSTAINS
- that a renamed constant is safe; renaming breaks the binding, and the bound count is the signal

## Troubleshooting

| you see | what it means and how to fix it |
|---|---|
| `ABSTAIN — ZERO constant pairs were bound` | Binding is by NAME: a constant must appear with the same name in both trees. Check --proofs/--code, or pass `--allow-zero-bindings` if that is genuinely expected. |

These strings are checked against the live code by `python oss/tools/gen_docs.py --verify`, so a changed message cannot leave stale advice behind.

Full CLI reference, generated from `--help`: [`docs/CLI.md`](docs/CLI.md)
<!-- /HONEST-SCOPE -->

## Contributing

Bug reports and pull requests welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

**A false accusation is a defect of equal severity to a missed detection.** If this tool flags something correct, open an issue with the input and the verdict you expected: over-refusal trains people to bypass refusals, which destroys the tool.

Citation metadata is in [CITATION.cff](CITATION.cff).

<!-- PORTFOLIO -->
---

## The rest of the portfolio

25 artifacts, one idea: **a measurement you cannot check is a press release.** Every tool
here reports; none of them gates.

**Tools**

| | |
|---|---|
| [`abstain-bench`](https://github.com/nickharris808/abstain-bench) | how often does a verifier pass input it could not check? |
| [`evidence`](https://github.com/nickharris808/evidence) | run the whole portfolio over your repo — the weakest leg, never the mean |
| [`floorgen`](https://github.com/nickharris808/floorgen) | what must your system remember? an exact lower bound |
| [`formal-proof-mcp`](https://github.com/nickharris808/formal-proof-mcp) | a proof kernel for your coding agent |
| [`gatecount`](https://github.com/nickharris808/gatecount) | exactly how many states does removing this check admit? |
| [`gridlock`](https://github.com/nickharris808/gridlock) | certify a wait-for relation cannot wedge |
| [`honestbench`](https://github.com/nickharris808/honestbench) | measure your CI's escape rate |
| [`kvleak`](https://github.com/nickharris808/kvleak) | cross-tenant leak scanner |
| [`kvprobe`](https://github.com/nickharris808/kvprobe) | model-substitution detector with a measured FPR |
| [`preregister`](https://github.com/nickharris808/preregister) | refuses to seal a plan whose conclusion is already fixed |
| [`proof-carrying-ci`](https://github.com/nickharris808/proof-carrying-ci) | the whole portfolio as one CI check, with SARIF |
| [`proof-to-code-drift`](https://github.com/nickharris808/proof-to-code-drift) | fail the build when the proof stops matching ← you are here |
| [`sf-verify`](https://github.com/nickharris808/sf-verify) | re-derive admission decisions offline |
| [`signoff-cert`](https://github.com/nickharris808/signoff-cert) | certificates that carry their own false-pass bound |
| [`tokencount`](https://github.com/nickharris808/tokencount) | a token count both parties can recompute |

**Benchmarks** — each recomputes one of our own published numbers from its certificate

| | |
|---|---|
| [`illusion-bench`](https://github.com/nickharris808/illusion-bench) | how many broken kernels does your oracle admit? |
| [`kv-reuse-econ-bench`](https://github.com/nickharris808/kv-reuse-econ-bench) | recompute our economics headline |
| [`llm-tenant-isolation-bench`](https://github.com/nickharris808/llm-tenant-isolation-bench) | recompute our isolation figures |

**Datasets**

| | |
|---|---|
| [`abstain-corpus`](https://huggingface.co/datasets/nickh007/abstain-corpus) | 32 inputs a verifier must NOT pass |
| [`kv-reuse-econ-traces`](https://huggingface.co/datasets/nickh007/kv-reuse-econ-traces) | per-workload reuse accounting + the closed form |
| [`kv-tenant-isolation-bench`](https://huggingface.co/datasets/nickh007/kv-tenant-isolation-bench) | isolation observations, uninterpretable rows included |
| [`llm-precision-fingerprints`](https://huggingface.co/datasets/nickh007/llm-precision-fingerprints) | precision-labelled logprobs with a negative control |

**Try it in a browser** — no install, no GPU

| | |
|---|---|
| [`negative-results-atlas`](https://huggingface.co/spaces/nickh007/negative-results-atlas) | ten claims we took back |
| [`tenant-leak-demo`](https://huggingface.co/spaces/nickh007/tenant-leak-demo) | the residency calculator |
| [`wait-for-visualiser`](https://huggingface.co/spaces/nickh007/wait-for-visualiser) | paste a wait-for graph, see the cycle |

### Documentation

Everything above, explained in one place: **<https://nickharris808.github.io/evidence-docs/>** —
the [tutorial](https://nickharris808.github.io/evidence-docs/start/tutorial/),
[what this proves and what it does not](https://nickharris808.github.io/evidence-docs/concepts/what-this-proves/),
and a [CLI reference](https://nickharris808.github.io/evidence-docs/reference/cli/) generated by
running `--help` on every published command.

### The commercial edition

Everything above is **measure-only** and Apache-2.0: it tells you what is true and never acts on
it. The **enforcement** side — binding a partition key at the admission decision, the compiled gate
corpus, and the certificate-*issuing* faucet — is covered by filed patents and licensed separately.

**Reading is free. Enforcing is licensed.**
<!-- /PORTFOLIO -->
