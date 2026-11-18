---
name: readback
description: Rewrite code so a person can read it, in any language, with proof that its behavior did not change. Use to clean up, untangle, simplify, unslop or make readable AI-written or legacy code, shell scripts or CI pipelines, or to audit them for readability.
---

# readback

Say the code again in plain words, then prove nothing changed in between. The claim is never "shorter": bloated code shrinks, packed code grows. The claim is "readable for a person, identical on everything the lock covers, and here is how strong the lock is."

## Ground rules

- One module per run: a file, a package, a script, a pipeline.
- The public surface found in triage does not change: exported names and types, parameter names where callers can pass them by keyword, CLI arguments, printed output, files written, calls made, job names.
- Bugs are pinned by the lock and reported, never fixed in the same run. A fix changes behavior and needs its own approval and its own change.
- Dead means proven. Search for callers through reflection, dependency injection, routes, config, string lookups and other repositories. A surviving mutant in a function is a hint, not proof.
- Plan before editing, then wait for approval.
- Once the first rewrite pass starts, the lock, the tests it froze and `.readback/config.json` never change. A red check means the rewrite is wrong.
- One commit per pass, in the repository's own commit style.

## Tooling

`python3 <this skill>/scripts/readback.py --root <module root> <command>`, Python 3.11 or later.

| Command | Does |
|---|---|
| `init --targets <globs>` | Writes `.readback/config.json` from the detected adapter |
| `surface` | Prints the public surface the lock will hold |
| `scenarios` | Runs the recorded scenarios and prints what they captured |
| `lock` | Accepts today's behavior: compile, surface, tests, scenarios, pipeline |
| `verify` | Exit 0 only if every check still matches the lock; writes `.readback/proof.json` |
| `mutate [--max N]` | Plants small changes and reports which ones the lock missed |

Adapters: `typescript`, `java`, `python`, `shell`, `gitlab-ci`, and `generic` for any other language. See `references/adapters.md`.

## Flow

### 1. Triage

1. Read the whole module. Map who calls it and what they can observe.
2. Run `init`, then fill in `surface.entries` (and `surface.names` where the language has no visibility rules) and the checks. `surface` prints what you declared; read it.
3. Go through `references/signs.md` group by group and list every sign as `file:line`, with fix, report, count or leave.
4. Look across the list for one change that removes several signs at once.
5. If little is wrong, say so and stop. "Light" is a valid result.

### 2. Lock

Read `references/lock.md` before writing anything here.

1. Write characterization cases at the public boundary only: tests that import what callers import, or scenarios that run the program the way callers run it. A test that reaches inside pins the structure you are about to change.
2. Take every expected value from running the original code, never from reasoning about it.
3. Pin each bug you found with a case named "known bug: ...".
4. Walk the edge-class checklist in `references/lock.md`.
5. `lock`, then `mutate`. For every surviving mutant, write down one of three things:
   - a missing case, which you add before relocking;
   - an equivalent mutant, with the reason it cannot change behavior;
   - unreachable code, with the evidence.
6. Aim for 80% of valid mutants killed, and every survivor explained either way. Until the first rewrite pass starts, delete `.readback/lock.json` and lock again as cases are added.

### 3. Plan

Post this, then stop:

```
MODULE      root, adapter, files, lines
SURFACE     what stays, from `surface` and triage
SIGNS       id, file:line, action
LOCK        tests or scenarios, mutants killed of valid, survivors explained
PASSES      what each of the three passes will change
DEFECTS     pinned bugs, reported only
DECISIONS   anything that needs the owner's call
```

### 4. Rewrite in three passes

After each pass, run `verify`. `LOCK HELD` is the only way forward. On `LOCK BROKEN`, revert the pass and redo it smaller. Never touch the frozen files.

1. **Mechanical.** Names, comments, proven-dead code, formatting. Follow the `self-documenting-code` skill for naming if it is installed.
2. **Structural.** Unpack packed code, flatten nesting, name the steps, extract or inline, group what changes together. Follow the `software-design` skill if it is installed.
3. **Boundary.** Types, outcome values in place of flags, parsing where outside data arrives. Only where callers see nothing new.

Equivalences that are not equivalent, all caught in this repo's evals:

- `trim().isEmpty()` versus `isBlank()`
- `echo "$x"` versus `printf '%s\n' "$x"`
- `"%.2f" % x` versus `f"{x:.2f}"` on bad input
- `a && b || c` versus if/else
- Destructuring versus property access on a null value
- The order of side effects and of short-circuit calls
- A Python parameter name, which keyword callers depend on
- A mutable default argument, whose identity callers can see

### 5. Prove and report

Run `verify`, then `mutate` on the rewrite to show the lock still sees the new code. Report in this shape, with no narrative:

```
Lock        22 tests, 2 surface lines; 58 of 65 mutants killed, 7 survivors explained
Verify      LOCK HELD (frozen, compile, surface, tests)
Change      128 -> 91 lines, 2 files deleted, 3 commits
Special     cases before -> after
Defects     one line each: where, what happens, who it affects
Not covered what the lock cannot see for this module
```

## What is guaranteed

Behavior is identical on everything the lock exercises, and the mutation score says how much that is. It is tested equivalence, not proven equivalence. Performance, concurrency, timing, and inputs no case or scenario reaches are outside it, and the report says which of those apply.

## References

- `references/signs.md`: what makes code hard to read, and the action for each sign.
- `references/lock.md`: lock tiers, characterization rules, the edge-class checklist, scenario files, classifying survivors.
- `references/adapters.md`: the adapters, every config field, and how to add a language.
