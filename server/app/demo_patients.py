"""Synthetic demo patients. Every name, date and number here is made up."""

from __future__ import annotations

from .questionnaire import GENDER_SYSTEM, SMOKING_ANSWER_SYSTEM

DEMO_PATIENTS: dict[str, dict[str, object]] = {
    "maria": {
        "given-name": "Maria",
        "family-name": "Delgado-Test",
        "birth-date": "1979-04-12",
        "gender": "female",
        "phone": "555-0142",
        "reason": "Bad cough for about a week and I feel tired all the time.",
        "pain-score": 3,
        "medications": "I take lisinopril 10mg every morning for my blood pressure and Lipitor at night.",
        "allergies": "Allergic to penicillin, it gives me hives. Shellfish makes my throat swell, I carry an EpiPen.",
        "history": "High blood pressure and high cholesterol. Had asthma as a kid but grew out of it.",
        "smoking": "former",
        "weight-lb": 162,
    },
    "james": {
        "given-name": "James",
        "family-name": "Okafor-Test",
        "birth-date": "1958-11-30",
        "gender": "male",
        "phone": "555-0188",
        "reason": "Follow-up on my sugar levels, and my knees hurt when I walk.",
        "pain-score": 5,
        "medications": "Metformin 500 mg twice a day. I stopped the simvastatin last month because of muscle aches. Tylenol when needed.",
        "allergies": "No known allergies",
        "history": "Type 2 diabetes for ten years, arthritis in both knees. My dad had a heart attack.",
        "smoking": "never",
        "weight-lb": 214,
    },
    "priya": {
        "given-name": "Priya",
        "family-name": "Raman-Test",
        "birth-date": "1994-02-03",
        "gender": "female",
        "reason": "Migraines are getting more frequent, about three a week now.",
        "pain-score": 6,
        "medications": "Sumatriptan 50mg when a migraine starts. Synthroid 75 mcg daily. Vitamin D.",
        "allergies": "Latex gives me a rash. Advil upsets my stomach but I don't think it's an allergy.",
        "history": "Migraines since college, underactive thyroid.",
        "smoking": "never",
    },
}

ORDER = [
    ("about", ["given-name", "family-name", "birth-date", "gender", "phone"]),
    ("today", ["reason", "pain-score"]),
    ("health", ["medications", "allergies", "history"]),
    ("lifestyle", ["smoking", "weight-lb"]),
]


def _answer(link_id: str, value: object) -> dict:
    if link_id == "gender":
        return {"valueCoding": {"system": GENDER_SYSTEM, "code": value}}
    if link_id == "smoking":
        return {"valueCoding": {"system": SMOKING_ANSWER_SYSTEM, "code": value}}
    if link_id == "birth-date":
        return {"valueDate": value}
    if link_id == "pain-score":
        return {"valueInteger": value}
    if link_id == "weight-lb":
        return {"valueDecimal": value}
    return {"valueString": value}


def as_questionnaire_response(answers: dict[str, object]) -> dict:
    """Shape plain answers the way the patient app sends them."""

    groups = []
    for group, link_ids in ORDER:
        items = [
            {"linkId": link, "answer": [_answer(link, answers[link])]}
            for link in link_ids
            if answers.get(link) not in (None, "")
        ]
        if items:
            groups.append({"linkId": group, "item": items})
    return {
        "resourceType": "QuestionnaireResponse",
        "status": "completed",
        "item": groups,
    }
