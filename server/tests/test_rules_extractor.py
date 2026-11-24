from app.demo_patients import DEMO_PATIENTS
from app.extract.rules import RulesExtractor
from app.models import IntakeText


def text_for(key: str) -> IntakeText:
    p = DEMO_PATIENTS[key]
    return IntakeText(reason=p["reason"], medications=p["medications"], allergies=p["allergies"], history=p["history"])


def test_maria_findings():
    e = RulesExtractor().extract_sync(text_for("maria"))
    assert {c.term_key for c in e.conditions} == {"hypertension", "hyperlipidemia", "asthma"}
    assert next(c for c in e.conditions if c.term_key == "asthma").clinical_status == "resolved"
    assert {a.term_key for a in e.allergies} == {"penicillin", "shellfish"}
    assert next(a for a in e.allergies if a.term_key == "shellfish").severity == "severe"
    meds = {m.term_key: m for m in e.medications}
    assert meds["lisinopril"].dose == "10mg"
    assert "atorvastatin" in meds  # brand name Lipitor


def test_stopped_medication_and_no_known_allergies():
    e = RulesExtractor().extract_sync(text_for("james"))
    meds = {m.term_key: m.status for m in e.medications}
    assert meds["simvastatin"] == "stopped"
    assert meds["metformin"] == "active"
    assert e.no_known_allergies is True
    assert e.allergies == []
    # "My dad had a heart attack" is family history, not the patient's.
    assert all("dad" not in c.source_quote.lower() for c in e.conditions)


def test_quotes_are_verbatim():
    for key in ("maria", "james", "priya"):
        t = text_for(key)
        e = RulesExtractor().extract_sync(t)
        for item in [*e.conditions, *e.allergies, *e.medications]:
            assert item.source_quote in t.all_text()
