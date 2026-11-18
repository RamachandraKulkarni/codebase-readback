# Public surface extractors: what callers outside the module can see, as sorted text lines.
import ast
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from readback_toolkit.run_config import ReadbackError, RunConfig, expand_globs

SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1]
TYPESCRIPT_CACHE_DIRECTORY = Path.home() / ".cache" / "readback" / "typescript"
TREE_SITTER_LANGUAGE_BY_EXTENSION = {
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".kt": "kotlin", ".kts": "kotlin", ".cs": "csharp",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".swift": "swift", ".scala": "scala",
    ".php": "php", ".lua": "lua", ".ex": "elixir", ".exs": "elixir", ".dart": "dart", ".java": "java",
    ".py": "python", ".ts": "typescript", ".js": "javascript", ".sh": "bash",
}
DEFINITION_NODE_KEYWORDS = ("function", "method", "class", "struct", "interface", "enum", "trait", "type", "module", "constructor")


def extract_surface(run_config: RunConfig) -> list[str]:
    surface_settings = run_config.settings.get("surface", {})
    extractor_name = surface_settings.get("extractor", "none")
    extractors = {
        "none": lambda project_root, settings: [],
        "typescript": extract_typescript_surface,
        "java": extract_java_surface,
        "python": extract_python_surface,
        "tree-sitter": extract_tree_sitter_surface,
    }
    if extractor_name not in extractors:
        raise ReadbackError(f"unknown surface extractor {extractor_name!r}")
    return sorted(extractors[extractor_name](run_config.project_root, surface_settings))


def require_entries(project_root: Path, surface_settings: dict[str, Any]) -> list[str]:
    entry_paths = expand_globs(project_root, surface_settings.get("entries", []))
    if 0 == len(entry_paths):
        raise ReadbackError("surface.entries lists no files; name the module's public entry points")
    return entry_paths


def run_tool(command: list[str], project_root: Path, extra_environment: dict[str, str] | None = None) -> str:
    completed = subprocess.run(command, cwd=project_root, capture_output=True, text=True,
                               env={**os.environ, **(extra_environment or {})})
    if 0 != completed.returncode:
        raise ReadbackError(f"{' '.join(command[:3])} failed: {completed.stderr.strip()[-600:]}")
    return completed.stdout


def extract_typescript_surface(project_root: Path, surface_settings: dict[str, Any]) -> list[str]:
    entry_paths = require_entries(project_root, surface_settings)
    ensure_typescript_compiler_api()
    surface_text = run_tool(["node", str(SCRIPTS_DIRECTORY / "ts_surface.mjs"), *entry_paths], project_root,
                            {"READBACK_TYPESCRIPT_DIR": str(TYPESCRIPT_CACHE_DIRECTORY / "node_modules" / "typescript")})
    return surface_text.splitlines()


def ensure_typescript_compiler_api() -> None:
    # The native tsc binary has no JavaScript API, so the compiler package is cached once per machine.
    if (TYPESCRIPT_CACHE_DIRECTORY / "node_modules" / "typescript" / "package.json").exists():
        return
    TYPESCRIPT_CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    run_tool(["npm", "install", "--prefix", str(TYPESCRIPT_CACHE_DIRECTORY), "--no-save", "--silent", "typescript@5"],
             TYPESCRIPT_CACHE_DIRECTORY)


def extract_java_surface(project_root: Path, surface_settings: dict[str, Any]) -> list[str]:
    source_paths = expand_globs(project_root, surface_settings.get("sources", ["src/main/java/**/*.java"]))
    if 0 == len(source_paths):
        raise ReadbackError("surface.sources matches no Java files")
    with tempfile.TemporaryDirectory(prefix="readback-javap-") as class_directory:
        run_tool(["javac", "-nowarn", "-d", class_directory, *source_paths], project_root)
        compiled_class_names = sorted(
            class_path.relative_to(class_directory).with_suffix("").as_posix().replace("/", ".")
            for class_path in Path(class_directory).rglob("*.class")
        )
        class_names = surface_settings.get("entries") or compiled_class_names
        javap_text = run_tool(["javap", "-public", "-cp", class_directory, *class_names], project_root)
    return [line.strip() for line in javap_text.splitlines() if line.strip() and not line.startswith("Compiled from")]


def extract_python_surface(project_root: Path, surface_settings: dict[str, Any]) -> list[str]:
    surface_lines = []
    declared_names = set(surface_settings.get("names", []))
    for entry_path in require_entries(project_root, surface_settings):
        module_tree = ast.parse((project_root / entry_path).read_text(), entry_path)
        # Names the triage declared public win over __all__, which wins over the underscore convention.
        exported_names = declared_names or find_dunder_all(module_tree)
        for statement in module_tree.body:
            for defined_name, surface_line in describe_python_statement(statement):
                is_public = defined_name in exported_names if None is not exported_names else not defined_name.startswith("_")
                if is_public:
                    surface_lines.append(f"{entry_path}: {surface_line}")
    return surface_lines


def find_dunder_all(module_tree: ast.Module) -> set[str] | None:
    for statement in module_tree.body:
        is_dunder_all = isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and "__all__" == target.id for target in statement.targets)
        if is_dunder_all:
            return set(ast.literal_eval(statement.value))
    return None


def describe_python_statement(statement: ast.stmt) -> list[tuple[str, str]]:
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return [(statement.name, f"def {describe_python_function(statement)}")]
    if isinstance(statement, ast.ClassDef):
        class_header = f"class {statement.name}({', '.join(ast.unparse(base) for base in statement.bases)})"
        decorators = "".join(f"@{ast.unparse(decorator)} " for decorator in statement.decorator_list)
        member_lines = [f"class {statement.name}.{line}" for member in statement.body for line in describe_python_member(member)]
        return [(statement.name, line) for line in [f"class {decorators}{class_header}", *member_lines]]
    if isinstance(statement, ast.Assign):
        return [(target.id, f"name {target.id}") for target in statement.targets if isinstance(target, ast.Name)]
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        return [(statement.target.id, f"name {statement.target.id}: {ast.unparse(statement.annotation)}")]
    return []


def describe_python_member(member: ast.stmt) -> list[str]:
    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and not is_private_python_name(member.name):
        return [describe_python_function(member)]
    if isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name) and not member.target.id.startswith("_"):
        default_text = "" if None is member.value else f" = {ast.unparse(member.value)}"
        return [f"{member.target.id}: {ast.unparse(member.annotation)}{default_text}"]
    return []


def is_private_python_name(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def describe_python_function(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    decorators = "".join(f"@{ast.unparse(decorator)} " for decorator in function_node.decorator_list)
    return_annotation = "" if None is function_node.returns else f" -> {ast.unparse(function_node.returns)}"
    async_marker = "async " if isinstance(function_node, ast.AsyncFunctionDef) else ""
    return f"{decorators}{async_marker}{function_node.name}({ast.unparse(function_node.args)}){return_annotation}"


def extract_tree_sitter_surface(project_root: Path, surface_settings: dict[str, Any]) -> list[str]:
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError as missing_package:
        raise ReadbackError("generic surface needs tree-sitter: pip install tree-sitter-language-pack") from missing_package
    public_names = set(surface_settings.get("names", []))
    surface_lines = []
    for entry_path in require_entries(project_root, surface_settings):
        language = surface_settings.get("language") or TREE_SITTER_LANGUAGE_BY_EXTENSION.get(Path(entry_path).suffix)
        if not language:
            raise ReadbackError(f"{entry_path}: set surface.language, the extension is not known")
        syntax_tree = get_parser(language).parse((project_root / entry_path).read_bytes())
        for definition_line in collect_definitions(syntax_tree.root_node, owner_name="", depth=0):
            defined_name = re.split(r"[.( ]", definition_line.split(" ", 1)[1])[0]
            if 0 == len(public_names) or defined_name in public_names:
                surface_lines.append(f"{entry_path}: {definition_line}")
    return surface_lines


def collect_definitions(node: Any, owner_name: str, depth: int) -> list[str]:
    definition_lines = []
    for child in node.named_children:
        name_node = child.child_by_field_name("name")
        is_definition = None is not name_node and any(keyword in child.type for keyword in DEFINITION_NODE_KEYWORDS)
        if is_definition:
            qualified_name = f"{owner_name}.{name_node.text.decode()}" if owner_name else name_node.text.decode()
            parameters_node = child.child_by_field_name("parameters")
            parameters_text = "" if None is parameters_node else " ".join(parameters_node.text.decode().split())
            result_node = child.child_by_field_name("result") or child.child_by_field_name("return_type")
            result_text = "" if None is result_node else f" -> {' '.join(result_node.text.decode().split())}"
            definition_lines.append(f"{child.type} {qualified_name}{parameters_text}{result_text}")
            if depth < 2:
                definition_lines.extend(collect_definitions(child, qualified_name, depth + 1))
        elif depth < 3:
            definition_lines.extend(collect_definitions(child, owner_name, depth + 1))
    return definition_lines
