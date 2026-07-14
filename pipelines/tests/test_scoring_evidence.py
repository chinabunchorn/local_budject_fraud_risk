"""Evidence assembly — the regulation-id extraction is pure; the full assembly
is checked against the real ingested corpus (skips cleanly when it is absent)."""

import pytest
from sqlalchemy import text

from common.prompts import load_risk_scoring
from common.scoring_evidence import assemble_evidence, regulation_ids_in


def test_regulation_ids_pulled_from_factor_templates():
    ids = regulation_ids_in(load_risk_scoring("v1"))
    assert "fiscal-discipline-act-2561/s.37" in ids
    assert all("/" in code for code in ids)
    assert ids == sorted(set(ids))  # deduped + stable order


class TestAssembleAgainstRealCorpus:
    @pytest.fixture()
    def scored_project(self, engine):
        with engine.connect() as conn:
            pid = conn.execute(
                text("SELECT project_id FROM precheck_results ORDER BY project_id LIMIT 1")
            ).scalar()
        if pid is None:
            pytest.skip("no extracted projects — run flows.extract_structured first")
        return str(pid)

    def test_evidence_carries_citable_chunks_regs_and_prechecks(self, engine, scored_project):
        bundle = load_risk_scoring("v1")
        ev = assemble_evidence(engine, scored_project, bundle)
        assert ev is not None
        # real chunk_ids so the model's citations resolve at guardrails time
        assert "[chunk_id:" in ev.document_excerpts
        # regulation context labelled with guardrails-resolvable ids
        assert "[regulation_id: fiscal-discipline-act-2561/s.37]" in ev.regulation_context
        # the deterministic pre-check findings are handed to the model as evidence
        assert "ตรวจสอบเชิงกฎเกณฑ์อัตโนมัติ" in ev.budget_lines
        assert "ราคากลาง" in ev.budget_lines
