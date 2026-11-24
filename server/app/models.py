"""The extraction contract shared by every extractor (Claude and the rules baseline)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from . import terminology


class ConditionFinding(BaseModel):
    name: str = Field(description="Plain-language name of the condition, e.g. 'high blood pressure'.")
    term_key: str = Field(description="Key from the allowed condition list, or 'other'.")
    clinical_status: Literal["active", "resolved"]
    source_quote: str = Field(description="The exact words from the patient's answer this came from.")


class AllergyFinding(BaseModel):
    substance: str
    term_key: str
    reactions: list[str] = Field(description="Reaction keys from the allowed reaction list, or 'other'.")
    severity: Literal["mild", "moderate", "severe", "unknown"]
    source_quote: str


class MedicationFinding(BaseModel):
    name: str
    term_key: str
    dose: str = Field(description="Dose as the patient wrote it, e.g. '10 mg'. Empty if not given.")
    frequency: str = Field(description="How often, e.g. 'once a day'. Empty if not given.")
    status: Literal["active", "stopped"]
    source_quote: str


class Extraction(BaseModel):
    visit_summary: str = Field(description="One neutral sentence for front desk staff. No diagnosis.")
    conditions: list[ConditionFinding]
    allergies: list[AllergyFinding]
    medications: list[MedicationFinding]
    no_known_allergies: bool
    # Filled in by the extractor, not by the model: which extractor produced this.
    extractor: str = ""

    def normalized(self) -> "Extraction":
        """Force any key the model invented back to 'other' so codes only come from our table."""

        def fix(key: str, table: dict) -> str:
            return key if key in table else terminology.OTHER

        return Extraction(
            visit_summary=self.visit_summary.strip(),
            conditions=[
                c.model_copy(update={"term_key": fix(c.term_key, terminology.CONDITIONS)}) for c in self.conditions
            ],
            allergies=[
                a.model_copy(
                    update={
                        "term_key": fix(a.term_key, terminology.ALLERGENS),
                        "reactions": [fix(r, terminology.REACTIONS) for r in a.reactions],
                    }
                )
                for a in self.allergies
            ],
            medications=[
                m.model_copy(update={"term_key": fix(m.term_key, terminology.MEDICATIONS)}) for m in self.medications
            ],
            no_known_allergies=self.no_known_allergies and not self.allergies,
            extractor=self.extractor,
        )


class IntakeText(BaseModel):
    """The free-text answers an extractor reads."""

    reason: str = ""
    medications: str = ""
    allergies: str = ""
    history: str = ""

    def as_prompt_block(self) -> str:
        parts = [
            ("What brings you in today", self.reason),
            ("Medicines", self.medications),
            ("Allergies", self.allergies),
            ("Health conditions", self.history),
        ]
        return "\n\n".join(f"<answer question=\"{q}\">\n{a.strip() or '(left blank)'}\n</answer>" for q, a in parts)

    def all_text(self) -> str:
        return "\n".join([self.reason, self.medications, self.allergies, self.history])


def json_schema() -> dict:
    """JSON schema for structured output, with the allowlists as enums.

    Built by hand rather than from the Pydantic models so the enums are explicit
    and every object closes with additionalProperties: false.
    """

    def keys(table: dict) -> list[str]:
        return sorted(table) + [terminology.OTHER]

    def obj(properties: dict) -> dict:
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    string = {"type": "string"}
    return obj(
        {
            "visit_summary": string,
            "conditions": {
                "type": "array",
                "items": obj(
                    {
                        "name": string,
                        "term_key": {"type": "string", "enum": keys(terminology.CONDITIONS)},
                        "clinical_status": {"type": "string", "enum": ["active", "resolved"]},
                        "source_quote": string,
                    }
                ),
            },
            "allergies": {
                "type": "array",
                "items": obj(
                    {
                        "substance": string,
                        "term_key": {"type": "string", "enum": keys(terminology.ALLERGENS)},
                        "reactions": {
                            "type": "array",
                            "items": {"type": "string", "enum": keys(terminology.REACTIONS)},
                        },
                        "severity": {"type": "string", "enum": ["mild", "moderate", "severe", "unknown"]},
                        "source_quote": string,
                    }
                ),
            },
            "medications": {
                "type": "array",
                "items": obj(
                    {
                        "name": string,
                        "term_key": {"type": "string", "enum": keys(terminology.MEDICATIONS)},
                        "dose": string,
                        "frequency": string,
                        "status": {"type": "string", "enum": ["active", "stopped"]},
                        "source_quote": string,
                    }
                ),
            },
            "no_known_allergies": {"type": "boolean"},
        }
    )
