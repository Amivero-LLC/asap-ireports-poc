"""Index the synthetic cases into local OpenSearch.

    docker compose -f infrastructure/docker/compose.yaml up -d
    uv run --env-file .env python spikes/lambda_demo/index_cases.py

Costs a few embedding calls per case — cheap (input tokens only), but not free, so it is a
separate script rather than something a run does implicitly.

**This is a development convenience, not the production indexer.** AWS owns chunking and embedding
in production (ADR-007); this exists so a developer has something to query.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ireports_gateway import build_embedding_gateway
from ireports_retrieval import IndexableSpan, connect, index_case
from lambda_demo.case_loader import available_cases, load_case

CASES_DIR = Path(__file__).resolve().parent / "cases"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_ids", nargs="*", help="default: every case on disk")
    args = parser.parse_args()

    client = connect()
    embedder = build_embedding_gateway()

    for case_id in args.case_ids or available_cases(CASES_DIR):
        case = load_case(CASES_DIR / case_id)
        spans = tuple(
            IndexableSpan(
                evidence_id=s.evidence_id,
                document_id=s.document_id,
                title=s.title,
                text=s.text,
                page_number=s.page_number,
                source_type=s.source_type,
            )
            for s in case.spans
        )
        result = index_case(client, embedder, case_id=case_id, spans=spans)
        print(
            f"{case_id}: {result.documents} spans -> {result.index} "
            f"({result.embedding_model}, {result.dimensions}d, {result.total_tokens:,} tokens)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
