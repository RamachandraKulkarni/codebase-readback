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
- 2026-11-18 Scope widened to any language. The method is universal; the proof is tiered (A surface, B behavior, C lock strength) and every report states what it reached
- 2026-11-18 One Python toolkit (standard library, plus tree-sitter for the generic surface and PyYAML for GitLab CI). Languages are JSON adapters over it
- 2026-11-18 Adapters in v1: typescript, java, python, shell, gitlab-ci, generic
- 2026-11-18 The built-in mutator is the default for every language, so scores compare across languages. Native tools (Stryker, PIT, mutmut) run with `mutate --native`
- 2026-11-18 Characterization goes through the public surface only, and every expected value is recorded by running the original
- 2026-11-18 The lock may be rebuilt while cases are added; once the first rewrite pass starts it never changes
- 2026-11-18 pipeline-readback is folded in as the gitlab-ci adapter. Its trigger matrix now adds an unlisted value per variable

## Milestones

- [ ] 1. Signs catalog and deliberately sloppy examples with answer keys
  - [x] references/signs.md first draft
  - [ ] signs.md reviewed by Ram
  - [x] examples/typescript-order-pricing, 27 key entries
  - [x] examples/java-csv-import, 26 key entries
  - [x] examples/shell-publish-build, 18 key entries, written fresh
  - [x] evals/check-answer-keys.mjs
  - [x] Build files for the Java and TypeScript examples (pom.xml not run yet: Maven Central was unreachable from the build sandbox)
  - [x] examples/python-invoice-reminders, 23 key entries
  - [x] examples/gitlab-ci-release, 12 key entries
- [ ] 2. Lock toolkit: surface, freeze, record, gate
  - [x] Surface: TypeScript compiler API, javap, Python ast, tree-sitter
  - [ ] Old versus new on generated inputs for pure functions
  - [x] Recorded behavior for code with I/O: scenario recorder with stubbed commands
  - [x] Baseline parity: compile, test count, skipped counts as red, frozen tests and config
  - [ ] Lint parity
  - [x] Built-in mutator with survivors reported by file:line
- [ ] 3. Proof manifest, verify command, GitHub Action that rechecks without the agent
  - [x] `readback verify` writes .readback/proof.json
  - [ ] GitHub Action
- [ ] 4. Policy file .readback.yml, enforced by the scripts
- [x] 5. SKILL.md run flow, with state in .readback/
- [ ] 6. Evals: audit accuracy against the answer keys, and catch rate on planted bad refactors
  - [x] evals/run-lock-evals.py: lock, mutants, reference rewrite, planted bad refactors, for 6 fixtures
  - [ ] Audit accuracy scored by an agent that has not seen the answer keys
- [ ] 7. Packaging: plugin manifest, versioning, changelog, SECURITY.md, docs

## Open questions

- Review flow: pull requests per milestone, or direct merges to main
- Java eval runs on scenarios through javac; the JUnit path through Maven still needs a run where Maven Central is reachable

## Findings from the shell trial

- Readable was longer: 173 lines became 273. The script was dense, not bloated
- The script triaged as light. The skill must be able to say "little to do" and stop
- A scenario recorder with stubbed commands locked a shell script: 30 scenarios identical, 20 of 20 deliberate breaks caught
- One deliberate break survived the first run and exposed a missing scenario. Mutation is what found the hole
- The trial script belongs to a work codebase and must not be committed here

## Findings from the v1 lock evals (2026-11-18)

- First pass caught 31 of 36 planted bad refactors. All five misses were input classes, not operators: non-ASCII letters, control characters and Unicode spaces, a value past a 40-character cut, two special cases at once, amounts with thousands. Mutants did not reveal any of them. Fixed with cases, and the edge-class checklist in references/lock.md
- Surviving mutants found real gaps too: a header-only CSV, a demo entry point outside the lock, arguments in another order, letters at the ends of the alphabet, a top count of one
- The first Python lock imported an internal class, which would have frozen the structure the rewrite removes. Characterization now goes through the surface only
- A value worked out by hand was wrong (half-to-even rounding). Expected values are recorded by running the code
- The pipeline lock never exercised `!= ""` rules: the trigger matrix only held literals and unset. An unlisted value per variable fixed it; a real 23-job pipeline went from 624 to 1512 scenarios and its rewrite still held
- New bugs surfaced and pinned, not fixed: Java drops a first data row that starts with "email"; TypeScript never validates couponPercent; Python puts a late fee on Springfield's gentle reminders
