"""Claude extractor tests with a fake API client: no network, no key."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app import models
from app.extract.claude import ClaudeExtractor, ExtractionError
from app.models import IntakeText

GOOD = {
    "visit_summary": "Here for a week-long cough.",
    "conditions": [{"name": "high blood pressure", "term_key": "hypertension", "clinical_status": "active", "source_quote": "high blood pressure"}],
    "allergies": [{"substance": "penicillin", "term_key": "penicillin", "reactions": ["hives", "made_up"], "severity": "mild", "source_quote": "penicillin gives me hives"}],
    "medications": [{"name": "Zestril", "term_key": "not_a_key", "dose": "10 mg", "frequency": "daily", "status": "active", "source_quote": "Zestril 10 mg daily"}],
    "no_known_allergies": False,
}


def fake_response(payload=None, stop_reason="end_turn", model="claude-sonnet-5-5"):
    content = [SimpleNamespace(type="text", text=json.dumps(payload))] if payload is not None else []
    return SimpleNamespace(
        content=content, stop_reason=stop_reason, stop_details=None, model=model, usage={}, _request_id="req_test"
    )


def extractor_returning(response):
    extractor = ClaudeExtractor(model="claude-sonnet-5-5", api_key="test-key")
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return response

    extractor._client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return extractor, calls


def test_parses_and_forces_unknown_keys_to_other():
    extractor, calls = extractor_returning(fake_response(GOOD))
    result = asyncio.run(extractor.extract(IntakeText(history="high blood pressure")))
    assert result.conditions[0].term_key == "hypertension"
    assert result.medications[0].term_key == "other"
    assert result.allergies[0].reactions == ["hives", "other"]
    assert result.extractor == "claude:claude-sonnet-5-5"
    request = calls[0]
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert request["fallbacks"] == "default"


def test_refusal_raises():
    extractor, _ = extractor_returning(fake_response(None, stop_reason="refusal"))
    with pytest.raises(ExtractionError):
        asyncio.run(extractor.extract(IntakeText()))


def test_schema_closes_every_object():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(models.json_schema())
