# Records what a program does at its process boundary: exit code, output, files written, and every
# call it makes to stubbed commands. Works for any language that runs as a command.
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from readback_toolkit.run_config import ReadbackError

STUB_DIRECTORY_NAME = ".readback-stubs"
CALL_LOG_FILE_NAME = ".readback-calls.jsonl"
SANDBOX_PLACEHOLDER = "<sandbox>"
DEFAULT_SCENARIO_TIMEOUT_SECONDS = 30

# Each stub logs its call, then answers from the scripted responses in order, repeating the last.
STUB_PROGRAM_TEMPLATE = """#!{python}
import json, os, sys
stub_name = {stub_name!r}
responses = {responses!r}
reads_stdin = {reads_stdin!r}
call_log_path = os.environ["READBACK_CALL_LOG"]
counter_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), stub_name + ".count")
call_index = int(open(counter_path).read()) if os.path.exists(counter_path) else 0
open(counter_path, "w").write(str(call_index + 1))
call_record = {{"command": stub_name, "args": sys.argv[1:]}}
if reads_stdin:
    call_record["stdin"] = sys.stdin.read()
with open(call_log_path, "a") as call_log:
    call_log.write(json.dumps(call_record) + "\\n")
response = responses[min(call_index, len(responses) - 1)] if responses else {{}}
sys.stdout.write(response.get("stdout", ""))
sys.stderr.write(response.get("stderr", ""))
sys.exit(response.get("exit", 0))
"""


def load_scenario_suite(project_root: Path, scenario_file: str) -> dict[str, Any]:
    scenario_path = project_root / scenario_file
    if not scenario_path.exists():
        raise ReadbackError(f"no scenario file {scenario_file}")
    scenario_suite = json.loads(scenario_path.read_text())
    scenario_names = [scenario["name"] for scenario in scenario_suite["scenarios"]]
    if len(scenario_names) != len(set(scenario_names)):
        raise ReadbackError(f"{scenario_file}: scenario names must be unique")
    return scenario_suite


def record_all_scenarios(project_root: Path, scenario_file: str) -> dict[str, dict[str, Any]]:
    scenario_suite = load_scenario_suite(project_root, scenario_file)
    return {
        scenario["name"]: record_scenario(project_root, scenario_suite, scenario)
        for scenario in scenario_suite["scenarios"]
    }


def record_scenario(project_root: Path, scenario_suite: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="readback-") as sandbox_text:
        sandbox = Path(sandbox_text)
        copy_into_sandbox(project_root, sandbox, scenario_suite.get("copy", []))
        for relative_path, file_content in scenario.get("files", {}).items():
            (sandbox / relative_path).parent.mkdir(parents=True, exist_ok=True)
            (sandbox / relative_path).write_text(file_content)
        stub_directory = sandbox / STUB_DIRECTORY_NAME
        install_stubs(stub_directory, {**scenario_suite.get("stubs", {}), **scenario.get("stubs", {})})
        call_log_path = sandbox / CALL_LOG_FILE_NAME
        call_log_path.touch()
        hashes_before_run = hash_sandbox_files(sandbox)
        process_environment = {
            "PATH": f"{stub_directory}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(sandbox),
            "TMPDIR": str(sandbox),
            "TZ": "UTC",
            "LC_ALL": "C",
            "LANG": "C",
            "READBACK_CALL_LOG": str(call_log_path),
            **scenario_suite.get("env", {}),
            **scenario.get("env", {}),
        }
        command = scenario.get("command", scenario_suite["command"]) + scenario.get("args", [])
        try:
            completed = subprocess.run(
                command, cwd=sandbox, env=process_environment, input=scenario.get("stdin", ""),
                capture_output=True, text=True,
                timeout=scenario.get("timeout", DEFAULT_SCENARIO_TIMEOUT_SECONDS),
            )
            exit_code, stdout_text, stderr_text = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired:
            exit_code, stdout_text, stderr_text = "timeout", "", ""
        return {
            "exit": exit_code,
            "stdout": stdout_text.replace(str(sandbox), SANDBOX_PLACEHOLDER),
            "stderr": stderr_text.replace(str(sandbox), SANDBOX_PLACEHOLDER),
            "calls": read_call_log(call_log_path, sandbox),
            "files": describe_file_changes(hashes_before_run, hash_sandbox_files(sandbox)),
        }


def copy_into_sandbox(project_root: Path, sandbox: Path, relative_paths: list[str]) -> None:
    for relative_path in relative_paths:
        source_path = project_root / relative_path
        destination_path = sandbox / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(source_path, destination_path)
        else:
            shutil.copy2(source_path, destination_path)


def install_stubs(stub_directory: Path, stubs: dict[str, dict[str, Any]]) -> None:
    stub_directory.mkdir()
    for stub_name, stub_definition in stubs.items():
        stub_path = stub_directory / stub_name
        stub_path.write_text(STUB_PROGRAM_TEMPLATE.format(
            python=sys.executable, stub_name=stub_name,
            responses=stub_definition.get("responses", []),
            reads_stdin=stub_definition.get("reads_stdin", False),
        ))
        stub_path.chmod(0o755)


def read_call_log(call_log_path: Path, sandbox: Path) -> list[dict[str, Any]]:
    call_log_text = call_log_path.read_text().replace(str(sandbox), SANDBOX_PLACEHOLDER)
    return [json.loads(call_line) for call_line in call_log_text.splitlines() if call_line.strip()]


def hash_sandbox_files(sandbox: Path) -> dict[str, str]:
    file_hashes = {}
    for file_path in sorted(sandbox.rglob("*")):
        relative_path = file_path.relative_to(sandbox).as_posix()
        if not file_path.is_file() or relative_path.startswith(STUB_DIRECTORY_NAME) or CALL_LOG_FILE_NAME == relative_path:
            continue
        file_hashes[relative_path] = hashlib.sha256(file_path.read_bytes()).hexdigest()
    return file_hashes


def describe_file_changes(hashes_before_run: dict[str, str], hashes_after_run: dict[str, str]) -> dict[str, str]:
    # Only what the run created, changed or deleted; the copied program itself is expected to change.
    file_changes = {
        relative_path: file_hash for relative_path, file_hash in hashes_after_run.items()
        if hashes_before_run.get(relative_path) != file_hash
    }
    for deleted_path in hashes_before_run.keys() - hashes_after_run.keys():
        file_changes[deleted_path] = "deleted"
    return dict(sorted(file_changes.items()))


def describe_recording_differences(baseline: dict[str, dict[str, Any]], current: dict[str, dict[str, Any]]) -> list[str]:
    differences = []
    for scenario_name in sorted(baseline.keys() | current.keys()):
        baseline_recording = baseline.get(scenario_name)
        current_recording = current.get(scenario_name)
        if None is baseline_recording or None is current_recording:
            differences.append(f"{scenario_name}: {'added' if None is baseline_recording else 'missing'}")
            continue
        for field_name in ("exit", "stdout", "stderr", "calls", "files"):
            if baseline_recording[field_name] != current_recording[field_name]:
                differences.append(f"{scenario_name}.{field_name} differs")
    return differences
