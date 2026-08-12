"""What the *wrapper* claims, checked offline.

This spike is no longer where the analysis lives. Criteria selection, specialists, synthesis and
both orchestrators graduated to `packages/orchestration/`, and their tests went with them to
`tests/orchestration/`. What remains here is the runnable shell around them — reading a case off
disk, building the envelope, and the Lambda handler — and that is what this file tests.

Everything runs against `StubGateway`, so it is free, deterministic, and safe in CI. The live half
is `run_case.py`, which is opt-in and costs money.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from ireports_domain import ASAPEnvelope, FindingClassification
from ireports_gateway import StubGateway
from ireports_orchestration import CATALOG, ORCHESTRATORS
from ireports_retrieval import InMemoryRetriever, RetrievedSpan
from lambda_demo import handler as handler_module
from lambda_demo.case_loader import load_case
from lambda_demo.package import build_envelope

CASE_DIR = Path(__file__).parent / "cases" / "AMI-SYN-FIN-001"
RUN_ID = "run_test_0001"


@pytest.fixture
def case():
    return load_case(CASE_DIR)


@pytest.fixture
def retriever(case):
    """Every span, ignoring the query — offline and free. Not a retriever; see
    `tests/orchestration/test_orchestration.py`, which says the same thing at more length."""
    return InMemoryRetriever(
        tuple(
            RetrievedSpan(
                evidence_id=s.evidence_id,
                document_id=s.document_id,
                title=s.title,
                text=s.text,
                page_number=s.page_number,
                source_type=s.source_type,
                score=1.0,
            )
            for s in case.spans
        )
    )


def _finding(**overrides: Any) -> dict[str, Any]:
    """A well-formed finding as a model would emit it, before any override."""
    base: dict[str, Any] = {
        "title": "Foreign family contact reported in the questionnaire",
        "observation": "The record shows regular contact with a parent residing abroad [ev_001].",
        "policy_relevance": "Contact with foreign nationals may be relevant to this criterion.",
        "recommended_officer_action": "Review the reported contact and confirm its frequency.",
        "supporting_evidence": ["ev_001"],
        "mitigating_evidence": ["ev_002"],
        "information_gaps": [],
        "evidence_confidence": "moderate",
        "analysis_confidence": "moderate",
    }
    base.update(overrides)
    return base


def _gateway(*findings: dict[str, Any]) -> StubGateway:
    return StubGateway(default=json.dumps({"findings": list(findings)}))


# ---------------------------------------------------------------------------
# Loading a case off disk
# ---------------------------------------------------------------------------


def test_the_case_loader_is_the_only_thing_here_that_knows_about_files() -> None:
    """The boundary this spike exists to hold after the graduation.

    `ireports_orchestration` owns the types; this package owns reading them off a disk, because
    where a case comes from is a property of the deployment (ADR-007). A `Path` or an `open()`
    appearing in the analysis package would put the AWS ingestion path one refactor away.
    """
    package = Path(__file__).parent / "src" / "lambda_demo"
    filesystem_aware = {
        module.name
        for module in package.glob("*.py")
        if "pathlib" in module.read_text() or "open(" in module.read_text()
    }
    assert filesystem_aware <= {"case_loader.py", "handler.py"}, sorted(filesystem_aware)


def test_a_case_with_duplicate_evidence_ids_is_refused(tmp_path: Path) -> None:
    """Ambiguous citations are worse than missing ones: every downstream check would pass."""
    (tmp_path / "case.json").write_text((CASE_DIR / "case.json").read_text())
    spans = json.loads((CASE_DIR / "evidence.json").read_text())["spans"]
    (tmp_path / "evidence.json").write_text(json.dumps({"spans": [spans[0], spans[0]]}))

    with pytest.raises(ValueError, match="duplicate evidence_id"):
        load_case(tmp_path)


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------


def test_envelope_is_machine_generated_and_unreviewed(case, retriever) -> None:
    """ADR-022: iReports emits proposals and records no human decision, ever."""
    result = ORCHESTRATORS["hand-rolled"].run(case, _gateway(_finding()), retriever, RUN_ID)
    envelope = build_envelope(case, result.findings, RUN_ID)

    assert envelope.analysis.machine_generated is True
    dumped = envelope.model_dump(mode="json")
    assert ASAPEnvelope.model_validate(dumped)

    flat = json.dumps(dumped)
    for forbidden in ("disposition", "approval", "human_reviewed", "release_to_asap", "sign_off"):
        assert forbidden not in flat, (
            f"the envelope carries a {forbidden!r} field. No contract in this system models a "
            "human decision — review happens in ASAP (ADR-022)."
        )


def test_no_findings_means_no_envelope(case) -> None:
    """An empty envelope would deliver 'nothing found' as though it were a result."""
    with pytest.raises(ValueError, match="no findings survived"):
        build_envelope(case, (), RUN_ID)


def test_synthesis_findings_reach_the_envelope(case, retriever) -> None:
    """A cross-criterion finding is a `ProposedFinding` like any other, and is delivered like one.

    Giving synthesis a privileged section in the envelope would imply its findings carry more
    weight than a specialist's. They do not.
    """
    gateway = StubGateway(
        responses={
            "synthesis": json.dumps(
                {
                    "contradictions": [
                        {
                            "title": "SF-86 answer conflicts with the interview disclosure",
                            "observation": "The questionnaire records 'No' (ev_003); the interview "
                            "records a 4 percent interest (ev_004). Both cannot describe the same "
                            "holding.",
                            "policy_relevance": "The conflict may be relevant to what the record "
                            "establishes.",
                            "recommended_officer_action": "Review both statements and resolve "
                            "which is accurate.",
                            "criterion_id": "731-202-B-3",
                            "conflicting_evidence": ["ev_003", "ev_004"],
                        }
                    ],
                    "information_gaps": [],
                }
            )
        },
        default=json.dumps({"findings": [_finding()]}),
    )
    result = ORCHESTRATORS["hand-rolled"].run(case, gateway, retriever, RUN_ID)
    envelope = build_envelope(case, result.findings, RUN_ID)

    delivered = {f.finding_id for f in envelope.analysis.findings}
    contradictions = [
        f for f in result.findings if f.classification is FindingClassification.CONTRADICTION
    ]
    assert len(contradictions) == 1
    assert contradictions[0].finding_id in delivered
    assert ASAPEnvelope.model_validate(envelope.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# The handler
# ---------------------------------------------------------------------------


def test_handler_rejects_a_run_id_without_the_prefix(monkeypatch) -> None:
    """The gotcha that cost the most time, made loud.

    A `run_id` missing its `run_` prefix does not fail at the top — it fails on every *finding*,
    because `finding_id` embeds it. The run burns three model calls and reports zero findings,
    which reads exactly like model nondeterminism. Catching it at the door is worth a test.
    """
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    with pytest.raises(ValueError, match="must start with 'run_'"):
        handler_module.handler({"case_id": CASE_DIR.name, "run_id": "demo_langgraph"})


def test_handler_refuses_a_candidate_it_was_not_packaged_for() -> None:
    """Each package holds only its own candidate's dependencies, so this cannot be served."""
    other = "langgraph" if handler_module.CANDIDATE != "langgraph" else "hand-rolled"
    with pytest.raises(ValueError, match="invoke the other function"):
        handler_module.handler({"case_id": "AMI-SYN-FIN-001", "candidate": other})


def _offline_retrieval(monkeypatch, retriever) -> None:
    """Stop the handler reaching a real OpenSearch.

    The handler builds its own retriever, so an un-patched handler test silently opened a
    connection to the local cluster — which made an "offline" test depend on a running container
    and on whatever happened to be indexed in it. It passed or failed based on the state of a
    Docker volume. Both the client and the embedder are replaced here.
    """
    monkeypatch.setattr("ireports_retrieval.connect", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(
        "ireports_retrieval.OpenSearchRetriever", lambda *a, **k: retriever, raising=True
    )
    monkeypatch.setattr(
        "ireports_gateway.build_embedding_gateway", lambda *a, **k: None, raising=True
    )


def test_handler_returns_an_envelope(monkeypatch, retriever) -> None:
    """The whole path, offline: event in, validated envelope out."""
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    _offline_retrieval(monkeypatch, retriever)
    monkeypatch.setattr(
        "ireports_gateway.build_gateway", lambda *a, **k: _gateway(_finding()), raising=True
    )

    payload = handler_module.handler({"case_id": CASE_DIR.name, "run_id": RUN_ID})

    assert payload["run_id"] == RUN_ID
    assert payload["findings"] == len(CATALOG)  # this case selects the whole catalog
    assert ASAPEnvelope.model_validate(payload["envelope"])


def test_handler_reports_an_empty_run_rather_than_crashing(monkeypatch, retriever) -> None:
    """A run where nothing survives validation still has to return its rejection record.

    That record is the only explanation of *why* nothing survived. Raising here would discard it
    and, under Lambda, trigger an automatic retry that pays for the same model calls again.
    """
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    _offline_retrieval(monkeypatch, retriever)
    monkeypatch.setattr(
        "ireports_gateway.build_gateway",
        lambda *a, **k: _gateway(_finding(supporting_evidence=["ev_999"])),
        raising=True,
    )

    payload = handler_module.handler({"case_id": CASE_DIR.name, "run_id": RUN_ID})

    assert payload["envelope"] is None
    assert "no findings survived" in payload["envelope_error"]
    assert payload["rejected"]


# ---------------------------------------------------------------------------
# The Lambda package
# ---------------------------------------------------------------------------


def test_build_stages_every_package_the_handler_imports() -> None:
    """A package staged short one dependency fails at *import time inside the container*.

    `build.py` copies our pure-Python packages in by path rather than pip-installing them, so
    adding a package to the workspace does not add it to the Lambda build. Graduating orchestration
    out of this spike is exactly the change that could have missed it — the demo would still pass
    every test here and fail on the first `sam local invoke`.

    Loaded by explicit path rather than `import build`: `spikes/lambda_fit/` has a `build.py` too,
    and which one a bare import resolves to depends on how pytest happened to order sys.path.
    """
    spec = importlib.util.spec_from_file_location(
        "lambda_demo_build", Path(__file__).parent / "build.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    staged = {name for _src, name in module.SHARED_SOURCE}
    assert staged >= {
        "ireports_domain",
        "ireports_gateway",
        "ireports_orchestration",
        "ireports_retrieval",
        "lambda_demo",
    }
    for src, _name in module.SHARED_SOURCE:
        assert src.is_dir(), f"{src} is staged by build.py and does not exist"
