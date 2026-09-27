from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from app.research.fee_engine.matcher import EmptyListPolicy, FeeRuleMatcher
from app.research.fee_engine.models import (
    FeeCalculation,
    FeeComponent,
    FeeMatchStatus,
    FeeRule,
    TransactionContext,
)
from app.research.fee_engine.provenance import build_rule_provenance
from app.research.fee_engine.ranges import RangeSyntaxError

RATE_DIVISOR = Decimal("10000")
EMPTY_LIST_ASSUMPTION = (
    "Empty account_type, merchant_category_code, and aci lists are treated as wildcards."
)


class FeeEngine:
    def __init__(
        self,
        rules: Iterable[FeeRule],
        *,
        empty_list_policy: EmptyListPolicy = EmptyListPolicy.WILDCARD,
    ) -> None:
        self.matcher = FeeRuleMatcher(rules, empty_list_policy=empty_list_policy)

    def calculate(
        self,
        *,
        psp_reference: str | int,
        amount: Decimal,
        context: TransactionContext,
    ) -> FeeCalculation:
        validation_error = self._validate_inputs(amount, context)
        if validation_error:
            return FeeCalculation(
                psp_reference=str(psp_reference),
                status=FeeMatchStatus.INVALID_SOURCE_DATA,
                transaction_amount=amount,
                components=(),
                total_fee=Decimal("0"),
                error=validation_error,
            )
        try:
            rules = self.matcher.applicable_rules(context)
        except RangeSyntaxError as exc:
            return FeeCalculation(
                psp_reference=str(psp_reference),
                status=FeeMatchStatus.UNSUPPORTED_RULE,
                transaction_amount=amount,
                components=(),
                total_fee=Decimal("0"),
                error=str(exc),
            )
        if not rules:
            return FeeCalculation(
                psp_reference=str(psp_reference),
                status=FeeMatchStatus.NO_MATCH,
                transaction_amount=amount,
                components=(),
                total_fee=Decimal("0"),
            )

        components = tuple(self.calculate_component(rule, amount, context) for rule in rules)
        uses_empty_lists = any(self.matcher.uses_empty_list_wildcard(rule) for rule in rules)
        assumptions = (EMPTY_LIST_ASSUMPTION,) if uses_empty_lists else ()
        status = FeeMatchStatus.MATCHED
        if uses_empty_lists and self.matcher.empty_list_policy is EmptyListPolicy.AMBIGUOUS:
            status = FeeMatchStatus.AMBIGUOUS_SEMANTICS
        return FeeCalculation(
            psp_reference=str(psp_reference),
            status=status,
            transaction_amount=amount,
            components=components,
            total_fee=sum((component.total for component in components), Decimal("0")),
            assumptions=assumptions,
        )

    @staticmethod
    def _validate_inputs(amount: Decimal, context: TransactionContext) -> str | None:
        if amount < 0:
            return "transaction amount cannot be negative"
        if context.monthly_volume < 0:
            return "monthly volume cannot be negative"
        if not Decimal("0") <= context.monthly_fraud_rate <= Decimal("1"):
            return "monthly fraud rate must be between 0 and 1"
        if context.aci not in set("ABCDEFG"):
            return f"unsupported ACI: {context.aci!r}"
        if context.account_type not in set("RDHFSO"):
            return f"unsupported account type: {context.account_type!r}"
        return None

    @staticmethod
    def calculate_component(
        rule: FeeRule,
        amount: Decimal,
        context: TransactionContext,
    ) -> FeeComponent:
        variable_amount = rule.rate * amount / RATE_DIVISOR
        return FeeComponent(
            fee_rule_id=rule.rule_id,
            fixed_amount=rule.fixed_amount,
            rate=rule.rate,
            variable_amount=variable_amount,
            total=rule.fixed_amount + variable_amount,
            provenance=build_rule_provenance(rule, context),
        )
