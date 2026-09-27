from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.dabstep.audit_dataset import audit, render_markdown
from evals.dabstep.common import HERE, default_data_dir
from evals.dabstep.download_adyen_dev import DEFAULT_PATH as ADYEN_DEV_PATH
from evals.dabstep.download_adyen_dev import download as download_adyen_dev
from evals.dabstep.download_dataset import download
from evals.dabstep.import_sql import import_database
from evals.dabstep.validate_fee_engine import REFERENCE_PATH as FEE_REFERENCE_PATH
from evals.dabstep.validate_fee_engine import build_reference as build_fee_reference
from evals.dabstep.verify_reference import EXPECTED_PATH, collect


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare and verify the pinned DABStep baseline.")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--database-url", default="sqlite:///evals/dabstep/work/dabstep.sqlite")
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()

    if not args.skip_download:
        download(args.data_dir)
        download_adyen_dev(ADYEN_DEV_PATH)

    result, selected = audit(args.data_dir)
    (HERE / "audit_snapshot.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (HERE / "AUDIT.md").write_text(render_markdown(result), encoding="utf-8")
    (HERE / "selected_tasks.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected),
        encoding="utf-8",
    )

    if args.database_url.startswith("sqlite:///"):
        Path(args.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    import_database(args.data_dir, args.database_url)
    if collect(args.database_url) != json.loads(EXPECTED_PATH.read_text(encoding="utf-8")):
        raise RuntimeError("SQL import does not match the committed reference results")
    fee_reference = build_fee_reference(
        args.data_dir,
        ADYEN_DEV_PATH,
        database_url=args.database_url,
    )
    if fee_reference != json.loads(FEE_REFERENCE_PATH.read_text(encoding="utf-8")):
        raise RuntimeError("fee engine does not match the committed fee reference results")
    print("DABStep baseline is prepared and verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
