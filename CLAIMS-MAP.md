# CLAIMS-MAP — proof-to-code-drift

**Tag: CLEAN. Licence: Apache-2.0.**

This file exists so the CLEAN tag is *auditable* rather than asserted.

## The line

The filed family nearest this tool terminates in:

> *"…recording the recomputed root value over the evidence set … and **refusing to admit a gate
> decision** in reliance on the evidence set."*

`proof-to-code-drift` **compares and reports**. It reads proof sources and runtime sources, binds
constants by name, and prints what disagrees. It maintains no admission gate and refuses no gate
decision.

## Claims approached, and the step not performed

| Filed claim family | What it recites | What proof-to-code-drift does instead |
|---|---|---|
| Evidence-backed admission gating | maintaining an evidence set backing an admission gate; recomputing a root over it; **refusing to admit a gate decision** in reliance on it | Recomputes the comparison and prints findings. The exit code is a reporting convention, documented as such in `cli.py`. Nothing is admitted or refused. |
| Docstring-vs-statement conformance | mechanically checking that a recorded claim is not stronger than the checked statement, and **withholding the artifact** when it is | Performs the check and reports it as a **heuristic**. Withholds nothing. |
| Certificate emission | binding a recomputed value into a durable record and **writing it into the relying party's environment** | Emits JSON to stdout. There is no relying-party environment and no write path. |

## Why advisory-by-default is a licence decision, not a UX one

The moment this tool's non-zero exit is wired to **block a deploy**, that wiring supplies the
terminal step the claims recite. The tool has not changed; the deployment has.

That is why blocking is the caller's explicit act rather than a default, and why the boundary is
enforced mechanically: `oss/tools/check_measure_only.py` fails the build if a CLEAN-tagged artifact
grows an actuation path.

## Non-claims

- A clean run attests that the constants this tool **bound** agree. It attests nothing about
  constants it could not bind, which is why the bound-pair count is always reported.
- A `docstring` finding is a prompt to read, not a defect. Reporting it as a defect would make the
  tool wrong in the cases where prose is fine and merely unusual.
- This tool never asks whether a theorem is true.
