# Built-in mutator: small, language-aware edits that a strong lock must notice.
import bisect
import re
from dataclasses import dataclass

from readback_toolkit.code_mask import LexicalRules, build_code_mask


@dataclass(frozen=True)
class Mutant:
    file_path: str
    line_number: int
    start_offset: int
    end_offset: int
    replacement: str
    description: str

    def apply_to(self, source_text: str) -> str:
        return source_text[:self.start_offset] + self.replacement + source_text[self.end_offset:]


# Each entry: pattern, replacement, label. Spaced operators avoid generics (`List<T>`) and arrows (`=>`).
OPERATOR_FAMILIES: dict[str, list[tuple[str, str, str]]] = {
    "c-like": [
        (r"===", "!==", "=== to !=="),
        (r"!==", "===", "!== to ==="),
        (r"(?<![=!<>])==(?!=)", "!=", "== to !="),
        (r"!=(?!=)", "==", "!= to =="),
        (r"<=", "<", "<= to <"),
        (r">=", ">", ">= to >"),
        (r"(?<= )<(?= )", "<=", "< to <="),
        (r"(?<= )>(?= )", ">=", "> to >="),
        (r"&&", "||", "&& to ||"),
        (r"\|\|", "&&", "|| to &&"),
        (r"(?<= )\+(?= )", "-", "+ to -"),
        (r"(?<= )-(?= )", "+", "- to +"),
        (r"(?<= )\*(?= )", "/", "* to /"),
        (r"(?<= )/(?= )", "*", "/ to *"),
        (r"\btrue\b", "false", "true to false"),
        (r"\bfalse\b", "true", "false to true"),
        (r"!(?=[\w(])", "", "drop !"),
        (r"(?<![\w.])\d+(?![\w.])", "+1", "integer + 1"),
    ],
    "python": [
        (r"(?<![=!<>])==(?!=)", "!=", "== to !="),
        (r"!=", "==", "!= to =="),
        (r"<=", "<", "<= to <"),
        (r">=", ">", ">= to >"),
        (r"(?<= )<(?= )", "<=", "< to <="),
        (r"(?<= )>(?= )", ">=", "> to >="),
        (r"\band\b", "or", "and to or"),
        (r"\bor\b", "and", "or to and"),
        (r"\bnot ", "", "drop not"),
        (r"(?<= )\+(?= )", "-", "+ to -"),
        (r"(?<= )-(?= )", "+", "- to +"),
        (r"(?<= )\*(?= )", "/", "* to /"),
        (r"\bTrue\b", "False", "True to False"),
        (r"\bFalse\b", "True", "False to True"),
        (r"(?<![\w.])\d+(?![\w.])", "+1", "integer + 1"),
    ],
    "shell": [
        (r"-eq\b", "-ne", "-eq to -ne"),
        (r"-ne\b", "-eq", "-ne to -eq"),
        (r"-lt\b", "-ge", "-lt to -ge"),
        (r"-gt\b", "-le", "-gt to -le"),
        (r"-z\b", "-n", "-z to -n"),
        (r"-n\b(?= )", "-z", "-n to -z"),
        (r"(?<= )==(?= )", "!=", "== to !="),
        (r"(?<= )!=(?= )", "==", "!= to =="),
        (r"&&", "||", "&& to ||"),
        (r"\|\|", "&&", "|| to &&"),
        (r"\bexit 0\b", "exit 1", "exit 0 to exit 1"),
        (r"\bexit 1\b", "exit 0", "exit 1 to exit 0"),
    ],
    "gitlab-ci": [
        (r"(?<= )==(?= )", "!=", "== to !="),
        (r"(?<= )!=(?= )", "==", "!= to =="),
        (r"&&", "||", "&& to ||"),
        (r"\|\|", "&&", "|| to &&"),
    ],
}

# Integer mutants rewrite the literal itself, so the replacement is computed rather than fixed.
INTEGER_INCREMENT_MARKER = "+1"


def find_mutants(file_path: str, source_text: str, rules: LexicalRules, operator_family: str,
                 deletable_line_pattern: str | None, deleted_line_replacement: str) -> list[Mutant]:
    is_code = build_code_mask(source_text, rules)
    line_start_offsets = [0] + [index + 1 for index, character in enumerate(source_text) if "\n" == character]
    mutants = []
    for pattern, replacement, label in OPERATOR_FAMILIES[operator_family]:
        for operator_match in re.finditer(pattern, source_text):
            if not all(is_code[operator_match.start():operator_match.end()]):
                continue
            mutated_text = str(int(operator_match.group()) + 1) if INTEGER_INCREMENT_MARKER == replacement else replacement
            mutants.append(Mutant(
                file_path, line_number_of(operator_match.start(), line_start_offsets),
                operator_match.start(), operator_match.end(), mutated_text, label,
            ))
    if None is not deletable_line_pattern:
        mutants.extend(find_line_deletions(file_path, source_text, is_code, line_start_offsets,
                                           deletable_line_pattern, deleted_line_replacement))
    return sorted(mutants, key=lambda mutant: (mutant.start_offset, mutant.description))


def find_line_deletions(file_path: str, source_text: str, is_code: list[bool], line_start_offsets: list[int],
                        deletable_line_pattern: str, deleted_line_replacement: str) -> list[Mutant]:
    line_deletions = []
    for line_index, line_start in enumerate(line_start_offsets):
        line_end = source_text.find("\n", line_start)
        line_end = len(source_text) if -1 == line_end else line_end
        # Strings become placeholders so a statement that holds a string still matches its shape.
        masked_line = "".join(
            character if is_code[line_start + offset] else "S"
            for offset, character in enumerate(source_text[line_start:line_end])
        )
        first_character_offset = line_start + len(masked_line) - len(masked_line.lstrip())
        is_comment_or_blank = first_character_offset >= line_end or not is_code[first_character_offset]
        if is_comment_or_blank or not re.match(deletable_line_pattern, masked_line):
            continue
        indentation = masked_line[:len(masked_line) - len(masked_line.lstrip())]
        line_deletions.append(Mutant(
            file_path, line_index + 1, line_start, line_end,
            indentation + deleted_line_replacement, "delete statement",
        ))
    return line_deletions


def line_number_of(offset: int, line_start_offsets: list[int]) -> int:
    return bisect.bisect_right(line_start_offsets, offset)


def pick_evenly(mutants: list[Mutant], maximum_count: int) -> list[Mutant]:
    if len(mutants) <= maximum_count:
        return mutants
    step = len(mutants) / maximum_count
    return [mutants[int(index * step)] for index in range(maximum_count)]
