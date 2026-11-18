#!/usr/bin/env python3
# Lock evals: for each fixture, lock the original, measure the lock with mutants, prove the reference rewrite holds,
# and prove every planted bad refactor breaks the lock.
# usage: python3 evals/run-lock-evals.py [fixture ...] [--mutants 60] [--skip-mutants]
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
READBACK_CLI = REPO_ROOT / "skills" / "readback" / "scripts" / "readback.py"
LOCKS_DIRECTORY = REPO_ROOT / "evals" / "locks"
REWRITES_DIRECTORY = REPO_ROOT / "evals" / "rewrites"
BAD_REFACTORS_DIRECTORY = REPO_ROOT / "evals" / "bad-refactors"
FIXTURE_DIRECTORIES = (REPO_ROOT / "examples", REPO_ROOT / "evals" / "fixtures")
LINKED_DEPENDENCY_DIRECTORIES = ("node_modules",)
IGNORED_WHEN_COPYING = shutil.ignore_patterns("node_modules", "target", "__pycache__", ".readback", "answer-key.json")


def find_fixture(fixture_name: str) -> Path:
    for fixtures_directory in FIXTURE_DIRECTORIES:
        if (fixtures_directory / fixture_name).is_dir():
            return fixtures_directory / fixture_name
    raise SystemExit(f"no fixture named {fixture_name}")


def run_readback(work_directory: Path, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(READBACK_CLI), "--root", str(work_directory), *arguments],
                          capture_output=True, text=True)


def overlay_directory(source_directory: Path, work_directory: Path, skipped_names: set[str]) -> None:
    for source_path in source_directory.rglob("*"):
        relative_path = source_path.relative_to(source_directory)
        if source_path.is_dir() or relative_path.name in skipped_names:
            continue
        (work_directory / relative_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, work_directory / relative_path)


def apply_rewrite(fixture_name: str, work_directory: Path) -> None:
    rewrite_directory = REWRITES_DIRECTORY / fixture_name
    overlay_directory(rewrite_directory, work_directory, skipped_names={"deleted.txt"})
    deleted_list = rewrite_directory / "deleted.txt"
    if deleted_list.exists():
        for deleted_path in deleted_list.read_text().split():
            (work_directory / deleted_path).unlink()


def edits_of(bad_refactor: dict) -> list[dict]:
    return bad_refactor.get("edits") or [{key: bad_refactor[key] for key in ("file", "find", "replace")}]


def is_bad_refactor_caught(work_directory: Path, bad_refactor: dict) -> tuple[bool, str]:
    saved_contents = {}
    try:
        for edit in edits_of(bad_refactor):
            edited_path = work_directory / edit["file"]
            saved_contents.setdefault(edited_path, edited_path.read_text())
            current_text = edited_path.read_text()
            if 1 != current_text.count(edit["find"]):
                raise SystemExit(f"bad refactor {bad_refactor['name']!r}: find text matches {current_text.count(edit['find'])} times")
            edited_path.write_text(current_text.replace(edit["find"], edit["replace"]))
        verification = run_readback(work_directory, "verify")
        failed_checks = [line.split()[1] for line in verification.stdout.splitlines() if line.startswith("  FAIL  ")]
        return 1 == verification.returncode, ", ".join(failed_checks)
    finally:
        for edited_path, original_text in saved_contents.items():
            edited_path.write_text(original_text)


def evaluate_fixture(fixture_name: str, mutant_count: int) -> dict:
    fixture_directory = find_fixture(fixture_name)
    lock_directory = LOCKS_DIRECTORY / fixture_name
    with tempfile.TemporaryDirectory(prefix=f"readback-eval-{fixture_name}-") as work_text:
        work_directory = Path(work_text) / fixture_name
        shutil.copytree(fixture_directory, work_directory, ignore=IGNORED_WHEN_COPYING)
        for dependency_directory in LINKED_DEPENDENCY_DIRECTORIES:
            if (fixture_directory / dependency_directory).exists():
                (work_directory / dependency_directory).symlink_to(fixture_directory / dependency_directory)
        overlay_directory(lock_directory, work_directory, skipped_names={"config.json"})
        (work_directory / ".readback").mkdir()
        shutil.copy2(lock_directory / "config.json", work_directory / ".readback" / "config.json")

        lock_run = run_readback(work_directory, "lock")
        if 0 != lock_run.returncode:
            return {"fixture": fixture_name, "error": f"lock failed:\n{lock_run.stdout}{lock_run.stderr}"}
        mutation_summary = "skipped"
        if 0 < mutant_count:
            run_readback(work_directory, "mutate", "--max", str(mutant_count))
            mutation = json.loads((work_directory / ".readback" / "mutation.json").read_text())
            mutation_summary = f"{mutation['killed']}/{mutation['killed'] + mutation['survived']} killed"

        apply_rewrite(fixture_name, work_directory)
        rewrite_run = run_readback(work_directory, "verify")
        bad_refactors = json.loads((BAD_REFACTORS_DIRECTORY / f"{fixture_name}.json").read_text())
        bad_refactor_results = [(bad_refactor["name"], *is_bad_refactor_caught(work_directory, bad_refactor)) for bad_refactor in bad_refactors]
        return {
            "fixture": fixture_name,
            "lock": lock_run.stdout.strip().splitlines()[-1],
            "mutants": mutation_summary,
            "rewrite": "LOCK HELD" if 0 == rewrite_run.returncode else f"LOCK BROKEN\n{rewrite_run.stdout}",
            "bad_refactors": bad_refactor_results,
        }


def main() -> int:
    argument_parser = argparse.ArgumentParser(description="Run the readback lock evals.")
    argument_parser.add_argument("fixtures", nargs="*", help="defaults to every fixture with a lock")
    argument_parser.add_argument("--mutants", type=int, default=60, help="mutants per fixture, 0 to skip")
    arguments = argument_parser.parse_args()
    fixture_names = arguments.fixtures or sorted(lock_path.name for lock_path in LOCKS_DIRECTORY.iterdir() if lock_path.is_dir())
    is_every_expectation_met = True
    for fixture_name in fixture_names:
        result = evaluate_fixture(fixture_name, arguments.mutants)
        print(f"== {fixture_name}")
        if "error" in result:
            print(f"  ERROR {result['error']}")
            is_every_expectation_met = False
            continue
        caught_count = sum(1 for _, is_caught, _ in result["bad_refactors"] if is_caught)
        print(f"  lock          {result['lock']}")
        print(f"  mutants       {result['mutants']}")
        print(f"  rewrite       {result['rewrite']}")
        print(f"  bad refactors {caught_count} of {len(result['bad_refactors'])} caught")
        for refactor_name, is_caught, failed_checks in result["bad_refactors"]:
            print(f"    {'caught' if is_caught else 'MISSED'}  {refactor_name}{f'  ({failed_checks})' if is_caught else ''}")
        if "LOCK HELD" != result["rewrite"] or caught_count != len(result["bad_refactors"]):
            is_every_expectation_met = False
    print("ALL EXPECTATIONS MET" if is_every_expectation_met else "EXPECTATIONS NOT MET")
    return 0 if is_every_expectation_met else 1


if __name__ == "__main__":
    sys.exit(main())
