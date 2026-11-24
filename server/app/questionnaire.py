"""The intake form, defined once as a FHIR R4 Questionnaire.

The patient app renders this resource at runtime, so a clinic can change the
form without shipping a new app build.
"""

from __future__ import annotations

from typing import Any

from .fhir_ids import BASE, QUESTIONNAIRE_URL

FREE_TEXT_LINK_IDS = ("reason", "medications", "allergies", "history")


GENDER_SYSTEM = "http://hl7.org/fhir/administrative-gender"
SMOKING_ANSWER_SYSTEM = f"{BASE}/CodeSystem/smoking-answer"


def _choice(link_id: str, text: str, system: str, options: list[tuple[str, str]], required: bool = False) -> dict:
    return {
        "linkId": link_id,
        "text": text,
        "type": "choice",
        "required": required,
        "answerOption": [
            {"valueCoding": {"system": system, "code": code, "display": display}} for code, display in options
        ],
    }


QUESTIONNAIRE: dict[str, Any] = {
    "resourceType": "Questionnaire",
    "id": "clinic-intake",
    "url": QUESTIONNAIRE_URL,
    "version": "1.0.0",
    "name": "ClinicIntake",
    "title": "New patient intake",
    "status": "active",
    "subjectType": ["Patient"],
    "item": [
        {
            "linkId": "about",
            "text": "About you",
            "type": "group",
            "item": [
                {"linkId": "given-name", "text": "First name", "type": "string", "required": True},
                {"linkId": "family-name", "text": "Last name", "type": "string", "required": True},
                {"linkId": "birth-date", "text": "Date of birth", "type": "date", "required": True},
                _choice(
                    "gender",
                    "Sex",
                    GENDER_SYSTEM,
                    [("female", "Female"), ("male", "Male"), ("other", "Other"), ("unknown", "Prefer not to say")],
                ),
                {"linkId": "phone", "text": "Mobile number", "type": "string"},
            ],
        },
        {
            "linkId": "today",
            "text": "Today's visit",
            "type": "group",
            "item": [
                {
                    "linkId": "reason",
                    "text": "What brings you in today? Use your own words.",
                    "type": "text",
                    "required": True,
                },
                {
                    "linkId": "pain-score",
                    "text": "If you're in pain, how bad is it from 0 (none) to 10 (worst)?",
                    "type": "integer",
                    "extension": [
                        {"url": "http://hl7.org/fhir/StructureDefinition/minValue", "valueInteger": 0},
                        {"url": "http://hl7.org/fhir/StructureDefinition/maxValue", "valueInteger": 10},
                    ],
                },
            ],
        },
        {
            "linkId": "health",
            "text": "Your health",
            "type": "group",
            "item": [
                {
                    "linkId": "medications",
                    "text": "Which medicines do you take, and how often? Include vitamins and anything you stopped recently.",
                    "type": "text",
                },
                {
                    "linkId": "allergies",
                    "text": "Are you allergic to anything? What happens when you're exposed?",
                    "type": "text",
                },
                {
                    "linkId": "history",
                    "text": "Any ongoing health conditions or past diagnoses?",
                    "type": "text",
                },
            ],
        },
        {
            "linkId": "lifestyle",
            "text": "A couple more",
            "type": "group",
            "item": [
                _choice(
                    "smoking",
                    "Do you smoke tobacco?",
                    SMOKING_ANSWER_SYSTEM,
                    [("never", "Never"), ("former", "I used to"), ("current", "Yes, currently")],
                ),
                {"linkId": "weight-lb", "text": "Your weight in pounds, if you know it", "type": "decimal"},
            ],
        },
    ],
}


def flatten_answers(questionnaire_response: dict) -> dict[str, Any]:
    """Map linkId -> first answer value from a QuestionnaireResponse, nested groups included."""

    answers: dict[str, Any] = {}

    def walk(items: list[dict]) -> None:
        for item in items or []:
            for answer in item.get("answer") or []:
                for key, value in answer.items():
                    if not key.startswith("value"):
                        continue
                    if key == "valueCoding":
                        value = value.get("code")
                    answers.setdefault(item["linkId"], value)
                    break
                walk(answer.get("item") or [])
            walk(item.get("item") or [])

    walk(questionnaire_response.get("item") or [])
    return answers


def required_link_ids() -> list[str]:
    found: list[str] = []

    def walk(items: list[dict]) -> None:
        for item in items:
            if item.get("required"):
                found.append(item["linkId"])
            walk(item.get("item") or [])

    walk(QUESTIONNAIRE["item"])
    return found
