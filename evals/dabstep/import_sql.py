from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from evals.dabstep.common import LOCK_PATH, default_data_dir, load_json, verify_files

TABLE_ORDER = (
    "payments",
    "merchants",
    "merchant_acquirers",
    "acquirer_countries",
    "merchant_category_codes",
    "fee_rules",
    "fee_rule_account_types",
    "fee_rule_mccs",
    "fee_rule_acis",
    "dataset_files",
)


def _json_compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_frames(data_dir: Path) -> dict[str, pd.DataFrame]:
    errors = verify_files(data_dir)
    if errors:
        raise RuntimeError("locked dataset verification failed:\n" + "\n".join(errors))

    context = data_dir / "context"
    payments = pd.read_csv(context / "payments.csv")
    dates = pd.to_datetime(payments["year"].astype(str), format="%Y") + pd.to_timedelta(
        payments["day_of_year"] - 1, unit="D"
    )
    payments["transaction_date"] = dates.dt.strftime("%Y-%m-%d")
    payments["transaction_month"] = dates.dt.strftime("%Y-%m")
    payments["intracountry"] = (payments["issuing_country"] == payments["acquirer_country"]).astype(
        int
    )
    for column in ("is_credit", "has_fraudulent_dispute", "is_refused_by_adyen"):
        payments[column] = payments[column].astype(int)

    merchant_records = load_json(context / "merchant_data.json")
    merchants = pd.DataFrame(
        {key: value for key, value in record.items() if key != "acquirer"}
        for record in merchant_records
    )
    merchant_acquirers = pd.DataFrame(
        {"merchant": record["merchant"], "acquirer": acquirer}
        for record in merchant_records
        for acquirer in record["acquirer"]
    )

    acquirer_countries = pd.read_csv(context / "acquirer_countries.csv").drop(
        columns=["Unnamed: 0"], errors="ignore"
    )
    merchant_category_codes = pd.read_csv(context / "merchant_category_codes.csv").drop(
        columns=["Unnamed: 0"], errors="ignore"
    )

    fee_records = load_json(context / "fees.json")
    fee_rules = pd.DataFrame(fee_records)
    for column in ("account_type", "merchant_category_code", "aci"):
        fee_rules[column] = fee_rules[column].map(_json_compact)
    fee_rules["is_credit"] = fee_rules["is_credit"].map(
        lambda value: None if pd.isna(value) else int(value)
    )
    fee_rules["intracountry"] = fee_rules["intracountry"].map(
        lambda value: None if pd.isna(value) else int(value)
    )
    fee_rule_account_types = pd.DataFrame(
        {"fee_id": record["ID"], "account_type": value}
        for record in fee_records
        for value in record["account_type"]
    )
    fee_rule_mccs = pd.DataFrame(
        {"fee_id": record["ID"], "mcc": value}
        for record in fee_records
        for value in record["merchant_category_code"]
    )
    fee_rule_acis = pd.DataFrame(
        {"fee_id": record["ID"], "aci": value} for record in fee_records for value in record["aci"]
    )

    lock = load_json(LOCK_PATH)
    dataset_files = pd.DataFrame(
        {
            "dataset": lock["dataset"],
            "revision": lock["revision"],
            "path": item["path"],
            "bytes": item["bytes"],
            "sha256": item["sha256"],
        }
        for item in lock["files"]
    )
    return {
        "payments": payments,
        "merchants": merchants,
        "merchant_acquirers": merchant_acquirers,
        "acquirer_countries": acquirer_countries,
        "merchant_category_codes": merchant_category_codes,
        "fee_rules": fee_rules,
        "fee_rule_account_types": fee_rule_account_types,
        "fee_rule_mccs": fee_rule_mccs,
        "fee_rule_acis": fee_rule_acis,
        "dataset_files": dataset_files,
    }


def import_database(data_dir: Path, database_url: str) -> None:
    frames = build_frames(data_dir)
    engine = create_engine(database_url)
    try:
        for table in TABLE_ORDER:
            frame = frames[table]
            print(f"importing {table}: {len(frame)} rows")
            frame.to_sql(table, engine, if_exists="replace", index=False, chunksize=5000)

        if engine.dialect.name == "sqlite":
            indexes = (
                "CREATE UNIQUE INDEX idx_payments_psp_reference ON payments(psp_reference)",
                "CREATE INDEX idx_payments_merchant_month ON payments(merchant, transaction_month)",
                "CREATE INDEX idx_payments_scheme_aci ON payments(card_scheme, aci)",
                "CREATE UNIQUE INDEX idx_merchants_name ON merchants(merchant)",
                "CREATE UNIQUE INDEX idx_fee_rules_id ON fee_rules(ID)",
            )
            with engine.begin() as connection:
                for statement in indexes:
                    connection.execute(text(statement))
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import pinned DABStep data into SQL.")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument(
        "--database-url",
        default=os.getenv("DABSTEP_DATABASE_URL", "sqlite:///evals/dabstep/work/dabstep.sqlite"),
        help="SQLAlchemy URL. Defaults to a local SQLite database; MySQL is also supported.",
    )
    args = parser.parse_args()
    if args.database_url.startswith("sqlite:///"):
        sqlite_path = Path(args.database_url.removeprefix("sqlite:///"))
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    import_database(args.data_dir, args.database_url)
    print(f"import complete: {args.database_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
