import uuid

import jwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("s3cret")
    assert verify_password("s3cret", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    payload = decode_token(token, expected_type="access")
    assert payload.user_id == user_id
    assert payload.jti


def test_refresh_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_refresh_token(user_id)
    payload = decode_token(token, expected_type="refresh")
    assert payload.user_id == user_id


def test_access_and_refresh_tokens_have_different_jti():
    user_id = uuid.uuid4()
    access = decode_token(create_access_token(user_id), expected_type="access")
    refresh = decode_token(create_refresh_token(user_id), expected_type="refresh")
    assert access.jti != refresh.jti


def test_decode_rejects_wrong_type():
    user_id = uuid.uuid4()
    access_token = create_access_token(user_id)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(access_token, expected_type="refresh")


def test_decode_rejects_garbage():
    with pytest.raises(jwt.InvalidTokenError):
        decode_token("not-a-jwt", expected_type="access")
