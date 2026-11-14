# Ledger

## Decisions

- 2026-11-13 Goal: code a human can read, with proof the behavior did not change. Line count is not the measure
- 2026-11-13 Languages for v1: Java, TypeScript, shell
- 2026-11-13 Name: readback. Repo codebase-readback, command /readback
- 2026-11-13 Scope of a run: one module, not a whole codebase
- 2026-11-13 The lock is tooling, not instructions: recorded behavior, frozen test hash, public surface diff, mutation runs
- 2026-11-13 Tests are frozen once the lock is accepted. A red run reverts the pass
- 2026-11-13 Bugs found during a run are pinned and reported, never fixed in the same run
- 2026-11-13 Defaults: mutation score 80% on the target or every survivor explained, Vitest and JUnit 5 as primary runners
- 2026-11-13 Ideas borrowed from caldoai/untangle-codebase and lookalikes are rewritten in our own words
- 2026-11-13 Commits are authored as Ram, with no AI attribution
- 2026-11-13 Target is enterprise grade: a reviewer who distrusts the agent can still trust the result
- 2026-11-13 License: Apache-2.0
- 2026-11-13 The guarantee is stated exactly: identical on the locked behaviors, lock strength measured by mutation score. Performance and concurrency are outside it
- 2026-11-13 Not building: dashboards, a hosted service, multi-agent orchestration, auto-merge

## Milestones

- [ ] 1. Signs catalog and deliberately sloppy examples with answer keys
  - [x] references/signs.md first draft
  - [ ] signs.md reviewed by Ram
  - [x] examples/typescript-order-pricing, 27 key entries
  - [x] examples/java-csv-import, 26 key entries
  - [x] examples/shell-publish-build, 18 key entries, written fresh
  - [x] evals/check-answer-keys.mjs
  - [ ] Build files for the Java and TypeScript examples, added with the lock toolkit
- [ ] 2. Lock toolkit: surface, freeze, record, gate, with TypeScript, Java and shell adapters
  - [ ] Surface diff from the compiler: tsc declarations, javap
  - [ ] Old versus new on generated inputs for pure functions
  - [ ] Recorded behavior for code with I/O
  - [ ] Baseline parity: compile, typecheck, lint, test count, skipped counts as red
- [ ] 3. Proof manifest readback.json, verify command, GitHub Action that rechecks without the agent
- [ ] 4. Policy file .readback.yml, enforced by the scripts
- [ ] 5. SKILL.md run flow with resumable state in .readback/
- [ ] 6. Evals: audit accuracy against the answer keys, and catch rate on planted bad refactors
- [ ] 7. Packaging: plugin manifest, versioning, changelog, SECURITY.md, docs

## Open questions

- Review flow: pull requests per milestone, or direct merges to main

## Findings from the shell trial

- Readable was longer: 173 lines became 273. The script was dense, not bloated
- The script triaged as light. The skill must be able to say "little to do" and stop
- A scenario recorder with stubbed commands locked a shell script: 30 scenarios identical, 20 of 20 deliberate breaks caught
- One deliberate break survived the first run and exposed a missing scenario. Mutation is what found the hole
- The trial script belongs to a work codebase and must not be committed here
