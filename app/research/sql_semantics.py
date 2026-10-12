from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass


class SemanticFormulaError(ValueError):
    """Raised when a pinned formula cannot be compiled by the safe expression subset."""


TOKEN_PATTERN = re.compile(
    r"\s*(?:(?P<number>\d+(?:\.\d+)?)|(?P<identifier>[A-Za-z_][A-Za-z0-9_]*)|"
    r"(?P<operator><=|>=|!=|=|<|>|\+|-|\*|/|\?|:|\(|\)))"
)


def _formula_assignment(definition: str) -> tuple[str, str]:
    match = re.search(r"\$([^$]+)\$", definition)
    expression = match.group(1) if match else definition.strip()
    if not expression:
        raise SemanticFormulaError("formula does not contain an expression")
    expression = re.sub(r"\\text\s*\{([A-Za-z_][A-Za-z0-9_]*)\}", r"\1", expression)
    expression = expression.replace(r"\left", "").replace(r"\right", "")
    expression = expression.replace(r"\times", "*")
    fraction_pattern = re.compile(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
    while r"\frac" in expression:
        rewritten, count = fraction_pattern.subn(r"((\1) / (\2))", expression)
        if not count:
            raise SemanticFormulaError("formula contains an unsupported nested fraction")
        expression = rewritten
    if "=" not in expression:
        raise SemanticFormulaError("formula does not contain an assignment")
    lhs, rhs = expression.split("=", 1)
    lhs = lhs.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", lhs):
        raise SemanticFormulaError("formula output is not a simple identifier")
    return lhs, rhs.strip()


def _tokenize(expression: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(expression):
        match = TOKEN_PATTERN.match(expression, position)
        if not match:
            raise SemanticFormulaError(
                f"formula contains an unsupported token near {expression[position : position + 12]!r}"
            )
        tokens.append(match.group("number") or match.group("identifier") or match.group("operator"))
        position = match.end()
    return tokens


@dataclass
class _ExpressionParser:
    tokens: list[str]
    resolve_identifier: Callable[[str], str]
    position: int = 0

    def parse(self) -> str:
        result = self._ternary()
        if self.position != len(self.tokens):
            raise SemanticFormulaError(f"unexpected formula token: {self.tokens[self.position]}")
        return result

    def _peek(self) -> str:
        return self.tokens[self.position] if self.position < len(self.tokens) else ""

    def _take(self, expected: str | None = None) -> str:
        token = self._peek()
        if not token or (expected is not None and token != expected):
            raise SemanticFormulaError(f"expected {expected or 'formula token'}, found {token!r}")
        self.position += 1
        return token

    def _ternary(self) -> str:
        condition = self._comparison()
        if self._peek() != "?":
            return condition
        self._take("?")
        when_true = self._ternary()
        self._take(":")
        when_false = self._ternary()
        return f"(CASE WHEN {condition} THEN {when_true} ELSE {when_false} END)"

    def _comparison(self) -> str:
        left = self._sum()
        if self._peek() not in {"<", "<=", ">", ">=", "=", "!="}:
            return left
        operator = self._take()
        right = self._sum()
        return f"({left} {operator} {right})"

    def _sum(self) -> str:
        left = self._product()
        while self._peek() in {"+", "-"}:
            operator = self._take()
            left = f"({left} {operator} {self._product()})"
        return left

    def _product(self) -> str:
        left = self._unary()
        while self._peek() in {"*", "/"}:
            operator = self._take()
            left = f"({left} {operator} {self._unary()})"
        return left

    def _unary(self) -> str:
        if self._peek() in {"+", "-"}:
            operator = self._take()
            return f"({operator}{self._unary()})"
        return self._primary()

    def _primary(self) -> str:
        token = self._take()
        if token == "(":
            value = self._ternary()
            self._take(")")
            return f"({value})"
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            return token
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            return self.resolve_identifier(token)
        raise SemanticFormulaError(f"unexpected primary token: {token}")


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def compile_semantic_sql_expressions(
    entries: Iterable[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    """Compile the safe arithmetic subset of pinned formulas to physical SQLite expressions."""
    copied = [dict(entry) for entry in entries]
    assignments: dict[str, tuple[str, str]] = {}
    for entry in copied:
        try:
            lhs, rhs = _formula_assignment(str(entry.get("definition", "")))
        except SemanticFormulaError:
            continue
        assignments[lhs.casefold()] = (lhs, rhs)

    physical: dict[str, set[tuple[str, str]]] = {}
    for entry in copied:
        for item in entry.get("resolved_columns", ()):
            if not isinstance(item, dict):
                continue
            identifier = str(item.get("formula_identifier", "")).strip()
            table_name = str(item.get("table_name", "")).strip()
            column_name = str(item.get("column_name", "")).strip()
            if identifier and table_name and column_name:
                physical.setdefault(identifier.casefold(), set()).add((table_name, column_name))

    cache: dict[str, tuple[str, frozenset[str]]] = {}
    compiling: set[str] = set()

    def compile_identifier(identifier: str) -> tuple[str, frozenset[str]]:
        key = identifier.casefold()
        if key in cache:
            return cache[key]
        if key in compiling:
            raise SemanticFormulaError(f"cyclic formula dependency: {identifier}")
        mappings = physical.get(key, set())
        if len(mappings) == 1:
            table_name, column_name = next(iter(mappings))
            result = (
                f"{_quoted_identifier(table_name)}.{_quoted_identifier(column_name)}",
                frozenset((table_name,)),
            )
            cache[key] = result
            return result
        if len(mappings) > 1:
            raise SemanticFormulaError(f"ambiguous physical formula identifier: {identifier}")
        assignment = assignments.get(key)
        if assignment is None:
            raise SemanticFormulaError(f"unresolved formula identifier: {identifier}")
        compiling.add(key)
        tables: set[str] = set()

        def resolve_nested(nested_identifier: str) -> str:
            expression, nested_tables = compile_identifier(nested_identifier)
            tables.update(nested_tables)
            return expression

        try:
            expression = _ExpressionParser(
                _tokenize(assignment[1]),
                resolve_nested,
            ).parse()
        finally:
            compiling.remove(key)
        result = expression, frozenset(tables)
        cache[key] = result
        return result

    for entry in copied:
        try:
            lhs, _rhs = _formula_assignment(str(entry.get("definition", "")))
            expression, tables = compile_identifier(lhs)
        except SemanticFormulaError:
            continue
        entry["compiled_sql_expression"] = expression
        entry["required_tables"] = sorted(tables)
    return tuple(copied)


__all__ = ["SemanticFormulaError", "compile_semantic_sql_expressions"]
