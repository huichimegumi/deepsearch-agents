"""Budgeted semantic context with complete dependency closures."""

from app.research.evidence_store import count_tokens


def definition_context(ranked, *, max_roots=5, max_tokens=4000):
    by_id = {entry["id"]: entry for entry in ranked}
    selected, rejected = {}, []

    def visit(key, visiting, closure):
        if key in visiting:
            raise ValueError("definition_dependency_cycle")
        if key in closure:
            return
        if key not in by_id:
            raise ValueError("definition_dependency_missing")
        entry = by_id[key]
        children = entry.get("children_knowledge", [])
        if isinstance(children, int):
            children = [children]
        for child in children:
            if child != -1:
                visit(child, visiting | {key}, closure)
        closure[key] = entry

    for root in ranked[:max_roots]:
        closure = dict(selected)
        try:
            visit(root["id"], set(), closure)
            if count_tokens(list(closure.values())) > max_tokens:
                raise ValueError("definition_dependency_budget")
            selected = closure
        except ValueError as exc:
            rejected.append({"root_id": root["id"], "reason": str(exc)})
    return list(selected.values()), rejected
