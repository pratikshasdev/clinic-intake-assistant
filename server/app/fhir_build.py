"""Build FHIR R4 resources from a QuestionnaireResponse plus an Extraction.

Everything for one intake goes to the server as a single transaction Bundle,
so either the whole intake is stored or none of it is.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from . import terminology
from .fhir_ids import (
    DEMO_TAG,
    EXT_EXTRACTOR,
    EXT_QUOTE_FOUND,
    EXT_REVIEW_STATUS,
    EXT_SOURCE_QUOTE,
    EXT_VISIT_SUMMARY,
    QUESTIONNAIRE_URL,
    REVIEW_PENDING,
)
from .models import Extraction, IntakeText

TERM = "http://terminology.hl7.org/CodeSystem"
UCUM = "http://unitsofmeasure.org"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _urn() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


def _meta() -> dict:
    return {"tag": [dict(DEMO_TAG)]}


def _coding(concept: terminology.Concept) -> dict:
    return {"system": concept.system, "code": concept.code, "display": concept.display}


def _codeable(concept: terminology.Concept | None, text: str) -> dict:
    if concept is None:
        return {"text": text}
    return {"coding": [_coding(concept)], "text": text}


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_found(quote: str, source: str) -> bool:
    """True when the model's quote really appears in what the patient wrote."""

    q = _normalize(quote)
    return bool(q) and q in _normalize(source)


def _ai_extensions(quote: str, source_text: str, extractor: str) -> list[dict]:
    return [
        {"url": EXT_REVIEW_STATUS, "valueCode": REVIEW_PENDING},
        {"url": EXT_SOURCE_QUOTE, "valueString": quote},
        {"url": EXT_QUOTE_FOUND, "valueBoolean": quote_found(quote, source_text)},
        {"url": EXT_EXTRACTOR, "valueString": extractor},
    ]


def _note(quote: str) -> list[dict]:
    return [{"text": f'Patient wrote: "{quote}". Extracted by AI, awaiting staff review.'}]


def build_patient(answers: dict[str, Any]) -> dict:
    patient: dict[str, Any] = {
        "resourceType": "Patient",
        "meta": _meta(),
        "name": [{"use": "official", "given": [answers["given-name"].strip()], "family": answers["family-name"].strip()}],
        "birthDate": answers["birth-date"],
    }
    if answers.get("gender") in {"female", "male", "other", "unknown"}:
        patient["gender"] = answers["gender"]
    if answers.get("phone"):
        patient["telecom"] = [{"system": "phone", "value": str(answers["phone"]).strip(), "use": "mobile"}]
    return patient


def build_intake_bundle(
    questionnaire_response: dict,
    answers: dict[str, Any],
    text: IntakeText,
    extraction: Extraction,
    existing_patient_id: str | None = None,
) -> dict:
    """Return a transaction Bundle holding the whole intake."""

    entries: list[dict] = []
    authored = now_iso()

    def add(resource: dict, full_url: str | None = None) -> str:
        url = full_url or _urn()
        entries.append(
            {
                "fullUrl": url,
                "resource": resource,
                "request": {"method": "POST", "url": resource["resourceType"]},
            }
        )
        return url

    if existing_patient_id:
        patient_ref = f"Patient/{existing_patient_id}"
    else:
        patient_ref = add(build_patient(answers))

    encounter = {
        "resourceType": "Encounter",
        "meta": _meta(),
        "status": "arrived",
        "class": {"system": f"{TERM}/v3-ActCode", "code": "AMB", "display": "ambulatory"},
        "subject": {"reference": patient_ref},
        "period": {"start": authored},
        "reasonCode": [{"text": text.reason.strip() or "Not given"}],
        "extension": [
            {"url": EXT_VISIT_SUMMARY, "valueString": extraction.visit_summary},
            {"url": EXT_EXTRACTOR, "valueString": extraction.extractor},
        ],
    }
    encounter_ref = add(encounter)

    qr = dict(questionnaire_response)
    qr.pop("id", None)
    qr.update(
        {
            "resourceType": "QuestionnaireResponse",
            "meta": _meta(),
            "questionnaire": QUESTIONNAIRE_URL,
            "status": "completed",
            "subject": {"reference": patient_ref},
            "encounter": {"reference": encounter_ref},
            "authored": qr.get("authored") or authored,
        }
    )
    qr_ref = add(qr)

    ai_refs: list[str] = []
    subject = {"reference": patient_ref}
    enc = {"reference": encounter_ref}

    for c in extraction.conditions:
        concept = terminology.lookup(terminology.CONDITIONS, c.term_key)
        ai_refs.append(
            add(
                {
                    "resourceType": "Condition",
                    "meta": _meta(),
                    "extension": _ai_extensions(c.source_quote, text.history + "\n" + text.reason, extraction.extractor),
                    "clinicalStatus": {
                        "coding": [{"system": f"{TERM}/condition-clinical", "code": c.clinical_status}]
                    },
                    "verificationStatus": {
                        "coding": [{"system": f"{TERM}/condition-ver-status", "code": "unconfirmed"}]
                    },
                    "category": [
                        {"coding": [{"system": f"{TERM}/condition-category", "code": "problem-list-item"}]}
                    ],
                    "code": _codeable(concept, c.name),
                    "subject": subject,
                    "encounter": enc,
                    "recordedDate": authored,
                    "note": _note(c.source_quote),
                }
            )
        )

    for a in extraction.allergies:
        concept = terminology.lookup(terminology.ALLERGENS, a.term_key)
        manifestations = [
            _codeable(terminology.lookup(terminology.REACTIONS, r), r) for r in a.reactions if r != terminology.OTHER
        ]
        resource: dict[str, Any] = {
            "resourceType": "AllergyIntolerance",
            "meta": _meta(),
            "extension": _ai_extensions(a.source_quote, text.allergies, extraction.extractor),
            "clinicalStatus": {
                "coding": [{"system": f"{TERM}/allergyintolerance-clinical", "code": "active"}]
            },
            "verificationStatus": {
                "coding": [{"system": f"{TERM}/allergyintolerance-verification", "code": "unconfirmed"}]
            },
            "code": _codeable(concept, a.substance),
            "patient": subject,
            "encounter": enc,
            "recordedDate": authored,
            "note": _note(a.source_quote),
        }
        if a.severity == "severe":
            resource["criticality"] = "high"
        if manifestations:
            reaction: dict[str, Any] = {"manifestation": manifestations}
            if a.severity != "unknown":
                reaction["severity"] = a.severity
            resource["reaction"] = [reaction]
        ai_refs.append(add(resource))

    if extraction.no_known_allergies:
        # SNOMED 716186003 |No known allergy (situation)| is the usual way to record NKA.
        ai_refs.append(
            add(
                {
                    "resourceType": "AllergyIntolerance",
                    "meta": _meta(),
                    "extension": _ai_extensions(text.allergies.strip(), text.allergies, extraction.extractor),
                    "clinicalStatus": {
                        "coding": [{"system": f"{TERM}/allergyintolerance-clinical", "code": "active"}]
                    },
                    "verificationStatus": {
                        "coding": [{"system": f"{TERM}/allergyintolerance-verification", "code": "unconfirmed"}]
                    },
                    "code": {
                        "coding": [
                            {"system": terminology.SNOMED, "code": "716186003", "display": "No known allergy"}
                        ],
                        "text": "No known allergies",
                    },
                    "patient": subject,
                    "encounter": enc,
                    "recordedDate": authored,
                }
            )
        )

    for m in extraction.medications:
        concept = terminology.lookup(terminology.MEDICATIONS, m.term_key)
        dosage_text = " ".join(part for part in [m.dose, m.frequency] if part).strip()
        resource = {
            "resourceType": "MedicationStatement",
            "meta": _meta(),
            "extension": _ai_extensions(m.source_quote, text.medications, extraction.extractor),
            "status": m.status,
            "medicationCodeableConcept": _codeable(concept, m.name),
            "subject": subject,
            "context": enc,
            "dateAsserted": authored,
            "informationSource": subject,
            "note": _note(m.source_quote),
        }
        if dosage_text:
            resource["dosage"] = [{"text": dosage_text}]
        ai_refs.append(add(resource))

    # Patient-reported structured answers: no AI involved, so no review needed.
    for obs in _observations(answers, subject, enc, authored):
        add(obs)

    if ai_refs:
        add(
            {
                "resourceType": "Provenance",
                "meta": _meta(),
                "target": [{"reference": ref} for ref in ai_refs],
                "recorded": authored,
                "activity": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-DataOperation", "code": "CREATE"}]
                },
                "agent": [
                    {
                        "type": {
                            "coding": [
                                {"system": f"{TERM}/provenance-participant-type", "code": "assembler", "display": "Assembler"}
                            ]
                        },
                        "who": {"display": f"Clinic intake assistant ({extraction.extractor})"},
                    }
                ],
                "entity": [{"role": "source", "what": {"reference": qr_ref}}],
            }
        )

    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}


def _observations(answers: dict[str, Any], subject: dict, enc: dict, when: str) -> list[dict]:
    def base(code: tuple[str, str], category: str) -> dict:
        return {
            "resourceType": "Observation",
            "meta": _meta(),
            "status": "final",
            "category": [{"coding": [{"system": f"{TERM}/observation-category", "code": category}]}],
            "code": {"coding": [{"system": terminology.LOINC, "code": code[0], "display": code[1]}], "text": code[1]},
            "subject": subject,
            "encounter": enc,
            "effectiveDateTime": when,
            "performer": [subject],
        }

    out: list[dict] = []
    smoking = terminology.SMOKING_STATUS_ANSWERS.get(answers.get("smoking") or "")
    if smoking:
        o = base(terminology.LOINC_SMOKING_STATUS, "social-history")
        o["valueCodeableConcept"] = _codeable(smoking, smoking.display)
        out.append(o)
    pain = answers.get("pain-score")
    if isinstance(pain, int) and 0 <= pain <= 10:
        o = base(terminology.LOINC_PAIN_SEVERITY, "survey")
        o["valueInteger"] = pain
        out.append(o)
    weight = answers.get("weight-lb")
    if isinstance(weight, (int, float)) and 0 < weight < 1500:
        o = base(terminology.LOINC_BODY_WEIGHT, "vital-signs")
        o["valueQuantity"] = {"value": float(weight), "unit": "lb", "system": UCUM, "code": "[lb_av]"}
        out.append(o)
    return out
