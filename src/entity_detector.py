from pydoc import text
import re
from typing import List

import spacy

from detector import PIIMatch


# Load spaCy's English NER model.
nlp = spacy.load("en_core_web_sm")


# ---------------------------------------------------------
# Company detection
# ---------------------------------------------------------

COMPANY_SUFFIX_PATTERN = re.compile(
    r"""
    (?<![A-Za-z])
    (
        [A-Z][A-Za-z0-9&.'()/,-]*
        (?:\s+[A-Za-z][A-Za-z0-9&.'()/,-]*){1,9}
        \s+
        (?:
            Private\s+Limited
            |
            Limited
            |
            LLP
            |
            Pvt\.?\s+Ltd\.?
            |
            Ltd\.?
            |
            Inc\.?
            |
            Corporation
            |
            Corp\.?
        )
    )
    (?![A-Za-z])
    """,
    re.VERBOSE,
)

# ---------------------------------------------------------
# Address indicators
# ---------------------------------------------------------

ADDRESS_TERMS = {
    "road",
    "rd",
    "street",
    "st",
    "lane",
    "nagar",
    "colony",
    "society",
    "apartment",
    "building",
    "bungalow",
    "bunglow",
    "floor",
    "marg",
    "park",
    "sector",
    "village",
    "taluka",
    "district",
    "maharashtra",
    "karnataka",
    "delhi",
    "mumbai",
    "pune",
    "bangalore",
    "bengaluru",
    "india",
}


POSTAL_CODE_PATTERN = re.compile(
    r"\b[1-9][0-9]{5}\b"
)


def detect_people(text: str) -> List[PIIMatch]:
    """
    Detect likely PERSON entities using spaCy plus conservative
    filtering to reduce false positives in financial/legal documents.
    """

    matches = []

    doc = nlp(
    text,
    disable=["parser", "lemmatizer", "textcat"]
)

    # Terms that commonly get incorrectly classified as PERSON
    # in financial/legal documents.
    excluded_terms = {
        # Financial / legal terminology
        "reference rate",
        "selling shareholder",
        "key managerial personnel",
        "key managerial",
        "secondary transfer",
        "mutual funds",
        "bid amount",
        "bidder's dp id",
        "upi bidders",
        "all offer-related",
        "offer price",
        "offer",
        "share transfer",
        "individual bidders",
        "qib bidders",
        "upi circulars",
        "the bid amount",
        "wilful defaulter",
        "bill",
        "gram jyoti",
        "dfi",
        "kisan urja suraksha",
        "operational",
        "particulars",
        "date",
        "telephone",
        "website",
        "floor price",
        "cap price",
        "registered broker",
        "share transfer agents",
        "acknowledgement slip",
        "schedule xiii",
        "escrow collection bank",
        "corrigenda thereto",
        "key",
        "kmp",

        # Address / location / building names
        "gopal house",
        "gopal bo",
        "deccan gymkhana",
        "buena monte",

        # Newspaper / publication text
        "widely circulated marathi daily newspaper",
    }

    # Location/address words.
    location_terms = {
        "taluka",
        "village",
        "pune",
        "mumbai",
        "marg",
        "road",
        "lane",
        "complex",
        "east",
        "west",
        "north",
        "south",
        "park",
        "hospital",
        "showroom",
        "chambers",
        "bhavan",
        "colony",
        "nagar",
        "reclamation",
        "churchgate",
        "house",
        "bo",
        "gymkhana",
        "monte",
        "marathe",
        "newspaper",
        "broker",
    
    }

    for entity in doc.ents:

        if entity.label_ != "PERSON":
            continue

        value = entity.text.strip()
        normalized = re.sub(r"\s+", " ", value).lower()

        # Must contain at least two words.
        words = value.split()

        if len(words) < 2 or len(words) > 5:
            continue

        # Reject known false positives.
        if normalized in excluded_terms:
            continue

        # Reject entities containing address/publication indicators.
        if any(
            term in normalized
            for term in [
                "marg",
                "house",
                "gymkhana",
                "newspaper",
                "registered broker",
            ]
        ):
            continue

        # Reject entities containing obvious location/address words.
        lower_words = set(normalized.replace("-", " ").split())

        if lower_words.intersection(location_terms):
            continue

        # A person's name should primarily consist of alphabetic
        # name tokens, allowing initials such as "N." or "K."
        valid_name = True

        for word in words:
            cleaned = word.strip(".,'()-")

            if not cleaned:
                continue

            # Allow initials: N., K., B.
            if len(cleaned) <= 2 and cleaned.replace(".", "").isalpha():
                continue

            if not cleaned.replace(".", "").isalpha():
                valid_name = False
                break

        if not valid_name:
            continue

        # Reject obvious business/entity phrases.
        business_words = {
            "limited",
            "private",
            "company",
            "corporation",
            "industrial",
            "automation",
            "waterloo",
            "nuvama",
            "website",
            "facility",
            "branch",
            "bank",
            "fund",
            "agents",
            "transfer",
        }

        if lower_words.intersection(business_words):
            continue
        

        # HUF is a legal/entity designation, not a person's name.
        if " huf" in normalized or normalized.endswith("huf"):
            continue

        if not looks_like_person_name(value):
            continue

        matches.append(
            PIIMatch(
                pii_type="PERSON",
                value=value,
                start=entity.start_char,
                end=entity.end_char,
            )
        )

    return matches


def detect_companies(text: str) -> List[PIIMatch]:
    """
    Detect company names using legal-entity suffixes.

    The detector intentionally favors precision:
    - Requires a legal company suffix.
    - Rejects generic phrases.
    - Rejects candidates that consist only of a suffix.
    - Removes common leading document words.
    """

    matches = []

    blocked_starts = {
        "our",
        "as",
        "set",
        "the",
        "for",
        "and",
        "from",
        "by",
        "including",
        "through",
        "prepared",
        "received",
        "based",
        "company",
    }

    blocked_exact = {
        "private limited",
        "limited",
        "pvt ltd",
        "pvt. ltd",
        "llp",
        "ltd",
        "corporation",
        "corp",
        "inc",
    }

    for match in COMPANY_SUFFIX_PATTERN.finditer(text):

        value = re.sub(r"\s+", " ", match.group()).strip()

        # Remove trailing punctuation.
        value = value.rstrip(".,;:")

        normalized = value.lower()

        # Reject suffix-only detections.
        if normalized in blocked_exact:
            continue

        words = value.split()

        if len(words) < 2:
            continue

        if len(words) > 10:
            continue

        # Reject obvious document prose.
        if words[0].lower() in blocked_starts:
            continue

        # Reject malformed candidates.
        if value.endswith(")") or value.startswith("("):
            continue

        matches.append(
            PIIMatch(
                pii_type="COMPANY",
                value=value,
                start=match.start(),
                end=match.end(),
            )
        )


                # Reject obvious non-company document text.
        bad_phrases = [
            "general information",
            "registered office",
            "corporate office",
            "anchor investor",
            "book running lead managers",
            "syndicate members",
            "registrar to the offer",
            "public offer account",
            "sponsor banks",
            "bankers to the offer",
            "care report prepared",
            "companies through",
            "family trust",
        ]

        if any(p in normalized for p in bad_phrases):
            continue

        # Reject candidates containing regulatory IDs.
        if re.search(
            r"\b(?:IN[A-Z]?\d{6,}|[A-Z]\d{5,}[A-Z]{2}\d{4}[A-Z0-9]+)\b",
            value,
            re.IGNORECASE,
        ):
            continue

                # Reject candidates containing too much numeric data.
        if sum(c.isdigit() for c in value) > 4:
            continue

    return matches


def looks_like_address(text: str) -> bool:
    """
    Decide whether a text block contains a physical/mailing address.

    Requires multiple address signals so that an entire paragraph
    containing an address is not incorrectly classified as one address.
    """

    lower_text = text.lower()

    address_terms = [
        "road",
        "rd.",
        "street",
        "st.",
        "lane",
        "nagar",
        "taluka",
        "village",
        "plot no",
        "plot number",
        "floor",
        "building",
        "industrial area",
        "industrial park",
        "complex",
        "marg",
        "pune",
        "mumbai",
        "maharashtra",
        "india",
    ]

    term_count = sum(
        1 for term in address_terms
        if term in lower_text
    )

    has_postal_code = bool(
        POSTAL_CODE_PATTERN.search(text)
    )

    # A genuine address should normally have several
    # address-related signals plus a postal code.
    return has_postal_code and term_count >= 2


def detect_addresses(text: str) -> List[PIIMatch]:
    """
    Detect physical/mailing addresses.

    Instead of treating an entire paragraph as an address, this
    detector extracts the address-like portion around a postal code.
    """

    matches = []

    # Indian PIN code: 6 digits
    postal_pattern = re.compile(r"\b\d{6}\b")

    # Words that commonly indicate an address.
    address_terms = (
        r"(?:road|rd\.?|street|st\.?|lane|nagar|marg|"
        r"village|taluka|plot|floor|building|industrial|"
        r"park|complex|area|phase|district|pune|mumbai|"
        r"maharashtra|india)"
    )

    # Look around each postal code.
    for postal_match in postal_pattern.finditer(text):

        postal_start = postal_match.start()
        postal_end = postal_match.end()

        # Look backwards up to ~250 characters.
        window_start = max(0, postal_start - 250)

        # Look forward only a small amount.
        window_end = min(len(text), postal_end + 30)

        window = text[window_start:window_end]

        # Find address-related words.
        term_matches = list(
            re.finditer(address_terms, window, re.IGNORECASE)
        )

        if not term_matches:
            continue

        # Start from the earliest address-related term.
        address_start = window_start + term_matches[0].start()

        # Try to move further backwards to include:
        # 11/3, 11/4 and 11/5, etc.
        prefix_start = address_start

        while prefix_start > window_start:
            previous_char = text[prefix_start - 1]

            if previous_char in ".\n":
                break

            prefix_start -= 1

        # Remove sentence-ending text before the actual address.
        candidate = text[prefix_start:window_end].strip()

        # Remove leading punctuation.
        candidate = candidate.lstrip(" ,:-")

        # Don't allow the candidate to continue into another sentence.
        sentence_parts = re.split(
            r"\.\s+(?=[A-Z])",
            candidate
        )

        if sentence_parts:
            candidate = sentence_parts[0].strip()

        # Final sanity checks.
        if not postal_pattern.search(candidate):
            continue

        if len(candidate) < 15:
            continue

        # Locate candidate in original text.
        candidate_start = text.find(
            candidate,
            max(0, prefix_start - 5),
            postal_end + 30
        )

        if candidate_start == -1:
            continue

        candidate_end = candidate_start + len(candidate)

        matches.append(
            PIIMatch(
                pii_type="ADDRESS",
                value=candidate,
                start=candidate_start,
                end=candidate_end,
            )
        )

    # Remove duplicates / overlapping addresses.
    unique = []
    seen = set()

    for match in matches:
        key = (match.start, match.end, match.value)

        if key not in seen:
            seen.add(key)
            unique.append(match)

    return unique



def detect_entities(text: str) -> List[PIIMatch]:
    """
    Detect names, companies and addresses.
    """

    matches = []

    # matches.extend(detect_people(text))
    # matches.extend(detect_companies(text))
    # matches.extend(detect_addresses(text))


    matches.extend(detect_people(text))
    company_matches = detect_companies(text)
    print("DEBUG COMPANY COUNT:", len(company_matches))
    matches.extend(company_matches)
    matches.extend(detect_addresses(text))


    return matches



def looks_like_person_name(value: str) -> bool:
    value = re.sub(r"\s+", " ", value.strip())

    words = value.split()

    # Full names should normally have 2–5 tokens.
    if not 2 <= len(words) <= 5:
        return False

    # Reject very long tokens.
    if any(len(word.strip(".,'()-")) > 25 for word in words):
        return False

    # Legal/business/document terms.
    blocked_words = {
        "telephone",
        "website",
        "bill",
        "company",
        "limited",
        "private",
        "industrial",
        "facility",
        "operational",
        "managerial",
        "personnel",
        "photo",
        "voltaic",
        "daily",
        "newspaper",
        "broker",
        "bank",
        "fund",
        "shareholder",
        "transfer",
        "bidder",
        "offer",
        "price",
        "gram",
        "jyoti",
        "dfi",
    }

    normalized_words = {
        word.lower().strip(".,'()-")
        for word in words
    }

    if normalized_words & blocked_words:
        return False

    # Every token should look like a name component.
    for word in words:
        cleaned = word.strip(".,'()-")

        # Initials such as N. or K.
        if len(cleaned) <= 2 and cleaned.replace(".", "").isalpha():
            continue

        if not cleaned.isalpha():
            return False

    return True