# codebase-readback

Agent skill that rewrites AI-generated code so humans can read it, and proves the behavior did not change.

In aviation, a readback is the pilot repeating an instruction so both sides confirm nothing changed in between. This skill does the same for code: it says the code again in plain words, then proves the behavior is identical.

Status: in development. Progress is tracked in [tasks/todo.md](tasks/todo.md).

## How a run works

1. Scope one module and map its public surface, callers and side effects
2. Audit it against [the signs catalog](skills/readback/references/signs.md) and decide how much to change
3. Lock the behavior with tests at the public boundary, and prove the tests can fail
4. Rewrite in ordered passes, one commit each, with the locked tests run after every pass
5. Report what changed, the proof, and any bugs found and left untouched

## Languages

Java, TypeScript and shell in the first version.
