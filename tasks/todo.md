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

## Milestones

- [ ] 1. Signs catalog and deliberately sloppy example modules
  - [x] references/signs.md first draft
  - [ ] signs.md reviewed by Ram
  - [ ] examples/ sloppy Java module
  - [ ] examples/ sloppy TypeScript module
  - [ ] examples/ sloppy shell script (written fresh, not taken from any work codebase)
- [ ] 2. Lock: references/lock.md and the gate scripts, TypeScript first, then Java, then shell
- [ ] 3. SKILL.md with the run flow and the passes
- [ ] 4. Evals on seeded fixtures: gate pass rate and readability change
- [ ] 5. Report script and README

## Open questions

- License. The repo was created without one. MIT was the suggestion

## Findings from the shell trial

- Readable was longer: 173 lines became 273. The script was dense, not bloated
- The script triaged as light. The skill must be able to say "little to do" and stop
- A scenario recorder with stubbed commands locked a shell script: 30 scenarios identical, 20 of 20 deliberate breaks caught
- One deliberate break survived the first run and exposed a missing scenario. Mutation is what found the hole
- The trial script belongs to a work codebase and must not be committed here
