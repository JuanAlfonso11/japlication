from app.services.disposable_email import is_disposable_email


def test_known_disposable_domain_is_flagged():
    assert is_disposable_email("someone@mailinator.com") is True


def test_ordinary_domain_is_not_flagged():
    assert is_disposable_email("someone@gmail.com") is False


def test_is_case_insensitive():
    assert is_disposable_email("someone@MAILINATOR.COM") is True


def test_handles_malformed_input_without_raising():
    assert is_disposable_email("not-an-email") is False
