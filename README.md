# codebase-readback

Agent skill that rewrites code so people can read it, in any language, and proves the behavior did not change.

In aviation, a readback is the pilot repeating an instruction so both sides confirm nothing changed in between. This skill does the same for code: it says the code again in plain words, then proves the behavior is identical.

Status: in development. Progress is tracked in [tasks/todo.md](tasks/todo.md).

## How a run works

1. Scope one module and map its public surface, callers and side effects
2. Audit it against [the signs catalog](skills/readback/references/signs.md) and decide how much to change
3. Lock the behavior at the public boundary, and measure the lock with mutants
4. Rewrite in three passes, one commit each, with `readback verify` after every pass
5. Report what changed, the proof, and the bugs found and left untouched

The run flow is in [SKILL.md](skills/readback/SKILL.md). The lock is tooling, not instructions:

```
python3 skills/readback/scripts/readback.py --root path/to/module init --targets 'src/**/*.ts'
python3 skills/readback/scripts/readback.py --root path/to/module lock
python3 skills/readback/scripts/readback.py --root path/to/module mutate
python3 skills/readback/scripts/readback.py --root path/to/module verify
```

## What is guaranteed

Behavior is identical on everything the lock exercises, and the strength of that lock is measured by mutation score. That is tested equivalence, not proven equivalence. Performance and concurrency are outside the guarantee.

## Languages

| Adapter | Surface from | Behavior locked by |
|---|---|---|
| TypeScript and JavaScript | TypeScript compiler API | Vitest, or scenarios |
| Java | `javap -public` | JUnit through Maven, or scenarios |
| Python | `ast` | pytest, or scenarios |
| Shell | | Scenarios with stubbed commands |
| GitLab CI | | Every job's rules across the trigger matrix |
| Anything else | tree-sitter | Scenarios at the process boundary, or any test runner with JUnit output |

## Evals

`python3 evals/run-lock-evals.py` locks each fixture, measures the lock with mutants, checks that a reference rewrite holds, and checks that every planted bad refactor breaks the lock. `node evals/check-answer-keys.mjs` checks the audit answer keys.

## License

Apache-2.0. See [LICENSE](LICENSE).
