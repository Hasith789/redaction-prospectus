from src.detector import (
    detect_pii,
    luhn_check,
    valid_ip,
)


def get_types(text):
    return {
        match.pii_type
        for match in detect_pii(text)
    }


def test_email():
    text = "Contact john.doe@example.com"
    assert "EMAIL" in get_types(text)


def test_phone():
    text = "Call +91 9876543210"
    assert "PHONE" in get_types(text)


def test_ip():
    text = "Server IP is 192.168.1.100"
    assert "IP_ADDRESS" in get_types(text)


def test_ssn():
    text = "SSN: 123-45-6789"
    assert "SSN" in get_types(text)


def test_credit_card():
    text = "Card: 4532015112830366"
    assert "CREDIT_CARD" in get_types(text)


def test_dob():
    text = "Date of Birth: 15/08/1998"
    assert "DATE_OF_BIRTH" in get_types(text)


def test_invalid_ip():
    assert valid_ip("192.168.1.999") is False


def test_luhn():
    assert luhn_check("4532015112830366") is True

def test_indian_landline():
    text = "Telephone: +91 20 45053237"
    matches = detect_pii(text)

    values = [match.value for match in matches]

    assert "+91 20 45053237" in values


def test_indian_mobile():
    text = "Mobile: +91 9876543210"
    matches = detect_pii(text)

    values = [match.value for match in matches]

    assert "+91 9876543210" in values