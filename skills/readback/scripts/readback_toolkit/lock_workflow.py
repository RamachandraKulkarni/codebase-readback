# The three commands that make up the proof: lock the current behavior, verify a rewrite against it,
# and mutate the code to measure whether the lock would notice a real change.
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from readback_toolkit.checks import (CheckResult, original_copy_path, run_behavior_checks, run_compile_check,
                                     run_shell_command)
from readback_toolkit.code_mask import LexicalRules
from readback_toolkit.mutants import Mutant, find_mutants, pick_evenly
from readback_toolkit.run_config import ReadbackError, RunConfig, expand_globs
from readback_toolkit.surface import extract_surface

LOCK_FILE_NAME = "lock.json"
PROOF_FILE_NAME = "proof.json"
MUTATION_FILE_NAME = "mutation.json"
MINIMUM_MUTANT_TIMEOUT_SECONDS = 60
MUTANT_TIMEOUT_MULTIPLIER = 4


def hash_file(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def frozen_paths(run_config: RunConfig) -> list[str]:
    frozen_patterns = list(run_config.settings.get("frozen", []))
    scenario_file = run_config.checks.get("scenarios")
    if scenario_file:
        frozen_patterns.append(scenario_file)
    target_paths = set(run_config.target_paths)
    return [path for path in expand_globs(run_config.project_root, frozen_patterns) if path not in target_paths]


def hash_paths(project_root: Path, relative_paths: list[str]) -> dict[str, str]:
    return {relative_path: hash_file(project_root / relative_path) for relative_path in relative_paths}


def print_check_results(check_results: list[CheckResult]) -> None:
    for check_result in check_results:
        one_line_detail = " | ".join(line.strip() for line in check_result.detail.splitlines() if line.strip())
        print(f"  {'PASS' if check_result.is_passed else 'FAIL'}  {check_result.check_name:<10} {one_line_detail}")


def lock_behavior(run_config: RunConfig) -> int:
    lock_path = run_config.state_directory / LOCK_FILE_NAME
    if lock_path.exists():
        raise ReadbackError(f"{lock_path} exists. A lock is accepted once; delete it only with a reason in the ledger")
    has_behavior_check = any(run_config.checks.get(check_name) for check_name in ("tests", "scenarios", "pipeline"))
    if not has_behavior_check:
        raise ReadbackError("nothing locks behavior: configure checks.tests, checks.scenarios or checks.pipeline")
    # A rewrite may delete a target file, so only the lock insists that every target exists.
    missing_targets = [pattern for pattern in run_config.settings["targets"] if 0 == len(expand_globs(run_config.project_root, [pattern]))]
    if 0 < len(missing_targets):
        raise ReadbackError(f"targets match no files: {missing_targets}")
    locked_frozen_paths = frozen_paths(run_config)
    if run_config.checks.get("tests") and 0 == len(locked_frozen_paths):
        raise ReadbackError("checks.tests is set but \"frozen\" matches no test files; the tests must be frozen")

    copy_originals(run_config)
    check_results = [check_result for check_result in [run_compile_check(run_config)] if None is not check_result]
    surface_lines = extract_surface(run_config)
    check_results.extend(run_behavior_checks(run_config, lock_state=None))
    print(f"Lock {run_config.project_root.name} ({run_config.adapter_name})")
    print_check_results(check_results)
    if not all(check_result.is_passed for check_result in check_results):
        print("NOT LOCKED: the code must pass every check before its behavior can be locked")
        return 1

    measurements_by_check = {check_result.check_name: check_result.measurements for check_result in check_results}
    lock_state = {
        "created": now_text(),
        "adapter": run_config.adapter_name,
        "config_sha256": hash_file(run_config.config_path),
        "targets": hash_paths(run_config.project_root, run_config.target_paths),
        "frozen": hash_paths(run_config.project_root, locked_frozen_paths),
        "surface": surface_lines,
        "tests": {"tests": measurements_by_check.get("tests", {}).get("tests", 0),
                  "seconds": measurements_by_check.get("tests", {}).get("seconds", 0)},
        "scenarios": measurements_by_check.get("scenarios", {}).get("recordings"),
    }
    lock_path.write_text(json.dumps(lock_state, indent=2) + "\n")
    print(f"LOCKED  {len(lock_state['targets'])} target files, {len(lock_state['frozen'])} frozen files, "
          f"{len(surface_lines)} surface lines, {lock_state['tests']['tests']} tests, "
          f"{len(lock_state['scenarios'] or {})} scenarios")
    return 0


def copy_originals(run_config: RunConfig) -> None:
    pipeline_file = run_config.checks.get("pipeline")
    for relative_path in run_config.target_paths + ([pipeline_file] if pipeline_file else []):
        destination_path = original_copy_path(run_config, relative_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(run_config.project_root / relative_path, destination_path)


def load_lock_state(run_config: RunConfig) -> dict[str, Any]:
    lock_path = run_config.state_directory / LOCK_FILE_NAME
    if not lock_path.exists():
        raise ReadbackError("no lock; run `readback lock` on the original code first")
    return json.loads(lock_path.read_text())


def check_frozen_files(run_config: RunConfig, lock_state: dict[str, Any]) -> CheckResult:
    problems = []
    if hash_file(run_config.config_path) != lock_state["config_sha256"]:
        problems.append("config.json changed after the lock")
    for relative_path, locked_hash in lock_state["frozen"].items():
        current_path = run_config.project_root / relative_path
        if not current_path.exists():
            problems.append(f"{relative_path} deleted")
        elif hash_file(current_path) != locked_hash:
            problems.append(f"{relative_path} changed")
    added_paths = sorted(set(frozen_paths(run_config)) - lock_state["frozen"].keys())
    detail = "; ".join(problems) if problems else f"{len(lock_state['frozen'])} unchanged"
    if added_paths:
        detail += f"; {len(added_paths)} added: {', '.join(added_paths[:3])}"
    return CheckResult("frozen", 0 == len(problems), detail)


def check_surface(run_config: RunConfig, lock_state: dict[str, Any]) -> CheckResult:
    if "none" == run_config.settings.get("surface", {}).get("extractor", "none"):
        return CheckResult("surface", True, "locked by behavior checks for this adapter")
    current_surface = extract_surface(run_config)
    removed_lines = sorted(set(lock_state["surface"]) - set(current_surface))
    added_lines = sorted(set(current_surface) - set(lock_state["surface"]))
    if 0 == len(removed_lines) and 0 == len(added_lines):
        return CheckResult("surface", True, f"{len(current_surface)} lines identical")
    changes = [f"- {line}" for line in removed_lines[:4]] + [f"+ {line}" for line in added_lines[:4]]
    return CheckResult("surface", False, f"{len(removed_lines)} removed, {len(added_lines)} added: {' | '.join(changes)}")


def verify_against_lock(run_config: RunConfig) -> int:
    lock_state = load_lock_state(run_config)
    check_results = [check_frozen_files(run_config, lock_state)]
    compile_result = run_compile_check(run_config)
    if None is not compile_result:
        check_results.append(compile_result)
    check_results.append(check_surface(run_config, lock_state))
    check_results.extend(run_behavior_checks(run_config, lock_state))
    is_behavior_preserved = all(check_result.is_passed for check_result in check_results)
    current_target_hashes = hash_paths(run_config.project_root, [p for p in lock_state["targets"] if (run_config.project_root / p).exists()])
    proof = {
        "verdict": "LOCK HELD" if is_behavior_preserved else "LOCK BROKEN",
        "verified": now_text(),
        "lock": {key: lock_state[key] for key in ("created", "adapter", "config_sha256")},
        "checks": [{"check": result.check_name, "passed": result.is_passed, "detail": result.detail} for result in check_results],
        "targets": {path: {"locked": locked_hash, "current": current_target_hashes.get(path, "deleted")}
                    for path, locked_hash in lock_state["targets"].items()},
    }
    (run_config.state_directory / PROOF_FILE_NAME).write_text(json.dumps(proof, indent=2) + "\n")
    changed_target_count = sum(1 for hashes in proof["targets"].values() if hashes["locked"] != hashes["current"])
    print(f"Verify {run_config.project_root.name} ({run_config.adapter_name}), {changed_target_count} of {len(proof['targets'])} targets changed")
    print_check_results(check_results)
    print(proof["verdict"])
    return 0 if is_behavior_preserved else 1


def lexical_rules_of(mutation_settings: dict[str, Any]) -> LexicalRules:
    return LexicalRules(
        line_comment_markers=tuple(mutation_settings["line_comments"]),
        block_comment_pairs=tuple(tuple(pair) for pair in mutation_settings["block_comments"]),
        string_quotes=tuple(mutation_settings["quotes"]),
        comment_needs_word_boundary=mutation_settings["comment_word_boundary"],
        backslash_escapes_in_single_quotes=mutation_settings["single_quote_escapes"],
    )


def collect_mutants(run_config: RunConfig, file_filter: str | None) -> list[Mutant]:
    mutation_settings = run_config.settings["mutation"]
    lexical_rules = lexical_rules_of(mutation_settings)
    mutants = []
    for target_path in run_config.target_paths:
        if None is not file_filter and file_filter not in target_path:
            continue
        mutants.extend(find_mutants(
            target_path, (run_config.project_root / target_path).read_text(), lexical_rules,
            mutation_settings["operators"], mutation_settings.get("deletable_line"), mutation_settings.get("deleted_line", ""),
        ))
    return mutants


def run_one_mutant(run_config: RunConfig, lock_state: dict[str, Any], mutant: Mutant, timeout_seconds: float) -> str:
    target_file = run_config.project_root / mutant.file_path
    original_text = target_file.read_text()
    try:
        target_file.write_text(mutant.apply_to(original_text))
        compile_result = run_compile_check(run_config, timeout_seconds)
        if None is not compile_result and not compile_result.is_passed:
            return "invalid"
        check_results = run_behavior_checks(run_config, lock_state, timeout_seconds)
        return "survived" if all(check_result.is_passed for check_result in check_results) else "killed"
    finally:
        target_file.write_text(original_text)


def mutate_targets(run_config: RunConfig, maximum_mutants: int, file_filter: str | None, is_listing_only: bool) -> int:
    lock_state = load_lock_state(run_config)
    all_mutants = collect_mutants(run_config, file_filter)
    selected_mutants = pick_evenly(all_mutants, maximum_mutants)
    print(f"Mutants: {len(all_mutants)} found, {len(selected_mutants)} selected")
    if is_listing_only:
        for mutant in selected_mutants:
            print(f"  {mutant.file_path}:{mutant.line_number}  {mutant.description}")
        return 0
    timeout_seconds = max(MINIMUM_MUTANT_TIMEOUT_SECONDS, MUTANT_TIMEOUT_MULTIPLIER * lock_state["tests"]["seconds"])
    started_at = time.monotonic()
    outcomes = []
    for mutant_index, mutant in enumerate(selected_mutants, start=1):
        outcome = run_one_mutant(run_config, lock_state, mutant, timeout_seconds)
        outcomes.append({"file": mutant.file_path, "line": mutant.line_number, "mutation": mutant.description,
                         "replacement": mutant.replacement, "outcome": outcome})
        print(f"  [{mutant_index}/{len(selected_mutants)}] {outcome:<8} {mutant.file_path}:{mutant.line_number}  {mutant.description}", flush=True)
    killed_count = sum(1 for outcome in outcomes if "killed" == outcome["outcome"])
    survived = [outcome for outcome in outcomes if "survived" == outcome["outcome"]]
    invalid_count = len(outcomes) - killed_count - len(survived)
    valid_count = killed_count + len(survived)
    score = 0.0 if 0 == valid_count else killed_count / valid_count
    (run_config.state_directory / MUTATION_FILE_NAME).write_text(json.dumps({
        "run": now_text(), "found": len(all_mutants), "selected": len(selected_mutants),
        "killed": killed_count, "survived": len(survived), "invalid": invalid_count,
        "score": round(score, 3), "outcomes": outcomes,
    }, indent=2) + "\n")
    print(f"Killed {killed_count} of {valid_count} valid mutants ({score:.0%}), {invalid_count} did not compile, "
          f"{time.monotonic() - started_at:.0f}s")
    for surviving_mutant in survived:
        print(f"  SURVIVED {surviving_mutant['file']}:{surviving_mutant['line']}  {surviving_mutant['mutation']}")
    return 0


def run_native_mutation(run_config: RunConfig) -> int:
    native_command = run_config.settings["mutation"].get("native_command")
    if not native_command:
        raise ReadbackError(f"the {run_config.adapter_name} adapter declares no native mutation tool")
    exit_code, output_tail, _ = run_shell_command(run_config, native_command, timeout_seconds=7200)
    print(output_tail)
    return 0 if 0 == exit_code else 1
