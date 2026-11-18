# Behavior checks. Each one runs against the code as it is on disk and reports pass or fail with a reason.
import subprocess
import sys
import time
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from readback_toolkit.run_config import ReadbackError, RunConfig
from readback_toolkit.scenarios import describe_recording_differences, record_all_scenarios

SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1]
DEFAULT_COMMAND_TIMEOUT_SECONDS = 900
ORIGINALS_DIRECTORY_NAME = "original"


@dataclass
class CheckResult:
    check_name: str
    is_passed: bool
    detail: str
    measurements: dict[str, Any] = field(default_factory=dict)


def run_shell_command(run_config: RunConfig, command: str, timeout_seconds: float) -> tuple[int | str, str, float]:
    started_at = time.monotonic()
    try:
        completed = subprocess.run(command, shell=True, cwd=run_config.project_root, capture_output=True,
                                   text=True, timeout=timeout_seconds)
        return completed.returncode, (completed.stdout + completed.stderr)[-2000:], time.monotonic() - started_at
    except subprocess.TimeoutExpired:
        return "timeout", f"no result after {timeout_seconds:.0f}s", time.monotonic() - started_at


def run_compile_check(run_config: RunConfig, timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> CheckResult | None:
    compile_command = run_config.checks.get("compile")
    if not compile_command:
        return None
    exit_code, output_tail, _ = run_shell_command(run_config, run_config.command_with_targets(compile_command), timeout_seconds)
    return CheckResult("compile", 0 == exit_code, "compiles" if 0 == exit_code else f"exit {exit_code}: {output_tail[-400:]}")


def count_junit_results(project_root: Path, report_pattern: str) -> dict[str, int]:
    test_counts = {"tests": 0, "failed": 0, "skipped": 0}
    # Reports usually live in build folders, which expand_globs skips on purpose, so glob directly.
    for report_path in sorted(project_root.glob(report_pattern)):
        for test_case in element_tree.parse(report_path).iter("testcase"):
            test_counts["tests"] += 1
            if None is not test_case.find("failure") or None is not test_case.find("error"):
                test_counts["failed"] += 1
            if None is not test_case.find("skipped"):
                test_counts["skipped"] += 1
    return test_counts


def remove_stale_reports(project_root: Path, report_pattern: str) -> None:
    for stale_report in project_root.glob(report_pattern):
        stale_report.unlink()


def run_test_check(run_config: RunConfig, baseline_test_count: int | None,
                   timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> CheckResult | None:
    test_settings = run_config.checks.get("tests")
    if not test_settings:
        return None
    report_pattern = test_settings["junit"]
    remove_stale_reports(run_config.project_root, report_pattern)
    exit_code, output_tail, duration = run_shell_command(run_config, run_config.command_with_targets(test_settings["command"]), timeout_seconds)
    test_counts = count_junit_results(run_config.project_root, report_pattern)
    measurements = {**test_counts, "seconds": round(duration, 2)}
    # A skipped test is counted as a failure: skipping is the cheapest way to make a lock go quiet.
    if 0 != exit_code or 0 < test_counts["failed"] or 0 < test_counts["skipped"]:
        return CheckResult("tests", False, f"exit {exit_code}, {test_counts['failed']} failed, {test_counts['skipped']} skipped: {output_tail[-400:]}", measurements)
    if 0 == test_counts["tests"]:
        return CheckResult("tests", False, f"no test results found at {report_pattern}", measurements)
    if None is not baseline_test_count and test_counts["tests"] < baseline_test_count:
        return CheckResult("tests", False, f"{test_counts['tests']} tests ran, lock has {baseline_test_count}", measurements)
    return CheckResult("tests", True, f"{test_counts['tests']} passed", measurements)


def run_scenario_check(run_config: RunConfig, baseline_recordings: dict[str, Any] | None) -> CheckResult | None:
    scenario_file = run_config.checks.get("scenarios")
    if not scenario_file:
        return None
    started_at = time.monotonic()
    current_recordings = record_all_scenarios(run_config.project_root, scenario_file)
    measurements = {"scenarios": len(current_recordings), "seconds": round(time.monotonic() - started_at, 2), "recordings": current_recordings}
    if None is baseline_recordings:
        return CheckResult("scenarios", True, f"{len(current_recordings)} recorded", measurements)
    differences = describe_recording_differences(baseline_recordings, current_recordings)
    identical_count = len(baseline_recordings) - len({difference.split(".")[0].split(":")[0] for difference in differences})
    if 0 < len(differences):
        return CheckResult("scenarios", False, f"{identical_count} of {len(baseline_recordings)} identical; {'; '.join(differences[:5])}", measurements)
    return CheckResult("scenarios", True, f"{len(current_recordings)} of {len(current_recordings)} identical", measurements)


def original_copy_path(run_config: RunConfig, relative_path: str) -> Path:
    return run_config.state_directory / ORIGINALS_DIRECTORY_NAME / relative_path


def run_pipeline_check(run_config: RunConfig) -> CheckResult | None:
    pipeline_file = run_config.checks.get("pipeline")
    if not pipeline_file:
        return None
    original_pipeline = original_copy_path(run_config, pipeline_file)
    if not original_pipeline.exists():
        raise ReadbackError(f"no original copy of {pipeline_file}; run `readback lock` first")
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS_DIRECTORY / "lock_pipeline.py"), "compare", str(original_pipeline), pipeline_file, "--show", "3"],
        cwd=run_config.project_root, capture_output=True, text=True,
    )
    summary_lines = [line for line in completed.stdout.splitlines() if line.startswith(("Trigger matrix", "Scenarios identical", "  DIFF", "Pipeline level"))]
    return CheckResult("pipeline", 0 == completed.returncode, "; ".join(summary_lines) or completed.stderr.strip()[-400:])


def run_behavior_checks(run_config: RunConfig, lock_state: dict[str, Any] | None,
                        test_timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> list[CheckResult]:
    baseline_test_count = None if None is lock_state else lock_state["tests"]["tests"]
    baseline_recordings = None if None is lock_state else lock_state["scenarios"]
    check_results = [
        run_test_check(run_config, baseline_test_count, test_timeout_seconds),
        run_scenario_check(run_config, baseline_recordings),
        run_pipeline_check(run_config),
    ]
    return [check_result for check_result in check_results if None is not check_result]
