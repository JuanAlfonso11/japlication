from app.core.security import create_refresh_token, hash_refresh_token


def test_refresh_token_is_random_and_long():
    a = create_refresh_token()
    b = create_refresh_token()
    assert a != b
    assert len(a) >= 32


def test_hash_refresh_token_is_deterministic():
    token = create_refresh_token()
    assert hash_refresh_token(token) == hash_refresh_token(token)


def test_hash_refresh_token_differs_per_token():
    a = create_refresh_token()
    b = create_refresh_token()
    assert hash_refresh_token(a) != hash_refresh_token(b)


def test_hash_refresh_token_does_not_return_the_raw_token():
    token = create_refresh_token()
    assert hash_refresh_token(token) != token
