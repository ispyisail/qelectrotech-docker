# TASK BRIEF — L6 phase 2: rank the inferred claims (Claude Opus 5)

> **Executor: Claude Opus 5, effort `xhigh`. Runs after L6 phase 1.**
>
> Phase 1 (delegated) produces `reports/pr-evidence.json` — a mechanical
> inventory classifying all 136 PRs as `observed` / `inferred` / `unstated`.
> **This phase does the part a classifier cannot: decide which of the inferred
> claims are actually worth re-testing.**
>
> The split exists because phase 1 is pattern-matching over text and phase 2 is
> risk judgement. Do not redo phase 1's work.

---

## 1. Input

- `reports/pr-evidence.json` from phase 1
- The lab binary from L2 (if built) — lets many claims be settled directly
- `scripts/qet-ab.sh` from L1 (if built) — lets a fixed-vs-unfixed comparison
  run in one command

Check phase 1's calibration before trusting its output: **#707 must be
`inferred`, #682 and #737 must be `observed`.** If that is wrong, phase 1 is
unreliable and you should say so rather than building on it.

---

## 2. The question

> *Of the PRs whose central claim rests on inference, which are most likely to
> be wrong in a way that matters — and what single check would settle each?*

---

## 3. Method

For each `inferred` PR, assess two axes:

**Likelihood the inference is wrong.** Raise it for:
- a claim about behaviour at a boundary (empty selection, first/last item, zero)
- reasoning that skips a layer ("the flag is set, therefore the file is written")
- a code path with a *parallel* path that could have been confused — this is the
  exact shape of #707, where `forceMovedByUser` and `forceRotateByUser` are
  parallel flags and the wrong one was called
- anything where the author noted uncertainty

**Cost of it being wrong.** Raise it for:
- merged and shipping to users
- silent failure modes (data written wrong, nothing crashes)
- anything other work now depends on

**Then be honest about the base rate: most inferred claims will be correct.**
The value is in the few that are not. **An audit flagging 30 PRs is useless; one
flagging 3 with specific reasons is worth acting on.**

---

## 4. Deliverable

`FINDINGS.md` — append a new section (do not rewrite existing entries):

1. **Phase 1 summary** — the distribution, and whether calibration held.
2. **Top candidates — at most 5.** For each: PR number, the claim, why the
   inference might be wrong, and **the specific command that would settle it**
   — ideally runnable with the L1 harness or the L2 lab binary.
3. **What you ruled out and why.** The reasoning matters more than the list.

---

## 5. The known-positive

**#707 is the calibration case and is already fully resolved** — see
`FINDINGS.md` F001 and F001-b. It was inferred, it was tested, the fix was
correct, and it had a second unnoticed symptom (`userx`/`usery` written
spuriously on all 67 conductors).

Use it to sanity-check your ranking method: **would your criteria have surfaced
#707 near the top?** If not, the criteria are miscalibrated — say so and adjust
before applying them to the rest.

---

## 6. Scope

**Analysis and, optionally, verification.** You may run the L1 harness or the L2
lab binary to settle a claim if it is cheap. You may not rewrite any PR, push,
comment on GitHub, or reopen anything.

If you do settle a claim, record it in `FINDINGS.md` with the exact command and
its real output — the same standard every other entry there meets.

---

## 7. Honesty requirements

- **If nothing looks risky, say so.** "136 PRs audited, no further #707-class
  gaps found" is a valid and valuable result. Do not manufacture candidates to
  justify the exercise.
- **Do not re-flag #707.** It is resolved; it is the calibration case.
- **Separate "unverified" from "suspect."** Most inferred claims are simply
  unverified and fine. Only elevate one to suspect when you can articulate the
  specific way it could be wrong.
