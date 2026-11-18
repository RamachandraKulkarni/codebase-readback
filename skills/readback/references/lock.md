# The lock

The lock is what turns "I rewrote it carefully" into "here is the evidence." It records today's behavior before anything changes, and every later step is checked against that record by a script, not by the agent's judgment.

## Tiers

| Tier | Question it answers | How |
|---|---|---|
| A. Surface | Can callers still compile and call it the same way? | `surface`: TypeScript compiler API, `javap -public`, Python `ast`, tree-sitter for other languages |
| B. Behavior | Does it still do the same thing? | Frozen tests at the public boundary, recorded scenarios at the process boundary, or the trigger matrix for GitLab CI |
| C. Strength | Would the lock notice a real change? | `mutate`, and the edge-class checklist below |

A lock without tier C is a hope. Mutants answer how much of the code the lock can see; the checklist covers the changes mutants cannot model.

## Characterization rules

1. Test through the surface only. Import what callers import and run what callers run. A test that imports an internal class freezes the structure the rewrite is meant to change.
2. Record, never predict. Run the original and copy the value it returns. In this repo's own evals, a value worked out by hand was wrong (half-to-even rounding gave 82, not 83).
3. Name known bugs. `"known bug: a coupon over 100 percent gives zero tax"` tells the reviewer the strange expectation is deliberate.
4. Prefer many small cases to one large one. A scenario per input class makes a failure point at the class.
5. Pin side-effect order, not only results: record every call to a store, log, network or command, in order.
6. Freeze everything the lock depends on. Test files and scenario files go in `frozen`; `.readback/config.json` is frozen automatically.

## Edge-class checklist

Walk this for every input the module accepts. Each item caught a real gap in this repo's evals that operator mutants did not.

- **Boundaries:** each threshold, one below and one above, and zero.
- **Combinations of special cases:** two rules that both apply at once (a customer minimum and a coupon).
- **Text:** empty, whitespace only, control characters, Unicode spaces, non-ASCII letters, mixed case, leading and trailing spaces.
- **Length:** values longer than any cut-off, truncation or column width.
- **Numbers:** negative, fractional where integers are expected, large enough to need thousands separators.
- **Shape:** missing fields, `null` entries, extra fields, wrong types, values in a different order.
- **Arguments:** each option in a different position, a missing value, an unknown option, repeated options.
- **Failures of what it calls:** each dependency failing once, failing every time, and returning garbage.
- **State across calls:** calling twice, in the same process, and checking that the second result is as before.
- **Time and environment:** anything read from the clock, environment or locale is injected or stubbed, never live.

## Scenario files

For anything that runs as a command, in any language. Each scenario runs in a fresh sandbox with a minimal environment (`HOME` and `TMPDIR` in the sandbox, `TZ=UTC`, `LC_ALL=C`).

```json
{
  "command": ["bash", "publish-build.sh"],
  "copy": ["publish-build.sh"],
  "env": {"DEPLOY_API": "https://deploy.example.test/api"},
  "stubs": {"sleep": {}},
  "scenarios": [
    {
      "name": "published after one pending check",
      "args": ["--env", "staging", "--version", "1.4.0", "--artifact", "build.tar.gz"],
      "files": {"build.tar.gz": "hello\n"},
      "stdin": "",
      "stubs": {"curl": {"responses": [{"stdout": "{\"id\": \"b-42\"}"}, {"exit": 22, "stderr": "503"}]}}
    }
  ]
}
```

- `copy`: paths from the module root placed in the sandbox, such as the script or a build output folder.
- `stubs`: commands put first on `PATH`. Each call is logged with its arguments (and stdin with `"reads_stdin": true`), then answered from `responses` in order, the last one repeating.
- A scenario may set its own `command`, for example to run a second entry point.
- Recorded per scenario: exit code, stdout, stderr, every stub call, and every file the run created, changed or deleted. The sandbox path is replaced by `<sandbox>` so recordings compare across runs.

For a compiled language, compile into `.readback/` in the compile check and copy that folder into the sandbox. The Java and Go evals do this.

## Surviving mutants

`mutate` makes small edits outside strings and comments: flipped comparisons and boolean operators, changed arithmetic, integers plus one, dropped negations, deleted statements. Each is compiled first; one that does not compile is "invalid" and not scored. Every survivor gets one label in the plan:

- **Missing case:** the edit changes behavior and no case notices. Add the case, delete the lock, lock again.
- **Equivalent:** the edit cannot change behavior, for example rounding a value that is already an integer. Say why.
- **Unreachable:** nothing reaches the line through the surface. This supports deleting it; it does not prove it.

## What the lock cannot see

Performance, concurrency, timing, memory, and any input no case reaches. A lock built by scenarios also cannot see what a stub hides: the real service's behavior is not tested, only the calls made to it. Say which of these apply in the report.
