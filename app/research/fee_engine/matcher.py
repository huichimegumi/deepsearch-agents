from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from functools import lru_cache
from typing import Iterable

from app.research.fee_engine.models import FeeRule, RuleCriteria, TransactionContext
from app.research.fee_engine.ranges import (
    matches_capture_delay,
    matches_percentage,
    matches_volume,
)


class EmptyListPolicy(StrEnum):
    WILDCARD = "wildcard"
    AMBIGUOUS = "ambiguous"
    REJECT = "reject"


class FeeRuleMatcher:
    def __init__(
        self,
        rules: Iterable[FeeRule],
        *,
        empty_list_policy: EmptyListPolicy = EmptyListPolicy.WILDCARD,
    ) -> None:
        self.rules = tuple(sorted(rules, key=lambda rule: rule.rule_id))
        if len({rule.rule_id for rule in self.rules}) != len(self.rules):
            raise ValueError("fee rule IDs must be unique")
        self.empty_list_policy = empty_list_policy
        by_scheme: dict[str, list[FeeRule]] = defaultdict(list)
        for rule in self.rules:
            by_scheme[rule.card_scheme].append(rule)
        self._rules_by_scheme = {key: tuple(value) for key, value in by_scheme.items()}

    @lru_cache(maxsize=16384)
    def applicable_rules(self, context: TransactionContext) -> tuple[FeeRule, ...]:
        return tuple(
            rule
            for rule in self._rules_by_scheme.get(context.card_scheme, ())
            if self._matches_context(rule, context)
        )

    def filter_rules(self, criteria: RuleCriteria) -> tuple[FeeRule, ...]:
        """Filter using only criteria supplied by a benchmark question.

        An unspecified dimension imposes no restriction. For a supplied dimension,
        ``None`` and empty collections in the rule behave as wildcards.
        """

        candidates = (
            self._rules_by_scheme.get(criteria.card_scheme, ())
            if criteria.card_scheme is not None
            else self.rules
        )
        return tuple(rule for rule in candidates if self._matches_partial(rule, criteria))

    def uses_empty_list_wildcard(self, rule: FeeRule) -> bool:
        return not rule.account_types or not rule.merchant_category_codes or not rule.acis

    def _list_matches(self, allowed: tuple, actual) -> bool:
        if allowed:
            return actual in allowed
        if self.empty_list_policy is EmptyListPolicy.REJECT:
            return False
        return True

    def _matches_context(self, rule: FeeRule, context: TransactionContext) -> bool:
        return all(
            (
                rule.card_scheme == context.card_scheme,
                self._list_matches(rule.account_types, context.account_type),
                matches_capture_delay(rule.capture_delay, context.capture_delay),
                matches_percentage(rule.monthly_fraud_level, context.monthly_fraud_rate),
                matches_volume(rule.monthly_volume, context.monthly_volume),
                self._list_matches(rule.merchant_category_codes, context.merchant_category_code),
                rule.is_credit is None or rule.is_credit == context.is_credit,
                self._list_matches(rule.acis, context.aci),
                rule.intracountry is None or rule.intracountry == context.intracountry,
            )
        )

    def _matches_partial(self, rule: FeeRule, criteria: RuleCriteria) -> bool:
        checks = []
        if criteria.card_scheme is not None:
            checks.append(rule.card_scheme == criteria.card_scheme)
        if criteria.account_type is not None:
            checks.append(self._list_matches(rule.account_types, criteria.account_type))
        if criteria.capture_delay is not None:
            checks.append(matches_capture_delay(rule.capture_delay, criteria.capture_delay))
        if criteria.monthly_fraud_rate is not None:
            checks.append(matches_percentage(rule.monthly_fraud_level, criteria.monthly_fraud_rate))
        if criteria.monthly_volume is not None:
            checks.append(matches_volume(rule.monthly_volume, criteria.monthly_volume))
        if criteria.merchant_category_code is not None:
            checks.append(
                self._list_matches(rule.merchant_category_codes, criteria.merchant_category_code)
            )
        if criteria.is_credit is not None:
            checks.append(rule.is_credit is None or rule.is_credit == criteria.is_credit)
        if criteria.aci is not None:
            checks.append(self._list_matches(rule.acis, criteria.aci))
        if criteria.intracountry is not None:
            checks.append(rule.intracountry is None or rule.intracountry == criteria.intracountry)
        return all(checks)
