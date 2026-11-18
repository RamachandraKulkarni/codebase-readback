#!/usr/bin/env python3
# readback: lock a module's behavior, verify a rewrite against it, and measure the lock with mutants.
#   readback.py init --targets 'src/pricing.ts' [--adapter typescript]   write .readback/config.json
#   readback.py surface | scenarios                                       print what the lock will hold
#   readback.py lock                                                      accept the current behavior
#   readback.py verify                                                    exit 0 only if behavior is unchanged
#   readback.py mutate [--max 60] [--file name] [--list] [--native]      measure the lock
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from readback_toolkit.lock_workflow import lock_behavior, mutate_targets, run_native_mutation, verify_against_lock
from readback_toolkit.run_config import (ReadbackError, detect_adapter, list_adapter_names, load_run_config,
                                         write_initial_config)
from readback_toolkit.scenarios import record_all_scenarios
from readback_toolkit.surface import extract_surface


def build_argument_parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(prog="readback", description="Behavior lock for readability rewrites.")
    argument_parser.add_argument("--root", type=Path, default=Path.cwd(), help="module root holding .readback/")
    subcommands = argument_parser.add_subparsers(dest="command", required=True)
    init_command = subcommands.add_parser("init", help="write .readback/config.json from an adapter")
    init_command.add_argument("--targets", nargs="+", required=True, help="files or globs to rewrite")
    init_command.add_argument("--adapter", choices=list_adapter_names(), help="defaults to detection")
    subcommands.add_parser("surface", help="print the public surface")
    subcommands.add_parser("scenarios", help="run and print the recorded scenarios")
    subcommands.add_parser("lock", help="accept the current behavior as the lock")
    subcommands.add_parser("verify", help="check the current code against the lock")
    mutate_command = subcommands.add_parser("mutate", help="measure the lock with planted mutants")
    mutate_command.add_argument("--max", type=int, default=60, help="mutants to run, spread evenly")
    mutate_command.add_argument("--file", help="only targets whose path contains this text")
    mutate_command.add_argument("--list", action="store_true", help="list mutants without running them")
    mutate_command.add_argument("--native", action="store_true", help="run the adapter's own mutation tool")
    return argument_parser


def run_command(arguments: argparse.Namespace) -> int:
    project_root = arguments.root.resolve()
    if "init" == arguments.command:
        adapter_name = arguments.adapter or detect_adapter(project_root, arguments.targets)
        config_path = write_initial_config(project_root, adapter_name, arguments.targets)
        print(f"{config_path} written with the {adapter_name} adapter. Fill in surface entries and checks, then lock.")
        return 0
    run_config = load_run_config(project_root)
    if "surface" == arguments.command:
        print("\n".join(extract_surface(run_config)))
        return 0
    if "scenarios" == arguments.command:
        scenario_file = run_config.checks.get("scenarios")
        if not scenario_file:
            raise ReadbackError("checks.scenarios is not set")
        print(json.dumps(record_all_scenarios(project_root, scenario_file), indent=2))
        return 0
    if "lock" == arguments.command:
        return lock_behavior(run_config)
    if "verify" == arguments.command:
        return verify_against_lock(run_config)
    if arguments.native:
        return run_native_mutation(run_config)
    return mutate_targets(run_config, arguments.max, arguments.file, arguments.list)


def main() -> int:
    arguments = build_argument_parser().parse_args()
    try:
        return run_command(arguments)
    except ReadbackError as readback_error:
        print(f"ERROR: {readback_error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
