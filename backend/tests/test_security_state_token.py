import uuid

from app.core.security import create_state_token, decode_state_token


def test_state_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_state_token(user_id, purpose="upwork_oauth")
    assert decode_state_token(token, purpose="upwork_oauth") == str(user_id)


def test_state_token_wrong_purpose_rejected():
    user_id = uuid.uuid4()
    token = create_state_token(user_id, purpose="upwork_oauth")
    assert decode_state_token(token, purpose="something_else") is None


def test_state_token_garbage_rejected():
    assert decode_state_token("not-a-real-jwt", purpose="upwork_oauth") is None


def test_state_token_expired_rejected():
    user_id = uuid.uuid4()
    token = create_state_token(user_id, purpose="upwork_oauth", expires_minutes=-1)
    assert decode_state_token(token, purpose="upwork_oauth") is None
