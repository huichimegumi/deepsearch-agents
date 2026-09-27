from __future__ import annotations

from typing import Any

from app.research.fee_engine.models import FeeRule, FeeRuleProvenance, TransactionContext


def build_rule_provenance(rule: FeeRule, context: TransactionContext) -> FeeRuleProvenance:
    rule_values: dict[str, Any] = {
        "card_scheme": rule.card_scheme,
        "account_type": rule.account_types,
        "capture_delay": rule.capture_delay,
        "monthly_fraud_level": rule.monthly_fraud_level,
        "monthly_volume": rule.monthly_volume,
        "merchant_category_code": rule.merchant_category_codes,
        "is_credit": rule.is_credit,
        "aci": rule.acis,
        "intracountry": rule.intracountry,
    }
    context_values: dict[str, Any] = {
        "card_scheme": context.card_scheme,
        "account_type": context.account_type,
        "capture_delay": context.capture_delay,
        "monthly_fraud_level": context.monthly_fraud_rate,
        "monthly_volume": context.monthly_volume,
        "merchant_category_code": context.merchant_category_code,
        "is_credit": context.is_credit,
        "aci": context.aci,
        "intracountry": context.intracountry,
    }
    wildcard_conditions = tuple(
        name
        for name, value in rule_values.items()
        if value is None or (isinstance(value, tuple) and not value)
    )
    matched_conditions = {
        name: {
            "rule": _json_safe(rule_values[name]),
            "actual": _json_safe(context_values[name]),
        }
        for name in rule_values
        if name not in wildcard_conditions
    }
    return FeeRuleProvenance(
        fee_rule_id=rule.rule_id,
        source_locator=f"fees.json#ID={rule.rule_id}",
        matched_conditions=matched_conditions,
        wildcard_conditions=wildcard_conditions,
    )


def _json_safe(value: Any) -> Any:
    if hasattr(value, "as_tuple"):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value
