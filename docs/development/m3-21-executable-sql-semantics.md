# M3.21 Executable SQL semantics and proposal preflight

## Motivation

The post-M3.20 live run proved that grounded semantic Evidence can recover SQL correction after the
Supervisor exits early. Correction completed quickly and produced two different proposals, but both
were rejected for unknown columns. The model had the metric definition, dependency closure,
physical mappings, and relevant table catalogs, yet still represented the derived metric or grouping
concept as a database field.

More prompting or a longer timeout cannot make this failure deterministic. M3.21 therefore moves
two responsibilities into the backend:

1. compile the supported formula subset into an executable expression containing only physical
   `table.column` identifiers;
2. compile-check correction proposals before they consume an analytical SQL attempt.

No decrypted task, answer, reference SQL, model output, or local evaluation log is committed.

## Safe semantic formula compiler

Pinned semantic records are enriched after dependency expansion and physical-column resolution. The
compiler supports a deliberately small expression language:

- numeric literals and physical identifiers;
- parentheses and unary signs;
- addition, subtraction, multiplication, and division;
- numeric comparisons;
- ternary conditions, emitted as SQL `CASE WHEN`;
- the pinned LaTeX forms `\\text{Identifier}`, `\\times`, and simple `\\frac{a}{b}`;
- recursive references to other formulas in the selected dependency closure.

Identifiers resolve in one of two ways: to exactly one `resolved_columns` mapping or to another
compiled formula assignment. Ambiguous physical mappings, missing identifiers, cycles, unsupported
functions, and unsupported nested fractions fail closed. Such records remain useful descriptive
Evidence but do not receive an executable expression.

Successfully compiled records add:

- `compiled_sql_expression`, using quoted physical table and column names;
- `required_tables`, listing the tables referenced after full dependency expansion.

These additions remain discovery-only and cannot support final Claims by themselves.

## Read-only proposal preflight

SQLite Evidence adds `operation=validate_query`. It applies the existing read-only and single-
statement policy, then invokes `EXPLAIN QUERY PLAN` on the read-only connection. A valid proposal
returns stable `database_query_validation` Evidence containing only a query digest and validity
state. Invalid proposals return a structured error and no Evidence.

When executable semantic Evidence is present, SQL correction now follows this sequence:

1. request one structured SQL proposal;
2. preflight it without calling `admit_sql_query`;
3. if preflight rejects it, use the existing single repair slot with the bounded error and explicit
   instruction to copy `compiled_sql_expression`;
4. execute only a proposal that passed preflight.

Consequently, an invented column no longer increments analytical SQL attempts or consecutive
database-query failures. Preflight does not expand the proposal count, LLM budget, correction
deadline, Web budget, or research-round budget.

## Verification

Tests cover dependency expansion, physical qualification, ternary-to-`CASE` compilation, fractions,
unsupported formula fail-closed behavior, stable semantic Evidence, successful and rejected query
preflight, discovery-only gating, and repair of an invented metric before analytical execution.

A no-network check against the locked `alien` assets produced three semantic records for the target
metric, compiled the root expression across `observatories` and `telescopes`, passed SQLite
preflight, and returned one real query row. The compiled expression contained no metric or dependency
aliases.

## Remaining boundary

Preflight proves that identifiers and SQL structure are executable; it does not prove that an
arbitrary valid proposal is algebraically equivalent to the compiled expression. The correction
contract requires verbatim use of `compiled_sql_expression`, while a later hardening stage may add
AST-level semantic-equivalence enforcement if live validation shows the model can produce valid but
semantically different SQL.
