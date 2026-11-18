# Adapters

An adapter is one JSON file in `adapters/` holding the defaults for a language: how to find the surface, how to compile and test, which files to freeze, and how to plant mutants. `.readback/config.json` is laid over it, key by key, so a project changes only what differs.

| Adapter | Surface | Default behavior check | Mutants |
|---|---|---|---|
| `typescript` | Compiler API: every export of `surface.entries` with its full type | `tsc --noEmit`, Vitest with a JUnit report | C-like operators, statement deletion |
| `java` | `javap -public` on freshly compiled `surface.sources`, limited to `surface.entries` classes | `mvn -q compile`, `mvn -q test` with Surefire reports | C-like operators, statement deletion |
| `python` | `ast`: functions with full signatures, classes, public members; `surface.names` or `__all__` choose what is public | `py_compile`, pytest with `--junitxml` | Python operators, statement replaced by `pass` |
| `shell` | None; the scenarios are the surface | `bash -n`, scenarios | Test operators, `&&` and `||`, exit codes, command deletion |
| `gitlab-ci` | None; the trigger matrix is the surface | Every job's rules evaluated for every trigger combination, compared with the original | Rule operators, script line deletion |
| `generic` | tree-sitter definitions in `surface.entries`, filtered by `surface.names` | None by default: set tests or scenarios | C-like operators |

## Config fields

```json
{
  "adapter": "python",
  "targets": ["reminders.py"],
  "frozen": ["tests/**"],
  "surface": {"extractor": "python", "entries": ["reminders.py"], "names": ["run", "format_csv"]},
  "checks": {
    "compile": "python3 -m py_compile {targets}",
    "tests": {"command": "python3 -m pytest -q --junitxml=.readback/junit/pytest.xml", "junit": ".readback/junit/*.xml"},
    "scenarios": "readback-test/scenarios.json",
    "pipeline": ".gitlab-ci.yml"
  },
  "mutation": {"operators": "python", "deletable_line": "...", "deleted_line": "pass"}
}
```

- `targets`: the files the run may rewrite. Globs. A target may be deleted by the rewrite.
- `frozen`: tests and fixtures the lock depends on. Hashed at lock time; any change breaks `verify`. New files that match are allowed and listed.
- `surface.extractor`: `typescript`, `java`, `python`, `tree-sitter` or `none`. `entries` are files (or Java class names); `names` limits the surface to declared public names; `language` names the tree-sitter grammar when the file extension does not.
- `checks.compile`: run before everything else and before every mutant. `{targets}` becomes the quoted target paths.
- `checks.tests`: the command and where its JUnit XML lands. Old reports are deleted before each run. A skipped test counts as a failure, and the test count may not drop below the lock's.
- `checks.scenarios`: a scenario file; see `lock.md`.
- `checks.pipeline`: a GitLab CI file, compared with the copy taken at lock time.
- `mutation.native_command`: the language's own mutation tool (Stryker, PIT, mutmut), run by `mutate --native`. The built-in mutator is the default so every language is measured the same way.

Set a check to `null` to switch off an adapter default; the Java eval does this to use scenarios instead of Maven.

## Adding a language

Start with `generic`: compile into `.readback/`, lock through scenarios at the process boundary, declare public names for the tree-sitter surface. That works for any language with a tree-sitter grammar and a command line. The Go eval in this repo is built that way.

Write a dedicated adapter when the language has a test runner with JUnit output, or a compiler that can print the public surface more exactly than tree-sitter. Copy the closest adapter file, change `detect`, `checks` and `mutation`, and add a fixture with a lock, a rewrite and planted bad refactors under `evals/`.
