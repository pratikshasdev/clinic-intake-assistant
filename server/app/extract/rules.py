"""Offline keyword extractor.

It exists for two reasons: the demo runs with no API key, and it is the
baseline the eval compares Claude against. It is deliberately simple: it
matches synonyms from the terminology table, so it misses anything phrased
in a way the table doesn't list.
"""

from __future__ import annotations

import re

from .. import terminology
from ..models import AllergyFinding, ConditionFinding, Extraction, IntakeText, MedicationFinding

NO_ALLERGY_PATTERNS = re.compile(
    r"\b(no known (drug )?allergies|nkda|nka|no allergies|not allergic to anything|none)\b", re.I
)
STOPPED_PATTERNS = re.compile(r"\b(stopped|used to|no longer|quit|discontinued|not anymore|off of)\b", re.I)
FAMILY_PATTERNS = re.compile(r"\b(mom|mother|dad|father|sister|brother|grandma|grandpa|grandmother|grandfather|family)\b", re.I)
RESOLVED_PATTERNS = re.compile(r"\b(had|history of|as a kid|as a child|resolved|gone|years ago)\b", re.I)
DOSE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|units?|puffs?|iu)\b", re.I)
FREQUENCIES = [
    "twice a day", "twice daily", "three times a day", "once a day", "once daily", "every morning",
    "every night", "at night", "at bedtime", "daily", "weekly", "as needed", "when needed", "every day",
]
SEVERE = re.compile(r"\b(anaphyla\w*|severe|epipen|hospital|er\b|throat (closes|closed|swell))", re.I)
MILD = re.compile(r"\b(mild|a little|slight)\b", re.I)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.;\n!?]+", text) if s.strip()]


def _clauses(text: str) -> list[str]:
    out: list[str] = []
    for sentence in _sentences(text):
        out.extend(p.strip() for p in re.split(r",|\band\b|\balso\b", sentence) if p.strip())
    return out


def _find(table: dict[str, terminology.Concept], text: str) -> list[tuple[terminology.Concept, str]]:
    """Every concept whose synonym appears in text, longest synonym first, no duplicates."""

    found: list[tuple[terminology.Concept, str]] = []
    seen: set[str] = set()
    lowered = text.lower()
    pairs = sorted(
        ((c, s) for c in table.values() for s in c.synonyms), key=lambda pair: len(pair[1]), reverse=True
    )
    for concept, synonym in pairs:
        if concept.key in seen:
            continue
        if re.search(rf"\b{re.escape(synonym)}\b", lowered):
            found.append((concept, synonym))
            seen.add(concept.key)
    return found


class RulesExtractor:
    name = "rules-baseline"

    async def extract(self, text: IntakeText) -> Extraction:
        return self.extract_sync(text)

    def extract_sync(self, text: IntakeText) -> Extraction:
        conditions: list[ConditionFinding] = []
        seen_conditions: set[str] = set()
        for clause in _clauses(text.history) + _clauses(text.reason):
            if FAMILY_PATTERNS.search(clause):
                continue
            for concept, _ in _find(terminology.CONDITIONS, clause):
                if concept.key in seen_conditions:
                    continue
                seen_conditions.add(concept.key)
                conditions.append(
                    ConditionFinding(
                        name=concept.display,
                        term_key=concept.key,
                        clinical_status="resolved" if RESOLVED_PATTERNS.search(clause) else "active",
                        source_quote=clause,
                    )
                )

        allergies: list[AllergyFinding] = []
        no_known = False
        for sentence in _sentences(text.allergies):
            if NO_ALLERGY_PATTERNS.search(sentence) and not _find(terminology.ALLERGENS, sentence):
                no_known = True
                continue
            reactions = [c.key for c, _ in _find(terminology.REACTIONS, sentence)]
            severity = "severe" if SEVERE.search(sentence) else "mild" if MILD.search(sentence) else "unknown"
            for concept, _ in _find(terminology.ALLERGENS, sentence):
                allergies.append(
                    AllergyFinding(
                        substance=concept.display,
                        term_key=concept.key,
                        reactions=reactions,
                        severity=severity,
                        source_quote=sentence,
                    )
                )

        medications: list[MedicationFinding] = []
        seen_meds: set[str] = set()
        for clause in _clauses(text.medications):
            for concept, _ in _find(terminology.MEDICATIONS, clause):
                if concept.key in seen_meds:
                    continue
                seen_meds.add(concept.key)
                dose = DOSE.search(clause)
                frequency = next((f for f in FREQUENCIES if f in clause.lower()), "")
                medications.append(
                    MedicationFinding(
                        name=concept.display,
                        term_key=concept.key,
                        dose=dose.group(0) if dose else "",
                        frequency=frequency,
                        status="stopped" if STOPPED_PATTERNS.search(clause) else "active",
                        source_quote=clause,
                    )
                )

        summary = text.reason.strip().split("\n")[0][:160]
        return Extraction(
            visit_summary=f"Patient reports: {summary}" if summary else "No reason given.",
            conditions=conditions,
            allergies=allergies,
            medications=medications,
            no_known_allergies=no_known and not allergies,
            extractor=self.name,
        )
