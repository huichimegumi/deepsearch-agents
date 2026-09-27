from decimal import Decimal

from app.research.fee_engine import (
    EmptyListPolicy,
    FeeEngine,
    FeeMatchStatus,
    FeeRule,
    RuleCriteria,
    TransactionContext,
)
from app.research.fee_engine.ranges import (
    matches_capture_delay,
    matches_percentage,
    matches_volume,
)


def _rule(**overrides) -> FeeRule:
    values = {
        "ID": 10,
        "card_scheme": "GlobalCard",
        "account_type": [],
        "capture_delay": None,
        "monthly_fraud_level": None,
        "monthly_volume": None,
        "merchant_category_code": [],
        "is_credit": None,
        "aci": [],
        "fixed_amount": "0.10",
        "rate": "25",
        "intracountry": None,
    }
    values.update(overrides)
    return FeeRule.from_mapping(values)


def _context(**overrides) -> TransactionContext:
    values = {
        "merchant": "Merchant",
        "year": 2023,
        "month": 1,
        "card_scheme": "GlobalCard",
        "account_type": "H",
        "capture_delay": "2",
        "monthly_fraud_rate": Decimal("0.075"),
        "monthly_volume": Decimal("250000"),
        "merchant_category_code": 5812,
        "is_credit": True,
        "aci": "B",
        "intracountry": True,
    }
    values.update(overrides)
    return TransactionContext(**values)


def test_documented_range_boundaries_are_deterministic():
    assert matches_volume("100k-1m", Decimal("100000"))
    assert matches_volume("100k-1m", Decimal("1000000"))
    assert matches_volume(">5m", Decimal("5000000.01"))
    assert not matches_volume(">5m", Decimal("5000000"))
    assert matches_percentage("7.2%-7.7%", Decimal("0.072"))
    assert matches_percentage("7.2%-7.7%", Decimal("0.077"))
    assert matches_capture_delay("<3", "2")
    assert not matches_capture_delay("<3", "manual")
    assert matches_capture_delay("manual", "manual")


def test_empty_lists_match_as_wildcards_and_are_disclosed():
    engine = FeeEngine([_rule()])
    result = engine.calculate(
        psp_reference="p1",
        amount=Decimal("10"),
        context=_context(),
    )

    assert result.status is FeeMatchStatus.MATCHED
    assert result.matched_fee_rule_ids == (10,)
    assert result.total_fee == Decimal("0.125")
    assert result.assumptions
    assert result.components[0].provenance.source_locator == "fees.json#ID=10"
    assert set(result.components[0].provenance.wildcard_conditions) >= {
        "account_type",
        "merchant_category_code",
        "aci",
    }
    serialized = result.to_dict()
    assert serialized["status"] == "MATCHED"
    assert serialized["total_fee"] == "0.125"
    assert serialized["components"][0]["provenance"]["source_locator"] == "fees.json#ID=10"


def test_ambiguous_and_reject_empty_list_policies_are_explicit():
    ambiguous = FeeEngine([_rule()], empty_list_policy=EmptyListPolicy.AMBIGUOUS)
    rejected = FeeEngine([_rule()], empty_list_policy=EmptyListPolicy.REJECT)

    assert (
        ambiguous.calculate(psp_reference="p1", amount=Decimal("1"), context=_context()).status
        is FeeMatchStatus.AMBIGUOUS_SEMANTICS
    )
    assert (
        rejected.calculate(psp_reference="p1", amount=Decimal("1"), context=_context()).status
        is FeeMatchStatus.NO_MATCH
    )


def test_all_rule_dimensions_must_match():
    rule = _rule(
        account_type=["H"],
        capture_delay="<3",
        monthly_fraud_level="7.2%-7.7%",
        monthly_volume="100k-1m",
        merchant_category_code=[5812],
        is_credit=True,
        aci=["B"],
        intracountry=True,
    )
    engine = FeeEngine([rule])

    assert engine.matcher.applicable_rules(_context()) == (rule,)
    assert not engine.matcher.applicable_rules(_context(aci="A"))
    assert not engine.matcher.applicable_rules(_context(monthly_volume=Decimal("1000000.01")))


def test_partial_criteria_ignore_unspecified_dimensions():
    matching = _rule(account_type=["R"], aci=["B"], capture_delay=">5")
    other = _rule(ID=11, account_type=["H"], aci=["B"])
    engine = FeeEngine([matching, other])

    assert engine.matcher.filter_rules(RuleCriteria(account_type="R", aci="B")) == (matching,)


def test_invalid_source_data_is_not_silently_priced():
    result = FeeEngine([_rule()]).calculate(
        psp_reference="p1",
        amount=Decimal("10"),
        context=_context(monthly_fraud_rate=Decimal("1.2")),
    )

    assert result.status is FeeMatchStatus.INVALID_SOURCE_DATA
    assert result.total_fee == 0
    assert result.error
