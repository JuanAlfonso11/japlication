import pytest
from pydantic import ValidationError

from app.schemas.user import UserRegister


def test_accepts_a_compliant_password():
    user = UserRegister(email="ok@example.com", password="Str0ng!Pass", full_name="A B")
    assert user.password == "Str0ng!Pass"


@pytest.mark.parametrize(
    "password",
    [
        "alllowercase1!",  # no uppercase
        "NoDigitsHere!",  # no digit
        "NoSpecialChars123",  # no special character
    ],
)
def test_rejects_password_missing_a_required_class(password):
    with pytest.raises(ValidationError):
        UserRegister(email="ok@example.com", password=password, full_name="A B")


def test_rejects_disposable_email_domain():
    with pytest.raises(ValidationError):
        UserRegister(email="someone@mailinator.com", password="Str0ng!Pass", full_name="A B")
