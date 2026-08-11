"""Generate JSON Schema from the Pydantic contracts.

Blueprint §10.1: contracts are published as JSON Schema so that non-Python consumers — the AWS
ingestion pipeline, ASAP, and whoever implements this — can validate against them without
importing our package.

Run: `uv run python scripts/generate_schemas.py`
Check without writing: `uv run python scripts/generate_schemas.py --check`

`--check` is what CI runs. It fails if `schemas/` has drifted from the models, so a contract
change cannot be merged without its published schema.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ireports_domain import CONTRACT_VERSION, ROOT_CONTRACTS

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas"
SCHEMA_BASE_URI = "https://github.com/Amivero-LLC/asap-ireports/schemas"


def build_schema(stem: str, model: Any) -> dict[str, Any]:
    schema = model.model_json_schema(mode="serialization")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_BASE_URI}/{stem}.schema.json",
        "x-contract-version": CONTRACT_VERSION,
        **schema,
    }


def render(stem: str, model: Any) -> str:
    return json.dumps(build_schema(stem, model), indent=2, sort_keys=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the written schemas differ from the models.",
    )
    args = parser.parse_args()

    SCHEMA_DIR.mkdir(exist_ok=True)
    drifted: list[str] = []

    for stem, model in sorted(ROOT_CONTRACTS.items()):
        target = SCHEMA_DIR / f"{stem}.schema.json"
        rendered = render(stem, model)
        if args.check:
            if not target.exists() or target.read_text() != rendered:
                drifted.append(target.name)
        else:
            target.write_text(rendered)
            print(f"wrote {target.relative_to(REPO_ROOT)}")

    if args.check:
        if drifted:
            print(
                "schemas/ is out of date with the Pydantic models: "
                + ", ".join(drifted)
                + "\nrun: uv run python scripts/generate_schemas.py",
                file=sys.stderr,
            )
            return 1
        print(f"schemas/ is current ({len(ROOT_CONTRACTS)} contracts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
