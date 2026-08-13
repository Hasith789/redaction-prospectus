import re
from dataclasses import dataclass
from typing import List


@dataclass
class PIIMatch:
    """
    Represents one detected PII value.
    """
    pii_type: str
    value: str
    start: int
    end: int


# ---------------------------------------------------------
# Regular expressions
# ---------------------------------------------------------

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)


PHONE_PATTERN = re.compile(
    r"""
    (?<!\d)
    (?:
        # Indian mobile number
        \+?91[\s.-]?[6-9]\d{9}

        |

        # Indian landline with country code
        \+?91[\s.-]?\d{2,4}[\s.-]?\d{6,8}

        |

        # Indian landline with STD code
        0\d{2,4}[\s.-]\d{6,8}
    )
    (?!\d)
    """,
    re.VERBOSE,
)


IP_PATTERN = re.compile(
    r"\b(?:"
    r"(?:25[0-5]|2[0-4]\d|1?\d?\d)\."
    r"){3}"
    r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
    r"\b"
)


SSN_PATTERN = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b"
)


CREDIT_CARD_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:\d[ -]?){13,19}"
    r"(?!\d)"
)


DATE_PATTERN = re.compile(
    r"\b(?:"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|"
    r"\d{1,2}\s+"
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
    r"\s+\d{4}"
    r"|"
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}"
    r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------
# Utility functions
# ---------------------------------------------------------

def luhn_check(number: str) -> bool:
    """
    Validate a credit-card number using the Luhn algorithm.
    """
    digits = [int(char) for char in number if char.isdigit()]

    if not 13 <= len(digits) <= 19:
        return False

    checksum = 0
    parity = len(digits) % 2

    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2

            if digit > 9:
                digit -= 9

        checksum += digit

    return checksum % 10 == 0


def valid_ip(address: str) -> bool:
    """
    Validate an IPv4 address.
    """
    parts = address.split(".")

    if len(parts) != 4:
        return False

    return all(
        part.isdigit() and 0 <= int(part) <= 255
        for part in parts
    )


def has_birth_context(text: str, start: int, end: int) -> bool:
    """
    A date is considered a DOB only when nearby text contains
    birth-related terminology.
    """
    context_start = max(0, start - 50)
    context_end = min(len(text), end + 50)

    context = text[context_start:context_end].lower()

    birth_terms = [
        "date of birth",
        "dob",
        "birth date",
        "birthdate",
        "born",
    ]

    return any(term in context for term in birth_terms)


# ---------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------

def detect_emails(text: str) -> List[PIIMatch]:
    matches = []

    for match in EMAIL_PATTERN.finditer(text):
        matches.append(
            PIIMatch(
                pii_type="EMAIL",
                value=match.group(),
                start=match.start(),
                end=match.end(),
            )
        )

    return matches


def detect_phones(text: str) -> List[PIIMatch]:
    matches = []

    for match in PHONE_PATTERN.finditer(text):
        value = match.group().strip()

        # Count actual digits.
        digit_count = sum(char.isdigit() for char in value)

        # A valid phone number should contain enough digits.
        if digit_count < 10:
            continue

        # Avoid email addresses.
        nearby_start = max(0, match.start() - 1)
        nearby_end = min(len(text), match.end() + 1)

        nearby_text = text[nearby_start:nearby_end]

        if "@" in nearby_text:
            continue

        matches.append(
            PIIMatch(
                pii_type="PHONE",
                value=value,
                start=match.start(),
                end=match.end(),
            )
        )

    return matches


def detect_ips(text: str) -> List[PIIMatch]:
    matches = []

    for match in IP_PATTERN.finditer(text):
        value = match.group()

        if not valid_ip(value):
            continue

        matches.append(
            PIIMatch(
                pii_type="IP_ADDRESS",
                value=value,
                start=match.start(),
                end=match.end(),
            )
        )

    return matches


def detect_ssns(text: str) -> List[PIIMatch]:
    matches = []

    for match in SSN_PATTERN.finditer(text):
        matches.append(
            PIIMatch(
                pii_type="SSN",
                value=match.group(),
                start=match.start(),
                end=match.end(),
            )
        )

    return matches


def detect_credit_cards(text: str) -> List[PIIMatch]:
    matches = []

    for match in CREDIT_CARD_PATTERN.finditer(text):
        value = match.group()

        digits = re.sub(r"\D", "", value)

        if luhn_check(digits):
            matches.append(
                PIIMatch(
                    pii_type="CREDIT_CARD",
                    value=value,
                    start=match.start(),
                    end=match.end(),
                )
            )

    return matches


def detect_dobs(text: str) -> List[PIIMatch]:
    matches = []

    for match in DATE_PATTERN.finditer(text):

        if not has_birth_context(
            text,
            match.start(),
            match.end(),
        ):
            continue

        matches.append(
            PIIMatch(
                pii_type="DATE_OF_BIRTH",
                value=match.group(),
                start=match.start(),
                end=match.end(),
            )
        )

    return matches


# ---------------------------------------------------------
# Combined detector
# ---------------------------------------------------------

def remove_overlapping_matches(
    matches: List[PIIMatch],
) -> List[PIIMatch]:
    """
    Remove overlapping detections.

    Longer matches are preferred when two detections overlap.
    """

    matches = sorted(
        matches,
        key=lambda item: (
            item.start,
            -(item.end - item.start),
        ),
    )

    result = []

    for current in matches:

        overlaps = False

        for existing in result:

            if (
                current.start < existing.end
                and current.end > existing.start
            ):
                overlaps = True
                break

        if not overlaps:
            result.append(current)

    return sorted(
        result,
        key=lambda item: item.start,
    )


def detect_pii(text: str) -> List[PIIMatch]:
    """
    Run all PII detectors and return their combined results.
    """

    matches = []

    # Structured PII
    matches.extend(detect_emails(text))
    matches.extend(detect_phones(text))
    matches.extend(detect_ips(text))
    matches.extend(detect_ssns(text))
    matches.extend(detect_credit_cards(text))
    matches.extend(detect_dobs(text))

    # Entity-based PII
    try:
        from entity_detector import (
            detect_people,
            detect_companies,
            detect_addresses,
        )

        matches.extend(detect_people(text))
        matches.extend(detect_companies(text))
        matches.extend(detect_addresses(text))

    except ImportError:
        # Keep structured PII working even if entity detection
        # is unavailable.
        pass

    return matches

    matches.extend(detect_emails(text))
    matches.extend(detect_phones(text))
    matches.extend(detect_ips(text))
    matches.extend(detect_ssns(text))
    matches.extend(detect_credit_cards(text))
    matches.extend(detect_dobs(text))

    return remove_overlapping_matches(matches)


# ---------------------------------------------------------
# Simple command-line test
# ---------------------------------------------------------

if __name__ == "__main__":

    sample_text = """
    Contact John Doe at john.doe@example.com.

    His phone number is +91 9876543210.

    His IP address is 192.168.1.100.

    SSN: 123-45-6789.

    Credit card: 4532015112830366.

    Date of Birth: 15/08/1998.
    """

    detections = detect_pii(sample_text)

    for detection in detections:
        print(
            f"{detection.pii_type}: "
            f"{detection.value}"
        )