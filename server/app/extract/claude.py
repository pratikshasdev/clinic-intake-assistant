"""Claude extractor: free-text intake answers in, a validated Extraction out.

Design choices worth knowing:
- Structured output (output_config.format) with the terminology allowlists as
  enums, so the model can only pick a known concept key or "other". Codes are
  attached afterwards from our own table, never written by the model.
- Every finding carries the patient's exact words, which the service checks
  against the original answer before anything is shown to staff.
- Server-side refusal fallback is on, and any failure raises ExtractionError
  so the service can fall back to the offline extractor instead of losing the
  patient's intake.
"""

from __future__ import annotations

import json
import logging

import anthropic

from .. import models
from ..models import Extraction, IntakeText

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You turn a patient's self-reported clinic intake answers into structured data for front desk staff to review.

Rules:
- Record only what the patient says about themselves. Skip family history ("my mom has diabetes") and anything you would be guessing.
- Do not diagnose. A symptom the patient reports for today's visit is not a condition unless they name it as a diagnosis they have.
- For each finding, source_quote must be copied exactly, character for character, from the patient's answer, and be as short as possible while still containing the finding.
- term_key: choose the matching key from the allowed list. Brand names and lay terms count (Lipitor is atorvastatin, high blood pressure is hypertension). If nothing in the list matches, use "other" and put the patient's term in the name field.
- Medications the patient says they stopped or no longer take get status "stopped". Conditions the patient says are in the past get clinical_status "resolved".
- Allergy reactions: pick reaction keys from the allowed list; use "other" for anything else. Severity is "severe" for anaphylaxis, throat swelling, or needing emergency care, otherwise use what the patient says or "unknown".
- no_known_allergies is true only when the patient clearly says they have no allergies.
- visit_summary: one neutral sentence describing why the patient came in today, for the front desk. No diagnosis, no advice.
- Some answers may be blank or unclear. Return empty lists rather than inventing findings."""


class ExtractionError(RuntimeError):
    pass


class ClaudeExtractor:
    def __init__(self, model: str, effort: str = "medium", api_key: str | None = None):
        self.model = model
        self.effort = effort
        self.name = f"claude:{model}"
        # With api_key None the SDK reads ANTHROPIC_API_KEY (or another configured credential).
        self._client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else anthropic.AsyncAnthropic()

    async def extract(self, text: IntakeText) -> Extraction:
        try:
            response = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": models.json_schema()},
                },
                messages=[
                    {
                        "role": "user",
                        "content": "Here are the patient's answers:\n\n" + text.as_prompt_block(),
                    }
                ],
            )
        except anthropic.AuthenticationError as exc:
            raise ExtractionError("Anthropic API key was rejected") from exc
        except anthropic.RateLimitError as exc:
            raise ExtractionError("Rate limited by the Anthropic API") from exc
        except anthropic.APIStatusError as exc:
            raise ExtractionError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ExtractionError("Could not reach the Anthropic API") from exc

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            raise ExtractionError(f"Model declined the request (category: {category})")
        if response.stop_reason == "max_tokens":
            raise ExtractionError("Model output was cut off at max_tokens")

        text_block = next((b for b in response.content if b.type == "text"), None)
        if text_block is None:
            raise ExtractionError("Model returned no text block")
        try:
            extraction = Extraction.model_validate(json.loads(text_block.text))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ExtractionError("Model output did not match the extraction schema") from exc

        log.info("extraction request_id=%s model=%s usage=%s", response._request_id, response.model, response.usage)
        # response.model names the model that actually served the request,
        # which differs from self.model if a refusal fallback ran.
        return extraction.normalized().model_copy(update={"extractor": f"claude:{response.model}"})
