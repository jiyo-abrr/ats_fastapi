"""Keep the HTTP representation stable when services return plain results."""

import uuid
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domains.auth.contracts import AccessToken, SignupResult, TokenPair
from app.domains.auth.entities import User
from app.domains.auth.schemas import AccessTokenResponse, SignupResponse, TokenResponse


def test_signup_response_filters_entity_secrets_and_keeps_computed_fields():
    user = User(
        id=uuid.uuid4(),
        first_name="Ana",
        middle_initial=None,
        last_name="Reyes",
        contact_number="000",
        email="ana@example.com",
        password_hash="private-hash",
        role_id=uuid.uuid4(),
        role="applicant",
        resume_object_key="private/resume.pdf",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    api = FastAPI()

    @api.get("/signup-result", response_model=SignupResponse)
    def result():
        return SignupResult(access_token="access", refresh_token="refresh", user=user)

    response = TestClient(api).get("/signup-result")
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "access"
    assert body["refresh_token"] == "refresh"
    assert body["token_type"] == "bearer"
    assert body["user"]["has_resume"] is True
    assert body["user"]["email"] == "ana@example.com"
    assert not {"password_hash", "role_id", "resume_object_key"} & body["user"].keys()


def test_token_results_keep_the_existing_wire_format():
    assert TokenResponse.model_validate(
        TokenPair(
            access_token="access",
            refresh_token="refresh",
        )
    ).model_dump() == {
        "access_token": "access",
        "refresh_token": "refresh",
        "token_type": "bearer",
    }
    assert AccessTokenResponse.model_validate(AccessToken("access")).model_dump() == {
        "access_token": "access",
        "token_type": "bearer",
    }
