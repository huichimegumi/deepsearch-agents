"""Compile a deliberately small subset of public LaTeX formulas into existing plans."""

from __future__ import annotations

import ast
import hashlib
import re

from app.research.query_plan import BoundValue, Expression, schema


def symbol(text):
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


def formula(text):
    if len(text) > 4000:
        raise ValueError("formula_length")

    def group(start):
        if start >= len(text) or text[start] != "{":
            raise ValueError("formula_group")
        depth = 1
        for end in range(start + 1, len(text)):
            depth += (text[end] == "{") - (text[end] == "}")
            if depth == 0:
                return text[start + 1 : end], end + 1
        raise ValueError("formula_unbalanced")

    output, pos = [], 0
    while pos < len(text):
        if text[pos] == "\\":
            match = re.match(r"\\([A-Za-z]+)", text[pos:])
            if not match:
                raise ValueError("formula_command")
            command = match[1]
            pos += len(match[0])
            while pos < len(text) and text[pos].isspace():
                pos += 1
            if command in {"text", "mathrm", "operatorname"}:
                inner, pos = group(pos)
                output.append(inner if re.fullmatch(r"'[^']*'", inner) else symbol(inner))
            elif command == "frac":
                numerator, pos = group(pos)
                while pos < len(text) and text[pos].isspace():
                    pos += 1
                denominator, pos = group(pos)
                output.append(f"(({formula(numerator)}) / ({formula(denominator)}))")
            elif command in {"times", "cdot", "div", "le", "leq", "ge", "geq", "neq"}:
                output.append(
                    {
                        "times": "*",
                        "cdot": "*",
                        "div": "/",
                        "le": "<=",
                        "leq": "<=",
                        "ge": ">=",
                        "geq": ">=",
                        "neq": "!=",
                    }[command]
                )
            elif command not in {"left", "right"}:
                raise ValueError("unsupported_formula_command")
        elif text[pos] == "{":
            inner, pos = group(pos)
            output.append(f"({formula(inner)})")
        else:
            output.append(text[pos])
            pos += 1
    return "".join(output)


def conditional(text):
    """Convert parenthesized ternaries; refuse ambiguous/unbalanced syntax."""
    output, pos = [], 0
    while pos < len(text):
        if text[pos] != "(":
            output.append(text[pos])
            pos += 1
            continue
        depth, end = 1, pos + 1
        while end < len(text) and depth:
            depth += (text[end] == "(") - (text[end] == ")")
            end += 1
        if depth:
            raise ValueError("formula_parentheses")
        output.append("(" + conditional(text[pos + 1 : end - 1]) + ")")
        pos = end
    text = "".join(output)
    depth, question, colon = 0, None, None
    for i, char in enumerate(text):
        depth += (char == "(") - (char == ")")
        if not depth and char == "?":
            if question is not None:
                raise ValueError("ambiguous_formula_conditional")
            question = i
        if not depth and char == ":":
            colon = i
    if question is not None and colon is not None:
        return f"({text[question + 1 : colon]} if {text[:question]} else {text[colon + 1 :]})"
    return text


class MetricRegistry:
    def __init__(self, database, entries):
        self.database, self.entries = database, entries
        self.columns, self.metrics, self.symbols, self.rejected = {}, {}, {}, {}
        self.field_refs = {}
        for table, (columns, _) in sorted(schema(database).items()):
            for column in sorted(columns):
                ref = f"{table}.{column}"
                key = f"c{len(self.columns) + 1}"
                self.columns[key] = ref
                self.field_refs[ref] = key
                for alias in (symbol(column), symbol(ref)):
                    self.symbols.setdefault(alias, []).append(("column", key))
        for entry in entries:
            if entry.get("type") != "calculation_knowledge":
                continue
            key = f"m{entry['id']}"
            try:
                blocks = re.findall(r"\$([^$]+)\$", entry["definition"])
                assignment = next(block for block in blocks if "=" in block)
                lhs, rhs = assignment.split("=", 1)
                name = symbol(formula(lhs))
                tree = ast.parse(conditional(formula(rhs)).strip(), mode="eval").body
                if not name:
                    raise ValueError("formula_name")
                self.metrics[key] = {
                    "name": name,
                    "tree": tree,
                    "source_id": entry["id"],
                    "source_sha256": hashlib.sha256(entry["definition"].encode()).hexdigest(),
                }
                self.symbols.setdefault(name, []).append(("metric", key))
            except (ValueError, SyntaxError, StopIteration, RecursionError):
                self.rejected[key] = "unsupported_public_formula"

    def catalog(self, table):
        result = [
            {"id": key, "column": ref}
            for key, ref in self.columns.items()
            if ref.split(".")[0] == table
        ]
        for key, metric in self.metrics.items():
            try:
                builder = MetricBuilder(self)
                builder.field(key)
                if builder.tables != {table}:
                    continue
                result.append(
                    {
                        "id": key,
                        "metric": metric["name"],
                        "definition_id": metric["source_id"],
                        "source_sha256": metric["source_sha256"],
                    }
                )
            except (ValueError, RecursionError):
                continue
        return result


class MetricBuilder:
    def __init__(self, registry, values=None):
        self.registry = registry
        self.values = dict(values or {})
        self.expressions, self.cache, self.tables, self.sources = [], {}, set(), {}

    def node(self, op, args=(), *, ref="", number=None):
        identity = (op, tuple(args), ref, number)
        if identity not in self.cache:
            key = f"x{len(self.expressions)}"
            self.expressions.append(
                Expression(key=key, op=op, args=list(args), ref=ref, number=number)
            )
            self.cache[identity] = key
        return self.cache[identity]

    def field(self, key, stack=()):
        if key in self.registry.columns:
            ref = self.registry.columns[key]
            self.tables.add(ref.split(".")[0])
            return self.node("column", ref=ref)
        if key not in self.registry.metrics or key in stack:
            raise ValueError("unknown_or_recursive_metric")
        metric = self.registry.metrics[key]
        self.sources[key] = metric["source_sha256"]
        return self.expression(metric["tree"], stack + (key,))

    def expression(self, tree, stack):
        if isinstance(tree, ast.Name):
            choices = self.registry.symbols.get(symbol(tree.id), [])
            choices = list(dict.fromkeys(choices))
            if len(choices) != 1:
                raise ValueError("unknown_or_ambiguous_formula_symbol")
            return self.field(choices[0][1], stack)
        if isinstance(tree, ast.Constant) and type(tree.value) in {int, float}:
            return self.node("number", number=tree.value)
        if isinstance(tree, ast.Constant) and isinstance(tree.value, str):
            key = f"literal_{len(self.values)}"
            self.values[key] = BoundValue(
                value=tree.value, source_ref="public-definition:" + stack[-1]
            )
            return self.node("parameter", ref=key)
        binary = {ast.Add: "add", ast.Sub: "subtract", ast.Mult: "multiply", ast.Div: "divide"}
        if isinstance(tree, ast.BinOp) and type(tree.op) in binary:
            return self.node(
                binary[type(tree.op)],
                [self.expression(tree.left, stack), self.expression(tree.right, stack)],
            )
        if isinstance(tree, ast.UnaryOp) and isinstance(tree.op, ast.USub):
            return self.node(
                "multiply", [self.node("number", number=-1), self.expression(tree.operand, stack)]
            )
        comparison = {
            ast.Eq: "eq",
            ast.NotEq: "ne",
            ast.Lt: "lt",
            ast.LtE: "le",
            ast.Gt: "gt",
            ast.GtE: "ge",
        }
        if isinstance(tree, ast.Compare) and len(tree.ops) == 1 and type(tree.ops[0]) in comparison:
            return self.node(
                comparison[type(tree.ops[0])],
                [self.expression(tree.left, stack), self.expression(tree.comparators[0], stack)],
            )
        if isinstance(tree, ast.IfExp):
            return self.node(
                "choose",
                [
                    self.expression(tree.test, stack),
                    self.expression(tree.body, stack),
                    self.expression(tree.orelse, stack),
                ],
            )
        if (
            isinstance(tree, ast.Call)
            and isinstance(tree.func, ast.Name)
            and tree.func.id == "abs"
            and len(tree.args) == 1
            and not tree.keywords
        ):
            return self.node("abs", [self.expression(tree.args[0], stack)])
        raise ValueError("unsupported_formula_ast")
