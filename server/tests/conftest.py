import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client():
    app = create_app(Settings(fhir_base_url="memory", extractor="rules", _env_file=None))
    with TestClient(app) as c:
        yield c
