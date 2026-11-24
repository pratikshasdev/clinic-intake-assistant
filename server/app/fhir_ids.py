"""Canonical URLs and tag systems used on every resource this app writes.

example.org is the reserved domain for examples, which suits a demo that only
ever holds synthetic patients.
"""

BASE = "http://example.org/fhir/clinic-intake-assistant"

QUESTIONNAIRE_URL = f"{BASE}/Questionnaire/clinic-intake"

# Every resource we write carries this tag, so we only ever read back our own
# demo data from a shared public test server.
DEMO_TAG = {"system": f"{BASE}/tags", "code": "demo", "display": "Synthetic demo data"}

EXT_REVIEW_STATUS = f"{BASE}/StructureDefinition/review-status"
EXT_SOURCE_QUOTE = f"{BASE}/StructureDefinition/source-quote"
EXT_QUOTE_FOUND = f"{BASE}/StructureDefinition/source-quote-found"
EXT_VISIT_SUMMARY = f"{BASE}/StructureDefinition/visit-summary"
EXT_EXTRACTOR = f"{BASE}/StructureDefinition/extractor"

REVIEW_PENDING = "pending"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"
