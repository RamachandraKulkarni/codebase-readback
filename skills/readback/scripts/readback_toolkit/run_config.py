# The run configuration: the adapter's defaults with the project's .readback/config.json laid over them.
import glob
import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ADAPTERS_DIRECTORY = Path(__file__).resolve().parents[2] / "adapters"
STATE_DIRECTORY_NAME = ".readback"
CONFIG_FILE_NAME = "config.json"


class ReadbackError(Exception):
    pass


@dataclass(frozen=True)
class RunConfig:
    project_root: Path
    adapter_name: str
    settings: dict[str, Any]

    @property
    def state_directory(self) -> Path:
        return self.project_root / STATE_DIRECTORY_NAME

    @property
    def config_path(self) -> Path:
        return self.state_directory / CONFIG_FILE_NAME

    @property
    def target_paths(self) -> list[str]:
        return expand_globs(self.project_root, self.settings["targets"])

    @property
    def checks(self) -> dict[str, Any]:
        return self.settings.get("checks", {})

    def command_with_targets(self, command_template: str) -> str:
        quoted_targets = " ".join(shlex.quote(target_path) for target_path in self.target_paths)
        return command_template.replace("{targets}", quoted_targets)


def list_adapter_names() -> list[str]:
    return sorted(adapter_path.stem for adapter_path in ADAPTERS_DIRECTORY.glob("*.json"))


def load_adapter(adapter_name: str) -> dict[str, Any]:
    adapter_path = ADAPTERS_DIRECTORY / f"{adapter_name}.json"
    if not adapter_path.exists():
        raise ReadbackError(f"no adapter {adapter_name!r}; available: {', '.join(list_adapter_names())}")
    return json.loads(adapter_path.read_text())


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, override_value in override.items():
        base_value = merged.get(key)
        merged[key] = deep_merge(base_value, override_value) if isinstance(base_value, dict) and isinstance(override_value, dict) else override_value
    return merged


def load_run_config(project_root: Path) -> RunConfig:
    config_path = project_root / STATE_DIRECTORY_NAME / CONFIG_FILE_NAME
    if not config_path.exists():
        raise ReadbackError(f"no {config_path}; run `readback init` first")
    project_settings = json.loads(config_path.read_text())
    adapter_name = project_settings.get("adapter")
    if None is adapter_name:
        raise ReadbackError(f"{config_path}: missing \"adapter\"")
    settings = deep_merge(load_adapter(adapter_name), project_settings)
    if 0 == len(settings.get("targets", [])):
        raise ReadbackError(f"{config_path}: \"targets\" lists no files to rewrite")
    return RunConfig(project_root, adapter_name, settings)


def expand_globs(project_root: Path, patterns: list[str]) -> list[str]:
    matched_paths: set[str] = set()
    for pattern in patterns:
        for matched_path in glob.glob(pattern, root_dir=project_root, recursive=True, include_hidden=False):
            is_tool_file = matched_path.startswith((STATE_DIRECTORY_NAME, "node_modules", "target/")) or "__pycache__" in matched_path
            if (project_root / matched_path).is_file() and not is_tool_file:
                matched_paths.add(matched_path)
    return sorted(matched_paths)


def detect_adapter(project_root: Path, target_patterns: list[str]) -> str:
    target_paths = expand_globs(project_root, target_patterns)
    for adapter_name in list_adapter_names():
        detection = load_adapter(adapter_name)["detect"]
        is_marker_target = any(Path(target_path).name in detection["marker_files"] for target_path in target_paths)
        is_extension_match = 0 < len(target_paths) and all(Path(target_path).suffix in detection["extensions"] for target_path in target_paths)
        if is_marker_target or is_extension_match:
            return adapter_name
    return "generic"


def write_initial_config(project_root: Path, adapter_name: str, target_patterns: list[str]) -> Path:
    adapter = load_adapter(adapter_name)
    config_path = project_root / STATE_DIRECTORY_NAME / CONFIG_FILE_NAME
    if config_path.exists():
        raise ReadbackError(f"{config_path} already exists")
    initial_settings = {
        "adapter": adapter_name,
        "targets": target_patterns,
        "frozen": adapter["frozen"],
        "surface": adapter["surface"],
        "checks": adapter["checks"],
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(initial_settings, indent=2) + "\n")
    return config_path
