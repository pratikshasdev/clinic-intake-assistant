"""The intake workflow: submit, list arrivals, review AI-extracted items."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import fhir_build
from .extract.base import Extractor
from .extract.claude import ExtractionError
from .extract.rules import RulesExtractor
from .fhir_ids import (
    DEMO_TAG,
    EXT_EXTRACTOR,
    EXT_QUOTE_FOUND,
    EXT_REVIEW_STATUS,
    EXT_SOURCE_QUOTE,
    EXT_VISIT_SUMMARY,
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
)
from .fhir_store import FhirStore, demo_tag_param
from .models import IntakeText
from .questionnaire import flatten_answers, required_link_ids

log = logging.getLogger(__name__)

TERM = "http://terminology.hl7.org/CodeSystem"
REVIEWABLE = {"Condition", "AllergyIntolerance", "MedicationStatement"}
ENCOUNTER_FIELD = {
    "Condition": "encounter",
    "AllergyIntolerance": "encounter",
    "MedicationStatement": "context",
    "Observation": "encounter",
}


class IntakeError(ValueError):
    pass


def _ext(resource: dict, url: str) -> Any:
    for e in resource.get("extension", []):
        if e.get("url") == url:
            for k, v in e.items():
                if k.startswith("value"):
                    return v
    return None


def _set_ext(resource: dict, url: str, key: str, value: Any) -> None:
    exts = [e for e in resource.get("extension", []) if e.get("url") != url]
    exts.append({"url": url, key: value})
    resource["extension"] = exts


def _first_coding(concept: dict | None) -> dict | None:
    codings = (concept or {}).get("coding") or []
    if not codings:
        return None
    c = codings[0]
    return {"system": c.get("system"), "code": c.get("code"), "display": c.get("display")}


def _age(birth_date: str | None) -> int | None:
    try:
        born = date.fromisoformat(birth_date or "")
    except ValueError:
        return None
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class IntakeService:
    def __init__(self, store: FhirStore, extractor: Extractor):
        self.store = store
        self.extractor = extractor

    # ---- submit -------------------------------------------------------------

    async def submit(self, questionnaire_response: dict) -> dict:
        if questionnaire_response.get("resourceType") != "QuestionnaireResponse":
            raise IntakeError("Body must be a FHIR QuestionnaireResponse")
        answers = flatten_answers(questionnaire_response)
        missing = [link for link in required_link_ids() if not str(answers.get(link) or "").strip()]
        if missing:
            raise IntakeError(f"Missing required answers: {', '.join(missing)}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(answers["birth-date"])):
            raise IntakeError("birth-date must be YYYY-MM-DD")

        text = IntakeText(
            reason=str(answers.get("reason") or ""),
            medications=str(answers.get("medications") or ""),
            allergies=str(answers.get("allergies") or ""),
            history=str(answers.get("history") or ""),
        )
        try:
            extraction = await self.extractor.extract(text)
        except ExtractionError as exc:
            # Never lose a patient's intake because the model call failed:
            # fall back to the offline extractor and say so on every record.
            log.warning("AI extraction failed, using rules fallback: %s", exc)
            extraction = RulesExtractor().extract_sync(text)
            extraction = extraction.model_copy(update={"extractor": f"rules-baseline (fallback: {exc})"})

        existing = await self.store.search(
            "Patient",
            {
                "_tag": demo_tag_param(),
                "family": answers["family-name"].strip(),
                "given": answers["given-name"].strip(),
                "birthdate": answers["birth-date"],
            },
        )
        patient_id = existing[0]["id"] if existing else None

        bundle = fhir_build.build_intake_bundle(questionnaire_response, answers, text, extraction, patient_id)
        refs = await self.store.transaction(bundle)
        encounter_ref = next(r for r in refs if r.startswith("Encounter/"))
        patient_ref = f"Patient/{patient_id}" if patient_id else next(r for r in refs if r.startswith("Patient/"))
        return {
            "encounter_id": encounter_ref.split("/")[1],
            "patient_id": patient_ref.split("/")[1],
            "returning_patient": patient_id is not None,
            "extractor": extraction.extractor,
            "items_for_review": len(extraction.conditions) + len(extraction.allergies) + len(extraction.medications)
            + (1 if extraction.no_known_allergies else 0),
            "resources_written": len(refs),
        }

    # ---- read ---------------------------------------------------------------

    async def _recent(self, resource_type: str, since: str, extra: dict[str, str] | None = None) -> list[dict]:
        params = {"_tag": demo_tag_param(), "_lastUpdated": f"ge{since}", "_count": "500"}
        params.update(extra or {})
        return await self.store.search(resource_type, params)

    async def list_arrivals(self, hours: int = 24, include_resources: bool = False) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        encounters = await self.store.search(
            "Encounter",
            {"_tag": demo_tag_param(), "_lastUpdated": f"ge{since}", "_sort": "-_lastUpdated", "_count": "50"},
        )
        if not encounters:
            return []
        patient_ids = sorted({e["subject"]["reference"].split("/")[1] for e in encounters})
        patients = {p["id"]: p for p in await self.store.search("Patient", {"_id": ",".join(patient_ids)})}

        by_encounter: dict[str, list[dict]] = {}
        for rtype, field in ENCOUNTER_FIELD.items():
            for resource in await self._recent(rtype, since):
                ref = (resource.get(field) or {}).get("reference", "")
                by_encounter.setdefault(ref, []).append(resource)

        arrivals = [
            self._arrival_view(e, patients.get(e["subject"]["reference"].split("/")[1]), by_encounter.get(f"Encounter/{e['id']}", []), include_resources)
            for e in encounters
        ]
        arrivals.sort(key=lambda a: a["arrived_at"] or "", reverse=True)
        return arrivals

    async def get_arrival(self, encounter_id: str) -> dict:
        encounter = await self.store.read("Encounter", encounter_id)
        patient = await self.store.read("Patient", encounter["subject"]["reference"].split("/")[1])
        related: list[dict] = []
        for rtype, field in ENCOUNTER_FIELD.items():
            for resource in await self.store.search(rtype, {"patient": f"Patient/{patient['id']}", "_count": "500"}):
                if (resource.get(field) or {}).get("reference") == f"Encounter/{encounter_id}":
                    related.append(resource)
        qr = [
            r
            for r in await self.store.search("QuestionnaireResponse", {"subject": f"Patient/{patient['id']}", "_count": "50"})
            if (r.get("encounter") or {}).get("reference") == f"Encounter/{encounter_id}"
        ]
        view = self._arrival_view(encounter, patient, related, include_resources=True)
        view["resources"] = [patient, encounter, *qr, *related]
        return view

    def _arrival_view(self, encounter: dict, patient: dict | None, related: list[dict], include_resources: bool) -> dict:
        items = [self.item_view(r) for r in related if r["resourceType"] in REVIEWABLE]
        observations = [self._observation_view(r) for r in related if r["resourceType"] == "Observation"]
        order = {"AllergyIntolerance": 0, "MedicationStatement": 1, "Condition": 2}
        items.sort(key=lambda i: (order[i["resource_type"]], i["label"].lower()))
        counts = {s: sum(1 for i in items if i["review_status"] == s) for s in (REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED)}
        name = (patient or {}).get("name", [{}])[0]
        phone = next((t.get("value") for t in (patient or {}).get("telecom", []) if t.get("system") == "phone"), None)
        view = {
            "encounter_id": encounter["id"],
            "status": encounter.get("status"),
            "arrived_at": (encounter.get("period") or {}).get("start"),
            "reason": ((encounter.get("reasonCode") or [{}])[0]).get("text"),
            "visit_summary": _ext(encounter, EXT_VISIT_SUMMARY),
            "extractor": _ext(encounter, EXT_EXTRACTOR),
            "patient": {
                "id": (patient or {}).get("id"),
                "name": " ".join([*name.get("given", []), name.get("family", "")]).strip() or "Unknown",
                "birth_date": (patient or {}).get("birthDate"),
                "age": _age((patient or {}).get("birthDate")),
                "gender": (patient or {}).get("gender"),
                "phone": phone,
            },
            "counts": counts,
            "items": items,
            "observations": observations,
        }
        if include_resources:
            view["resource_refs"] = [f"{r['resourceType']}/{r['id']}" for r in related]
        return view

    @staticmethod
    def item_view(resource: dict) -> dict:
        rtype = resource["resourceType"]
        if rtype == "Condition":
            concept = resource.get("code") or {}
            kind = "condition"
            clinical = _first_coding(resource.get("clinicalStatus")) or {}
            detail = "Past" if clinical.get("code") == "resolved" else "Current"
        elif rtype == "AllergyIntolerance":
            concept = resource.get("code") or {}
            kind = "allergy"
            reactions = [
                (m.get("text") or (_first_coding(m) or {}).get("display") or "")
                for r in resource.get("reaction", [])
                for m in r.get("manifestation", [])
            ]
            severity = next((r.get("severity") for r in resource.get("reaction", []) if r.get("severity")), None)
            if resource.get("criticality") == "high":
                severity = "high risk"
            detail = ", ".join(x for x in [", ".join(reactions), severity] if x)
        else:
            concept = resource.get("medicationCodeableConcept") or {}
            kind = "medication"
            dosage = " ".join(d.get("text", "") for d in resource.get("dosage", []))
            status = resource.get("status")
            detail = " · ".join(x for x in [dosage, "stopped" if status == "stopped" else ""] if x)
        return {
            "resource_type": rtype,
            "id": resource["id"],
            "kind": kind,
            "label": concept.get("text") or (_first_coding(concept) or {}).get("display") or "Unnamed",
            "code": _first_coding(concept),
            "detail": detail,
            "source_quote": _ext(resource, EXT_SOURCE_QUOTE),
            "quote_found": _ext(resource, EXT_QUOTE_FOUND),
            "review_status": _ext(resource, EXT_REVIEW_STATUS) or REVIEW_PENDING,
        }

    @staticmethod
    def _observation_view(resource: dict) -> dict:
        label = (resource.get("code") or {}).get("text") or "Observation"
        if "valueQuantity" in resource:
            q = resource["valueQuantity"]
            value = f"{q.get('value'):g} {q.get('unit', '')}".strip()
        elif "valueInteger" in resource:
            value = f"{resource['valueInteger']} / 10"
        elif "valueCodeableConcept" in resource:
            value = resource["valueCodeableConcept"].get("text") or (_first_coding(resource["valueCodeableConcept"]) or {}).get("display")
        else:
            value = ""
        return {"resource_type": "Observation", "id": resource["id"], "label": label, "value": value,
                "code": _first_coding(resource.get("code"))}

    # ---- review -------------------------------------------------------------

    async def review(self, resource_type: str, resource_id: str, decision: str, reviewer: str = "Front desk") -> dict:
        if resource_type not in REVIEWABLE:
            raise IntakeError(f"{resource_type} is not reviewable")
        if decision not in ("approve", "reject"):
            raise IntakeError("decision must be approve or reject")
        resource = await self.store.read(resource_type, resource_id)
        if _ext(resource, EXT_REVIEW_STATUS) is None:
            raise IntakeError("Only AI-extracted items can be reviewed")

        approved = decision == "approve"
        _set_ext(resource, EXT_REVIEW_STATUS, "valueCode", REVIEW_APPROVED if approved else REVIEW_REJECTED)
        if resource_type == "Condition":
            resource["verificationStatus"] = {
                "coding": [{"system": f"{TERM}/condition-ver-status", "code": "confirmed" if approved else "entered-in-error"}]
            }
        elif resource_type == "AllergyIntolerance":
            resource["verificationStatus"] = {
                "coding": [
                    {"system": f"{TERM}/allergyintolerance-verification", "code": "confirmed" if approved else "entered-in-error"}
                ]
            }
        elif not approved:
            resource["status"] = "entered-in-error"
        for note in resource.get("note", []):
            note["text"] = note["text"].replace(
                "awaiting staff review", f"{'approved' if approved else 'rejected'} by {reviewer}"
            )

        updated = await self.store.update(resource)
        await self.store.create(
            {
                "resourceType": "Provenance",
                "meta": {"tag": [dict(DEMO_TAG)]},
                "target": [{"reference": f"{resource_type}/{resource_id}"}],
                "recorded": fhir_build.now_iso(),
                "activity": {
                    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-DataOperation", "code": "UPDATE"}],
                    "text": "approved after review" if approved else "rejected after review",
                },
                "agent": [
                    {
                        "type": {"coding": [{"system": f"{TERM}/provenance-participant-type", "code": "verifier", "display": "Verifier"}]},
                        "who": {"display": reviewer},
                    }
                ],
            }
        )
        return self.item_view(updated)

    async def approve_all(self, encounter_id: str, reviewer: str = "Front desk") -> dict:
        arrival = await self.get_arrival(encounter_id)
        for item in arrival["items"]:
            if item["review_status"] == REVIEW_PENDING:
                await self.review(item["resource_type"], item["id"], "approve", reviewer)
        return await self.get_arrival(encounter_id)
