"""A state token must never work as a session credential.

`create_state_token` is used for the email-verification link, so its value
travels through an inbox, browser history, and any Referer header the
verification page emits. It is signed with the same secret as an access
token and carries the same `sub`/`exp` claims, so before this was enforced
it also authenticated `Authorization: Bearer <that token>` for its ten
minute lifetime.
"""

import uuid

from app.core.security import (
    create_access_token,
    create_state_token,
    decode_access_token,
    decode_state_token,
)


def test_a_normal_access_token_still_works():
    user_id = uuid.uuid4()
    assert decode_access_token(create_access_token(user_id)) == str(user_id)


def test_a_state_token_is_not_accepted_as_an_access_token():
    user_id = uuid.uuid4()
    state = create_state_token(user_id, purpose="email_verify")
    assert decode_access_token(state) is None


def test_state_tokens_still_work_for_their_own_purpose():
    user_id = uuid.uuid4()
    state = create_state_token(user_id, purpose="email_verify")
    assert decode_state_token(state, purpose="email_verify") == str(user_id)


def test_a_state_token_is_not_accepted_for_a_different_purpose():
    user_id = uuid.uuid4()
    state = create_state_token(user_id, purpose="email_verify")
    assert decode_state_token(state, purpose="password_reset") is None


def test_an_access_token_is_not_accepted_where_a_state_token_is_required():
    user_id = uuid.uuid4()
    access = create_access_token(user_id)
    assert decode_state_token(access, purpose="email_verify") is None


def test_garbage_and_tampered_tokens_are_rejected():
    assert decode_access_token("not-a-token") is None
    assert decode_access_token("") is None
    tampered = create_access_token(uuid.uuid4())[:-3] + "aaa"
    assert decode_access_token(tampered) is None
