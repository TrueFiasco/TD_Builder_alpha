# Registration description quality — review rubric

`register_component` asks the model to author the words a component is found by:
a one-line `summary`, a few `use_cases`, and a `parameter_descriptions` line per
custom parameter. Nothing in CI can tell you whether those words are any *good* —
a registration with a vacuous summary commits, reloads, and reports
`retrievable: true` exactly like a great one. This rubric is the human check.

**How to use it.** Open [`registration_quality.md`](registration_quality.md). Each
entry puts what the model **authored** beside what the component **actually is**
(parsed from the same run's `prepare` skeleton — parameters, menus, defaults,
inner ops, I/O). Score the three axes, write a one-word verdict, done. Two
minutes an entry; you are checking the model's judgement, not its plumbing.

Score each axis **0–2**. Anchors are deliberately concrete — if you find yourself
splitting hairs, score down.

---

## 1. Specificity — does it discriminate?

Could this summary belong to a dozen other components?

| | |
|---|---|
| **0** | Generic boilerplate. "A useful TouchDesigner component." Swap in any other comp and the sentence still reads true. |
| **1** | Names the domain but not the thing. "Generates geometry" — true of half the palette. Would not help you choose between this and its nearest neighbour. |
| **2** | Discriminating. A reader could pick this component out of a lineup of its closest KB/palette neighbours. For `knotgen`, that lineup includes `superFormula`, `circlePOP`, and every other parametric shape source — a 2 says what makes *this* one different (knot curves; selectable knot family). |

## 2. Correctness — is every claim true?

Check each claim against the **Actual** column. This is the axis where a
confident, fluent, wrong description does real damage: it ships into the KB and
misleads every future search.

| | |
|---|---|
| **0** | Contradicts reality. Wrong parameter meaning, invented behaviour, claims an input the component does not have, describes a menu token that does not exist. |
| **1** | True but thin, or subtly off. Nothing checkably false, but a parameter description restates the parameter's own name ("Numpoints: the number of points") and adds no information. |
| **2** | Every claim is checkable against the skeleton and true. Parameter descriptions say what the parameter *does to the output*, not what it is called. Defaults/ranges/tokens, where mentioned, match. |

**Menu tokens are the sharp edge.** Setting a menu by index instead of its
string token is the single most common build failure. If a menu parameter's
description invents tokens, renames them, or implies numeric indices, that is a
**0** on this axis regardless of how good the prose is.

## 3. Searchability — will it actually be found?

The registration exists to be retrieved. Ask: if I forgot this component's name
in six months, do these words contain what I'd type?

| | |
|---|---|
| **0** | Uses only internal jargon or the component's own name. Nobody would ever type these words. |
| **1** | Findable if you already half-know what it is. Missing the obvious synonyms or the task phrasing a user would reach for. |
| **2** | Carries the natural vocabulary — what it makes, what you'd use it for, and the parameter/menu words that matter (`trefoil`, `knot`, `curve`). `use_cases` read like things a person wants, not restatements of the summary. |

---

## Verdict

- **ship** — 5–6 total, no axis at 0. Good enough to live in the KB.
- **fix** — anything else. Note *which* axis in the entry; a Correctness 0 is a
  product-and-prompt problem worth chasing, not just a bad roll.

A pattern of `fix` across entries is a signal about the **prompt or the tool's
`next` coaching**, not about one unlucky sample — the scenarios ask explicitly
for a discriminating summary and a per-parameter line, so a systematic miss means
the ask is not landing. Raise it as a finding rather than re-rolling the capture.
