from app.demo_patients import DEMO_PATIENTS, as_questionnaire_response
from app.extract.claude import ExtractionError


def test_questionnaire_served(client):
    q = client.get("/api/questionnaire").json()
    assert q["resourceType"] == "Questionnaire"


def test_submit_review_flow(client):
    created = client.post("/api/intake", json=as_questionnaire_response(DEMO_PATIENTS["maria"]))
    assert created.status_code == 201
    encounter_id = created.json()["encounter_id"]

    arrivals = client.get("/api/arrivals").json()
    assert len(arrivals) == 1
    arrival = arrivals[0]
    assert arrival["patient"]["name"] == "Maria Delgado-Test"
    assert arrival["counts"]["pending"] == len(arrival["items"]) > 0
    assert {o["label"] for o in arrival["observations"]} >= {"Tobacco smoking status", "Body weight"}

    first, second = arrival["items"][0], arrival["items"][1]
    ok = client.post(f"/api/items/{first['resource_type']}/{first['id']}/review", json={"decision": "approve"})
    assert ok.json()["review_status"] == "approved"
    no = client.post(f"/api/items/{second['resource_type']}/{second['id']}/review", json={"decision": "reject"})
    assert no.json()["review_status"] == "rejected"

    detail = client.post(f"/api/arrivals/{encounter_id}/approve-all").json()
    assert detail["counts"]["pending"] == 0
    assert detail["counts"]["rejected"] == 1
    types = {r["resourceType"] for r in detail["resources"]}
    assert {"Patient", "Encounter", "QuestionnaireResponse"} <= types


def test_returning_patient_is_matched(client):
    qr = as_questionnaire_response(DEMO_PATIENTS["james"])
    first = client.post("/api/intake", json=qr).json()
    second = client.post("/api/intake", json=qr).json()
    assert second["returning_patient"] is True
    assert second["patient_id"] == first["patient_id"]
    assert second["encounter_id"] != first["encounter_id"]


def test_missing_required_answers_rejected(client):
    qr = as_questionnaire_response({**DEMO_PATIENTS["priya"], "reason": ""})
    response = client.post("/api/intake", json=qr)
    assert response.status_code == 422
    assert "reason" in response.json()["detail"]


def test_patient_reported_observations_are_not_reviewable(client):
    client.post("/api/demo/patients/james")
    obs = client.get("/api/arrivals").json()[0]["observations"][0]
    response = client.post(f"/api/items/Observation/{obs['id']}/review", json={"decision": "approve"})
    assert response.status_code == 422


def test_model_failure_falls_back_to_rules(client):
    class Broken:
        name = "claude:test"

        async def extract(self, text):
            raise ExtractionError("Could not reach the Anthropic API")

    client.app.state.service.extractor = Broken()
    created = client.post("/api/demo/patients/maria").json()
    assert created["extractor"].startswith("rules-baseline (fallback")
    assert created["items_for_review"] > 0
