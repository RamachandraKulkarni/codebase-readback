#!/usr/bin/env python3
# Behavior lock for a GitLab CI file: which jobs run for every trigger, and exactly what each one runs.
# Usage:
#   lock_pipeline.py compare BEFORE.yml AFTER.yml   exit 0 only if every trigger scenario is identical
#   lock_pipeline.py scan PIPELINE.yml               pipeline errors and jobs that never run
import argparse
import itertools
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

UNSET_TRIGGER_VALUE = None
# A value no rule names, so `!= "x"` and bare-variable rules are exercised with a real value too.
UNLISTED_TRIGGER_VALUE = "readback-unlisted-value"
MAX_SCENARIO_COUNT = 200_000
MAX_REFERENCE_DEPTH = 10

NON_JOB_TOP_LEVEL_KEYS = frozenset(
    {"variables", "default", "stages", "image", "services", "before_script", "after_script", "cache"}
)
UNSUPPORTED_TOP_LEVEL_KEYS = frozenset({"include", "workflow"})
UNSUPPORTED_JOB_KEYS = frozenset({"only", "except", "trigger", "parallel", "inherit"})
UNSUPPORTED_RULE_KEYS = frozenset({"changes", "exists"})
# Keys a job takes from `default:` when it does not set them itself; GitLab replaces, never merges, these.
DEFAULT_INHERITABLE_KEYS = frozenset(
    {"image", "services", "before_script", "after_script", "cache", "tags", "artifacts",
     "retry", "timeout", "interruptible", "hooks", "id_tokens"}
)
SCRIPT_KEYS = ("before_script", "script", "after_script")

LITERAL_COMPARISON_PATTERN = re.compile(
    r"""\$\{?(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\}?\s*(?:==|!=)\s*(?P<quote>["'])(?P<literal>.*?)(?P=quote)"""
)
REVERSED_LITERAL_COMPARISON_PATTERN = re.compile(
    r"""(?P<quote>["'])(?P<literal>.*?)(?P=quote)\s*(?:==|!=)\s*\$\{?(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\}?"""
)
VARIABLE_REFERENCE_PATTERN = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
CONDITION_TOKEN_PATTERN = re.compile(
    r"""\s*(?:
        (?P<variable>\$\{?[A-Za-z_][A-Za-z0-9_]*\}?)
      | (?P<string>"[^"]*"|'[^']*')
      | (?P<regex>/(?:\\.|[^/\\])*/[imx]*)
      | (?P<operator>==|!=|=~|!~|&&|\|\|)
      | (?P<parenthesis>[()])
      | (?P<null>null)
    )""",
    re.VERBOSE,
)


class PipelineConfigError(Exception):
    pass


@dataclass(frozen=True)
class ReferenceTag:
    target_path: tuple[str, ...]


class PipelineYamlLoader(yaml.SafeLoader):
    pass


def construct_reference_tag(loader: PipelineYamlLoader, node: yaml.Node) -> ReferenceTag:
    return ReferenceTag(tuple(loader.construct_sequence(node)))


PipelineYamlLoader.add_constructor("!reference", construct_reference_tag)


def load_pipeline_document(pipeline_path: Path) -> dict[str, Any]:
    document = yaml.load(pipeline_path.read_text(encoding="utf-8"), Loader=PipelineYamlLoader)
    if not isinstance(document, dict):
        raise PipelineConfigError(f"{pipeline_path}: top level is not a mapping")
    unsupported_keys = UNSUPPORTED_TOP_LEVEL_KEYS & document.keys()
    if 0 < len(unsupported_keys):
        raise PipelineConfigError(f"{pipeline_path}: unsupported top-level keys {sorted(unsupported_keys)}")
    return resolve_reference_tags(document, document, depth=0)


def resolve_reference_tags(node: Any, document: dict[str, Any], depth: int) -> Any:
    if MAX_REFERENCE_DEPTH < depth:
        raise PipelineConfigError("!reference nesting deeper than GitLab allows")
    if isinstance(node, ReferenceTag):
        return resolve_reference_tags(lookup_reference_target(node, document), document, depth + 1)
    if isinstance(node, dict):
        return {key: resolve_reference_tags(value, document, depth) for key, value in node.items()}
    if isinstance(node, list):
        return [resolve_reference_tags(item, document, depth) for item in node]
    return node


def lookup_reference_target(reference: ReferenceTag, document: dict[str, Any]) -> Any:
    target = document
    for path_segment in reference.target_path:
        if not isinstance(target, dict) or path_segment not in target:
            raise PipelineConfigError(f"!reference {list(reference.target_path)} points at nothing")
        target = target[path_segment]
    return target


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, override_value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            merged[key] = deep_merge(base_value, override_value)
        else:
            merged[key] = override_value
    return merged


def resolve_extends(job_name: str, document: dict[str, Any], extends_chain: tuple[str, ...]) -> dict[str, Any]:
    job_definition = document[job_name]
    if not isinstance(job_definition, dict):
        raise PipelineConfigError(f"{job_name}: job definition is not a mapping")
    parent_job_names = job_definition.get("extends", [])
    if isinstance(parent_job_names, str):
        parent_job_names = [parent_job_names]
    inherited_definition: dict[str, Any] = {}
    for parent_job_name in parent_job_names:
        if parent_job_name in extends_chain or parent_job_name == job_name:
            raise PipelineConfigError(f"{job_name}: circular extends through {parent_job_name}")
        if parent_job_name not in document:
            raise PipelineConfigError(f"{job_name}: extends missing job {parent_job_name}")
        parent_definition = resolve_extends(parent_job_name, document, extends_chain + (job_name,))
        inherited_definition = deep_merge(inherited_definition, parent_definition)
    own_definition = {key: value for key, value in job_definition.items() if "extends" != key}
    return deep_merge(inherited_definition, own_definition)


def flatten_script_lines(script_value: Any) -> list[str]:
    # !reference inserts nested lists; GitLab flattens them into one command list.
    if isinstance(script_value, str):
        return [script_value]
    flattened_lines: list[str] = []
    for script_item in script_value:
        flattened_lines.extend(flatten_script_lines(script_item))
    return flattened_lines


def normalize_variables(variables_block: Any) -> dict[str, str]:
    if None is variables_block:
        return {}
    normalized_variables = {}
    for variable_name, variable_value in variables_block.items():
        if isinstance(variable_value, dict):
            variable_value = variable_value.get("value", "")
        normalized_variables[variable_name] = "" if None is variable_value else str(variable_value)
    return normalized_variables


@dataclass(frozen=True)
class PipelineDefinition:
    stages: list[str]
    global_variables: dict[str, str]
    job_defaults: dict[str, Any]
    resolved_jobs: dict[str, dict[str, Any]]


def build_pipeline_definition(document: dict[str, Any]) -> PipelineDefinition:
    legacy_defaults = {key: document[key] for key in DEFAULT_INHERITABLE_KEYS & document.keys()}
    job_defaults = {**legacy_defaults, **(document.get("default") or {})}
    resolved_jobs = {}
    for job_name in document:
        if job_name in NON_JOB_TOP_LEVEL_KEYS or job_name.startswith("."):
            continue
        resolved_job = resolve_extends(job_name, document, extends_chain=())
        unsupported_keys = UNSUPPORTED_JOB_KEYS & resolved_job.keys()
        if 0 < len(unsupported_keys):
            raise PipelineConfigError(f"{job_name}: unsupported job keys {sorted(unsupported_keys)}")
        for default_key, default_value in job_defaults.items():
            resolved_job.setdefault(default_key, default_value)
        for script_key in SCRIPT_KEYS:
            if script_key in resolved_job:
                resolved_job[script_key] = flatten_script_lines(resolved_job[script_key])
        resolved_jobs[job_name] = resolved_job
    return PipelineDefinition(
        stages=list(document.get("stages", ["build", "test", "deploy"])),
        global_variables=normalize_variables(document.get("variables")),
        job_defaults=job_defaults,
        resolved_jobs=resolved_jobs,
    )


class RuleConditionEvaluator:
    # Evaluates one `rules:if` expression with GitLab's operators: == != =~ !~ && || and parentheses.
    def __init__(self, condition_text: str, variable_values: dict[str, str | None]):
        self.condition_text = condition_text
        self.variable_values = variable_values
        self.tokens = self.tokenize(condition_text)
        self.position = 0

    def tokenize(self, condition_text: str) -> list[tuple[str, str]]:
        tokens = []
        scan_position = 0
        stripped_length = len(condition_text.rstrip())
        while scan_position < stripped_length:
            token_match = CONDITION_TOKEN_PATTERN.match(condition_text, scan_position)
            if None is token_match or token_match.end() == scan_position:
                raise PipelineConfigError(f"cannot parse rule condition: {condition_text!r}")
            tokens.append((token_match.lastgroup, token_match.group(token_match.lastgroup)))
            scan_position = token_match.end()
        return tokens

    def evaluate(self) -> bool:
        condition_result = self.parse_or_expression()
        if self.position != len(self.tokens):
            raise PipelineConfigError(f"trailing tokens in rule condition: {self.condition_text!r}")
        return condition_result

    def peek_token(self) -> tuple[str, str] | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take_token(self) -> tuple[str, str]:
        token = self.peek_token()
        if None is token:
            raise PipelineConfigError(f"rule condition ends early: {self.condition_text!r}")
        self.position += 1
        return token

    def parse_or_expression(self) -> bool:
        condition_result = self.parse_and_expression()
        while ("operator", "||") == self.peek_token():
            self.take_token()
            right_result = self.parse_and_expression()
            condition_result = condition_result or right_result
        return condition_result

    def parse_and_expression(self) -> bool:
        condition_result = self.parse_comparison()
        while ("operator", "&&") == self.peek_token():
            self.take_token()
            right_result = self.parse_comparison()
            condition_result = condition_result and right_result
        return condition_result

    def parse_comparison(self) -> bool:
        if ("parenthesis", "(") == self.peek_token():
            self.take_token()
            grouped_result = self.parse_or_expression()
            if ("parenthesis", ")") != self.take_token():
                raise PipelineConfigError(f"unbalanced parentheses: {self.condition_text!r}")
            return grouped_result
        left_kind, left_text = self.take_token()
        next_token = self.peek_token()
        if None is next_token or next_token[1] not in ("==", "!=", "=~", "!~"):
            left_value = self.operand_value(left_kind, left_text)
            return None is not left_value and "" != left_value
        _, comparison_operator = self.take_token()
        right_kind, right_text = self.take_token()
        if comparison_operator in ("=~", "!~"):
            is_pattern_matched = self.matches_pattern(self.operand_value(left_kind, left_text), right_kind, right_text)
            return is_pattern_matched if "=~" == comparison_operator else not is_pattern_matched
        is_equal = self.operand_value(left_kind, left_text) == self.operand_value(right_kind, right_text)
        return is_equal if "==" == comparison_operator else not is_equal

    def operand_value(self, token_kind: str, token_text: str) -> str | None:
        if "variable" == token_kind:
            return self.variable_values.get(token_text.strip("${}"))
        if "string" == token_kind:
            return token_text[1:-1]
        if "null" == token_kind:
            return None
        raise PipelineConfigError(f"unexpected {token_text!r} in {self.condition_text!r}")

    def matches_pattern(self, subject: str | None, pattern_kind: str, pattern_text: str) -> bool:
        if None is subject:
            return False
        if "variable" == pattern_kind:
            pattern_text = self.variable_values.get(pattern_text.strip("${}")) or ""
        elif "regex" != pattern_kind:
            raise PipelineConfigError(f"=~ needs a /regex/ in {self.condition_text!r}")
        pattern_body, _, pattern_flags = pattern_text[1:].rpartition("/")
        regex_flags = re.IGNORECASE if "i" in pattern_flags else 0
        return None is not re.search(pattern_body, subject, regex_flags)


def evaluate_job_rules(job: dict[str, Any], rule_variables: dict[str, str | None]) -> dict[str, Any] | None:
    # Returns the attributes the matching rule adds, or None when the job is left out of the pipeline.
    rules = job.get("rules")
    if None is rules:
        return {"when": job.get("when", "on_success")}
    for rule in rules:
        unsupported_keys = UNSUPPORTED_RULE_KEYS & rule.keys()
        if 0 < len(unsupported_keys):
            raise PipelineConfigError(f"unsupported rule keys {sorted(unsupported_keys)}")
        condition_text = rule.get("if")
        if None is not condition_text and not RuleConditionEvaluator(condition_text, rule_variables).evaluate():
            continue
        rule_when = rule.get("when", job.get("when", "on_success"))
        if "never" == rule_when:
            return None
        return {key: value for key, value in rule.items() if "if" != key} | {"when": rule_when}
    return None


def collect_trigger_matrix(pipelines: list[PipelineDefinition]) -> dict[str, list[str | None]]:
    # Every variable a rule tests, paired with every literal it is compared against, an unlisted value, and "not passed".
    literals_by_variable: dict[str, set[str]] = {}
    for pipeline in pipelines:
        for job in pipeline.resolved_jobs.values():
            for rule in job.get("rules") or []:
                condition_text = rule.get("if") or ""
                for variable_name in VARIABLE_REFERENCE_PATTERN.findall(condition_text):
                    literals_by_variable.setdefault(variable_name, set())
                for pattern in (LITERAL_COMPARISON_PATTERN, REVERSED_LITERAL_COMPARISON_PATTERN):
                    for comparison in pattern.finditer(condition_text):
                        literals_by_variable[comparison["variable"]].add(comparison["literal"])
    return {
        variable_name: sorted(literals) + [UNLISTED_TRIGGER_VALUE, UNSET_TRIGGER_VALUE]
        for variable_name, literals in sorted(literals_by_variable.items())
    }


def iterate_trigger_scenarios(trigger_matrix: dict[str, list[str | None]]):
    variable_names = list(trigger_matrix)
    for value_combination in itertools.product(*(trigger_matrix[name] for name in variable_names)):
        yield dict(zip(variable_names, value_combination))


def plan_pipeline_for_scenario(pipeline: PipelineDefinition, trigger_values: dict[str, str | None]) -> dict[str, Any]:
    passed_trigger_values = {name: value for name, value in trigger_values.items() if None is not value}
    planned_jobs = {}
    for job_name, job in pipeline.resolved_jobs.items():
        job_variables = normalize_variables(job.get("variables"))
        # Trigger variables outrank every variable written in the YAML file.
        rule_variables = {**pipeline.global_variables, **job_variables, **passed_trigger_values}
        matched_rule_attributes = evaluate_job_rules(job, rule_variables)
        if None is matched_rule_attributes:
            continue
        job_fingerprint = {key: value for key, value in job.items() if key not in ("rules", "variables")}
        job_fingerprint["variables"] = {
            **pipeline.global_variables, **job_variables,
            **normalize_variables(matched_rule_attributes.pop("variables", None)),
        }
        job_fingerprint.update(matched_rule_attributes)
        planned_jobs[job_name] = job_fingerprint
    return {"jobs": planned_jobs, "errors": find_pipeline_creation_errors(pipeline, planned_jobs)}


def find_pipeline_creation_errors(pipeline: PipelineDefinition, planned_jobs: dict[str, Any]) -> list[str]:
    creation_errors = []
    for job_name, job in planned_jobs.items():
        if job.get("stage", "test") not in pipeline.stages + [".pre", ".post"]:
            creation_errors.append(f"{job_name}: stage {job.get('stage')!r} is not declared")
        for needed_job in job.get("needs") or []:
            needed_job_name = needed_job if isinstance(needed_job, str) else needed_job.get("job")
            is_optional = isinstance(needed_job, dict) and True is needed_job.get("optional")
            if needed_job_name not in planned_jobs and not is_optional:
                creation_errors.append(f"{job_name}: needs {needed_job_name}, which is not in this pipeline")
    return sorted(creation_errors)


def describe_trigger(trigger_values: dict[str, str | None]) -> str:
    return " ".join(f"{name}={'<unset>' if None is value else value}" for name, value in trigger_values.items())


def describe_matrix_size(trigger_matrix: dict[str, list[str | None]]) -> tuple[str, int]:
    scenario_count = 1
    for values in trigger_matrix.values():
        scenario_count *= len(values)
    if MAX_SCENARIO_COUNT < scenario_count:
        raise PipelineConfigError(f"{scenario_count} scenarios exceeds the {MAX_SCENARIO_COUNT} limit")
    dimension_text = " x ".join(f"{name}({len(values)})" for name, values in trigger_matrix.items())
    return f"{dimension_text} = {scenario_count} scenarios", scenario_count


def find_job_differences(before_plan: dict[str, Any], after_plan: dict[str, Any]) -> list[str]:
    differences = []
    for job_name in sorted(before_plan["jobs"].keys() | after_plan["jobs"].keys()):
        before_job = before_plan["jobs"].get(job_name)
        after_job = after_plan["jobs"].get(job_name)
        if None is before_job or None is after_job:
            differences.append(f"{job_name}: {'added' if None is before_job else 'removed'}")
            continue
        for field_name in sorted(before_job.keys() | after_job.keys()):
            if before_job.get(field_name) != after_job.get(field_name):
                differences.append(f"{job_name}.{field_name}: {before_job.get(field_name)!r} -> {after_job.get(field_name)!r}")
    if before_plan["errors"] != after_plan["errors"]:
        differences.append(f"pipeline errors: {before_plan['errors']} -> {after_plan['errors']}")
    return differences


def compare_pipelines(before_path: Path, after_path: Path, shown_difference_limit: int) -> int:
    before_pipeline = build_pipeline_definition(load_pipeline_document(before_path))
    after_pipeline = build_pipeline_definition(load_pipeline_document(after_path))
    trigger_matrix = collect_trigger_matrix([before_pipeline, after_pipeline])
    matrix_description, scenario_count = describe_matrix_size(trigger_matrix)
    print(f"Trigger matrix: {matrix_description}")

    pipeline_level_differences = []
    if before_pipeline.stages != after_pipeline.stages:
        pipeline_level_differences.append(f"stages: {before_pipeline.stages} -> {after_pipeline.stages}")
    if before_pipeline.global_variables != after_pipeline.global_variables:
        pipeline_level_differences.append("global variables differ (exported to every script)")
    if before_pipeline.resolved_jobs.keys() != after_pipeline.resolved_jobs.keys():
        pipeline_level_differences.append(
            f"job names: {sorted(before_pipeline.resolved_jobs.keys() ^ after_pipeline.resolved_jobs.keys())}"
        )
    print(f"Pipeline level: {'identical' if 0 == len(pipeline_level_differences) else 'DIFFERENT'}")
    for difference in pipeline_level_differences:
        print(f"  {difference}")

    differing_scenario_count = 0
    scenarios_with_errors = 0
    for trigger_values in iterate_trigger_scenarios(trigger_matrix):
        before_plan = plan_pipeline_for_scenario(before_pipeline, trigger_values)
        after_plan = plan_pipeline_for_scenario(after_pipeline, trigger_values)
        if 0 < len(before_plan["errors"]):
            scenarios_with_errors += 1
        scenario_differences = find_job_differences(before_plan, after_plan)
        if 0 == len(scenario_differences):
            continue
        differing_scenario_count += 1
        if differing_scenario_count <= shown_difference_limit:
            print(f"  DIFF [{describe_trigger(trigger_values)}]")
            for difference in scenario_differences:
                print(f"    {difference}")

    identical_count = scenario_count - differing_scenario_count
    print(f"Scenarios identical: {identical_count} of {scenario_count}")
    print(f"Scenarios that fail pipeline creation in BEFORE (pre-existing): {scenarios_with_errors}")
    is_behavior_preserved = 0 == differing_scenario_count and 0 == len(pipeline_level_differences)
    print("LOCK HELD" if is_behavior_preserved else "LOCK BROKEN")
    return 0 if is_behavior_preserved else 1


def scan_pipeline(pipeline_path: Path) -> int:
    pipeline = build_pipeline_definition(load_pipeline_document(pipeline_path))
    trigger_matrix = collect_trigger_matrix([pipeline])
    matrix_description, _ = describe_matrix_size(trigger_matrix)
    print(f"Trigger matrix: {matrix_description}")
    scenario_count_by_error: dict[str, int] = {}
    example_trigger_by_error: dict[str, str] = {}
    jobs_that_ever_run: set[str] = set()
    for trigger_values in iterate_trigger_scenarios(trigger_matrix):
        plan = plan_pipeline_for_scenario(pipeline, trigger_values)
        jobs_that_ever_run.update(plan["jobs"])
        for creation_error in plan["errors"]:
            scenario_count_by_error[creation_error] = scenario_count_by_error.get(creation_error, 0) + 1
            example_trigger_by_error.setdefault(creation_error, describe_trigger(trigger_values))
    print(f"Jobs: {len(pipeline.resolved_jobs)}, never selected by any trigger: "
          f"{sorted(pipeline.resolved_jobs.keys() - jobs_that_ever_run) or 'none'}")
    print(f"Pipeline creation errors: {len(scenario_count_by_error)}")
    for creation_error, affected_count in sorted(scenario_count_by_error.items()):
        print(f"  {creation_error} ({affected_count} scenarios, e.g. {example_trigger_by_error[creation_error]})")
    return 0


def main() -> int:
    argument_parser = argparse.ArgumentParser(description="Behavior lock for GitLab CI files.")
    subcommands = argument_parser.add_subparsers(dest="command", required=True)
    compare_command = subcommands.add_parser("compare", help="prove AFTER behaves exactly like BEFORE")
    compare_command.add_argument("before_path", type=Path)
    compare_command.add_argument("after_path", type=Path)
    compare_command.add_argument("--show", type=int, default=10, help="differing scenarios to print")
    scan_command = subcommands.add_parser("scan", help="report pipeline errors and jobs that never run")
    scan_command.add_argument("pipeline_path", type=Path)
    arguments = argument_parser.parse_args()
    try:
        if "compare" == arguments.command:
            return compare_pipelines(arguments.before_path, arguments.after_path, arguments.show)
        return scan_pipeline(arguments.pipeline_path)
    except PipelineConfigError as config_error:
        print(f"ERROR: {config_error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
