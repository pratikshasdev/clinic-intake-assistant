"""Every resource we build must parse as valid FHIR R4B (structurally the same as R4 for these types)."""

import pytest
from fhir.resources.R4B import get_fhir_model_class

from app.demo_patients import DEMO_PATIENTS, as_questionnaire_response
from app.extract.rules import RulesExtractor
from app.fhir_build import build_intake_bundle, quote_found
from app.fhir_ids import EXT_REVIEW_STATUS
from app.models import IntakeText
from app.questionnaire import QUESTIONNAIRE, flatten_answers


def bundle_for(key: str) -> dict:
    qr = as_questionnaire_response(DEMO_PATIENTS[key])
    answers = flatten_answers(qr)
    text = IntakeText(**{k: str(answers.get(k) or "") for k in ("reason", "medications", "allergies", "history")})
    return build_intake_bundle(qr, answers, text, RulesExtractor().extract_sync(text))


@pytest.mark.parametrize("key", list(DEMO_PATIENTS))
def test_bundle_validates(key):
    bundle = bundle_for(key)
    get_fhir_model_class("Bundle").model_validate(bundle)
    for entry in bundle["entry"]:
        resource = entry["resource"]
        get_fhir_model_class(resource["resourceType"]).model_validate(resource)


def test_questionnaire_validates():
    get_fhir_model_class("Questionnaire").model_validate(QUESTIONNAIRE)


def test_ai_items_start_unconfirmed_and_pending():
    bundle = bundle_for("maria")
    for entry in bundle["entry"]:
        r = entry["resource"]
        if r["resourceType"] in ("Condition", "AllergyIntolerance"):
            assert r["verificationStatus"]["coding"][0]["code"] == "unconfirmed"
        if r["resourceType"] in ("Condition", "AllergyIntolerance", "MedicationStatement"):
            review = next(e for e in r["extension"] if e["url"] == EXT_REVIEW_STATUS)
            assert review["valueCode"] == "pending"


def test_provenance_points_at_every_ai_item():
    bundle = bundle_for("maria")
    ai_urls = {
        e["fullUrl"]
        for e in bundle["entry"]
        if e["resource"]["resourceType"] in ("Condition", "AllergyIntolerance", "MedicationStatement")
    }
    provenance = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Provenance")
    assert {t["reference"] for t in provenance["target"]} == ai_urls


def test_quote_found_ignores_case_and_spacing():
    assert quote_found("lisinopril  10MG", "I take Lisinopril 10mg daily")
    assert not quote_found("metoprolol", "I take lisinopril")
    assert not quote_found("", "anything")
