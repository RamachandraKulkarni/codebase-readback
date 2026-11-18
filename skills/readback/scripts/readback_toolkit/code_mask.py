# Marks which characters of a source file are code, so mutations never land inside strings or comments.
from dataclasses import dataclass


@dataclass(frozen=True)
class LexicalRules:
    line_comment_markers: tuple[str, ...]
    block_comment_pairs: tuple[tuple[str, str], ...]
    string_quotes: tuple[str, ...]
    # Shell and YAML only start a comment at a word boundary, so `$#` and `a#b` stay code.
    comment_needs_word_boundary: bool
    backslash_escapes_in_single_quotes: bool


def build_code_mask(source_text: str, rules: LexicalRules) -> list[bool]:
    is_code = [True] * len(source_text)
    position = 0
    while position < len(source_text):
        skipped_length = (
            measure_comment(source_text, position, rules)
            or measure_string(source_text, position, rules)
        )
        if 0 == skipped_length:
            position += 1
            continue
        for masked_position in range(position, position + skipped_length):
            is_code[masked_position] = False
        position += skipped_length
    return is_code


def measure_comment(source_text: str, position: int, rules: LexicalRules) -> int:
    is_at_word_boundary = 0 == position or source_text[position - 1] in " \t\n"
    for marker in rules.line_comment_markers:
        if not source_text.startswith(marker, position):
            continue
        if rules.comment_needs_word_boundary and not is_at_word_boundary:
            continue
        line_end = source_text.find("\n", position)
        return (len(source_text) if -1 == line_end else line_end) - position
    for opening_marker, closing_marker in rules.block_comment_pairs:
        if source_text.startswith(opening_marker, position):
            closing_position = source_text.find(closing_marker, position + len(opening_marker))
            comment_end = len(source_text) if -1 == closing_position else closing_position + len(closing_marker)
            return comment_end - position
    return 0


def measure_string(source_text: str, position: int, rules: LexicalRules) -> int:
    # Longest quote first, so Python's triple quotes win over a single quote.
    for quote in sorted(rules.string_quotes, key=len, reverse=True):
        if not source_text.startswith(quote, position):
            continue
        is_escaping_allowed = "'" != quote or rules.backslash_escapes_in_single_quotes
        scan_position = position + len(quote)
        while scan_position < len(source_text):
            if is_escaping_allowed and "\\" == source_text[scan_position]:
                scan_position += 2
                continue
            if source_text.startswith(quote, scan_position):
                return scan_position + len(quote) - position
            if 1 == len(quote) and "`" != quote and "\n" == source_text[scan_position]:
                return scan_position - position
            scan_position += 1
        return len(source_text) - position
    return 0
