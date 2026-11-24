"""A small, curated terminology map for the demo.

The AI extractor may only pick a `key` from this allowlist (or "other").
Codes are attached here, deterministically, never by the model. Anything the
model can't map stays as uncoded text for front desk staff to review.

This is a demo-sized subset, not a clinical terminology service. In a real
deployment this lookup would call the clinic's terminology server.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SNOMED = "http://snomed.info/sct"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
LOINC = "http://loinc.org"


@dataclass(frozen=True)
class Concept:
    key: str
    display: str
    system: str
    code: str
    synonyms: tuple[str, ...] = field(default_factory=tuple)


def _index(concepts: list[Concept]) -> dict[str, Concept]:
    return {c.key: c for c in concepts}


CONDITIONS = _index(
    [
        Concept("hypertension", "Hypertensive disorder", SNOMED, "38341003",
                ("hypertension", "high blood pressure", "high bp", "htn")),
        Concept("type_2_diabetes", "Diabetes mellitus type 2", SNOMED, "44054006",
                ("type 2 diabetes", "type ii diabetes", "t2d", "diabetes type 2", "sugar diabetes")),
        Concept("asthma", "Asthma", SNOMED, "195967001", ("asthma",)),
        Concept("hyperlipidemia", "Hyperlipidemia", SNOMED, "55822004",
                ("high cholesterol", "hyperlipidemia", "cholesterol")),
        Concept("migraine", "Migraine", SNOMED, "37796009", ("migraine", "migraines")),
        Concept("hypothyroidism", "Hypothyroidism", SNOMED, "40930008",
                ("hypothyroidism", "underactive thyroid", "low thyroid")),
        Concept("copd", "Chronic obstructive lung disease", SNOMED, "13645005", ("copd", "emphysema")),
        Concept("gerd", "Gastroesophageal reflux disease", SNOMED, "235595009",
                ("gerd", "acid reflux", "reflux", "heartburn")),
        Concept("osteoarthritis", "Osteoarthritis", SNOMED, "396275006",
                ("osteoarthritis", "arthritis")),
        Concept("atrial_fibrillation", "Atrial fibrillation", SNOMED, "49436004",
                ("atrial fibrillation", "afib", "a-fib")),
    ]
)

ALLERGENS = _index(
    [
        Concept("penicillin", "Penicillin", SNOMED, "764146007", ("penicillin", "pcn")),
        Concept("amoxicillin", "Amoxicillin", RXNORM, "723", ("amoxicillin", "amoxil")),
        Concept("aspirin", "Aspirin", RXNORM, "1191", ("aspirin",)),
        Concept("ibuprofen", "Ibuprofen", RXNORM, "5640", ("ibuprofen", "advil", "motrin")),
        Concept("latex", "Latex", SNOMED, "111088007", ("latex",)),
        Concept("peanut", "Peanut", SNOMED, "762952008", ("peanut", "peanuts")),
        Concept("egg", "Egg", SNOMED, "102263004", ("egg", "eggs")),
        Concept("cow_milk", "Cow's milk", SNOMED, "3718001", ("milk", "dairy")),
        Concept("shellfish", "Shellfish", SNOMED, "735029006", ("shellfish", "shrimp", "crab", "lobster")),
    ]
)

MEDICATIONS = _index(
    [
        Concept("lisinopril", "Lisinopril", RXNORM, "29046", ("lisinopril", "lisinipril", "zestril", "prinivil")),
        Concept("metformin", "Metformin", RXNORM, "6809", ("metformin", "glucophage")),
        Concept("atorvastatin", "Atorvastatin", RXNORM, "83367", ("atorvastatin", "lipitor")),
        Concept("amlodipine", "Amlodipine", RXNORM, "17767", ("amlodipine", "norvasc")),
        Concept("levothyroxine", "Levothyroxine", RXNORM, "10582", ("levothyroxine", "synthroid")),
        Concept("albuterol", "Albuterol", RXNORM, "435", ("albuterol", "ventolin", "proair", "rescue inhaler")),
        Concept("omeprazole", "Omeprazole", RXNORM, "7646", ("omeprazole", "prilosec")),
        Concept("ibuprofen", "Ibuprofen", RXNORM, "5640", ("ibuprofen", "advil", "motrin")),
        Concept("aspirin", "Aspirin", RXNORM, "1191", ("aspirin", "baby aspirin")),
        Concept("acetaminophen", "Acetaminophen", RXNORM, "161", ("acetaminophen", "tylenol", "paracetamol")),
        Concept("simvastatin", "Simvastatin", RXNORM, "36567", ("simvastatin", "zocor")),
        Concept("losartan", "Losartan", RXNORM, "52175", ("losartan", "cozaar")),
        Concept("metoprolol", "Metoprolol", RXNORM, "6918", ("metoprolol", "lopressor", "toprol")),
        Concept("hydrochlorothiazide", "Hydrochlorothiazide", RXNORM, "5487", ("hydrochlorothiazide", "hctz")),
        Concept("sumatriptan", "Sumatriptan", RXNORM, "37418", ("sumatriptan", "imitrex")),
        Concept("montelukast", "Montelukast", RXNORM, "88249", ("montelukast", "singulair")),
        Concept("cetirizine", "Cetirizine", RXNORM, "20610", ("cetirizine", "zyrtec")),
        Concept("warfarin", "Warfarin", RXNORM, "11289", ("warfarin", "coumadin")),
    ]
)

# Allergy reaction manifestations (SNOMED clinical findings).
REACTIONS = _index(
    [
        Concept("hives", "Urticaria", SNOMED, "126485001", ("hives", "urticaria", "welts")),
        Concept("rash", "Eruption of skin", SNOMED, "271807003", ("rash", "skin rash")),
        Concept("anaphylaxis", "Anaphylaxis", SNOMED, "39579001", ("anaphylaxis", "anaphylactic")),
        Concept("swelling", "Swelling", SNOMED, "65124004", ("swelling", "swollen", "swells", "swell")),
        Concept("itching", "Itching", SNOMED, "418290006", ("itching", "itchy", "itch")),
        Concept("nausea", "Nausea", SNOMED, "422587007", ("nausea", "nauseous", "sick to my stomach")),
        Concept("shortness_of_breath", "Dyspnea", SNOMED, "267036007",
                ("shortness of breath", "trouble breathing", "can't breathe", "short of breath")),
    ]
)

# Observation codes used for structured questionnaire answers.
LOINC_SMOKING_STATUS = ("72166-2", "Tobacco smoking status")
LOINC_PAIN_SEVERITY = ("72514-3", "Pain severity - 0-10 verbal numeric rating [Score] - Reported")
LOINC_BODY_WEIGHT = ("29463-7", "Body weight")

SMOKING_STATUS_ANSWERS = {
    "never": Concept("never", "Never smoked tobacco", SNOMED, "266919005"),
    "former": Concept("former", "Ex-smoker", SNOMED, "8517006"),
    "current": Concept("current", "Smoker", SNOMED, "77176002"),
}

OTHER = "other"


def lookup(table: dict[str, Concept], key: str | None) -> Concept | None:
    if not key or key == OTHER:
        return None
    return table.get(key)
