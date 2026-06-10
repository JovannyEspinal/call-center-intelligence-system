from __future__ import annotations

import pytest

from src.models import PrivacyDataType, SpeakerRole
from src.models.redaction import contains_raw_sensitive_value
from src.services.security import RegexPIIRedactor


@pytest.fixture
def redactor() -> RegexPIIRedactor:
    return RegexPIIRedactor()


@pytest.mark.parametrize(
    ("raw_value", "placeholder", "data_type"),
    [
        ("123-45-6789", "[REDACTED_SSN]", PrivacyDataType.SSN),
        ("4111 1111 1111 1111", "[REDACTED_CREDIT_CARD]", PrivacyDataType.CREDIT_CARD),
        ("4111-1111-1111-1111", "[REDACTED_CREDIT_CARD]", PrivacyDataType.CREDIT_CARD),
        ("customer@example.com", "[REDACTED_EMAIL]", PrivacyDataType.EMAIL),
        ("CUSTOMER@EXAMPLE.COM", "[REDACTED_EMAIL]", PrivacyDataType.EMAIL),
        ("555-123-4567", "[REDACTED_PHONE]", PrivacyDataType.PHONE),
        ("(555) 123-4567", "[REDACTED_PHONE]", PrivacyDataType.PHONE),
        ("+1 555 123 4567", "[REDACTED_PHONE]", PrivacyDataType.PHONE),
    ],
)
def test_regex_redactor_redacts_required_pii_formats(
    redactor: RegexPIIRedactor,
    raw_value: str,
    placeholder: str,
    data_type: PrivacyDataType,
) -> None:
    result = redactor.redact_text(
        f"Customer said {raw_value}.",
        speaker_role=SpeakerRole.CUSTOMER,
        start_seconds=10,
        end_seconds=12,
    )

    assert raw_value not in result.redacted_text
    assert placeholder in result.redacted_text
    assert result.privacy_events[0].data_type is data_type
    assert result.privacy_events[0].placeholder == placeholder
    assert result.privacy_events[0].speaker_role is SpeakerRole.CUSTOMER
    assert result.privacy_events[0].start_seconds == 10
    assert result.privacy_events[0].end_seconds == 12


def test_regex_redactor_collects_all_matches_before_replacement(
    redactor: RegexPIIRedactor,
) -> None:
    result = redactor.redact_text(
        "Call me at 555-123-4567 or email customer@example.com. My SSN is 123-45-6789."
    )

    assert result.redacted_text == (
        "Call me at [REDACTED_PHONE] or email [REDACTED_EMAIL]. "
        "My SSN is [REDACTED_SSN]."
    )
    assert [event.data_type for event in result.privacy_events] == [
        PrivacyDataType.PHONE,
        PrivacyDataType.EMAIL,
        PrivacyDataType.SSN,
    ]


def test_regex_redactor_context_tracks_each_repeated_placeholder(
    redactor: RegexPIIRedactor,
) -> None:
    result = redactor.redact_text(
        "Primary phone is 555-123-4567. Backup phone is 555-987-6543."
    )

    assert result.redacted_text == (
        "Primary phone is [REDACTED_PHONE]. "
        "Backup phone is [REDACTED_PHONE]."
    )
    assert len(result.privacy_events) == 2
    assert "Primary phone" in result.privacy_events[0].context_excerpt
    assert "Backup phone" in result.privacy_events[1].context_excerpt


def test_regex_redactor_event_context_contains_no_raw_sensitive_values(
    redactor: RegexPIIRedactor,
) -> None:
    result = redactor.redact_text(
        "Please send confirmation to customer@example.com after the call."
    )

    assert not contains_raw_sensitive_value(result.redacted_text)
    for event in result.privacy_events:
        assert not contains_raw_sensitive_value(event.context_excerpt)
        assert "customer@example.com" not in event.context_excerpt


def test_regex_redactor_handles_text_without_pii(redactor: RegexPIIRedactor) -> None:
    result = redactor.redact_text("Customer asked about refund timing.")

    assert result.redacted_text == "Customer asked about refund timing."
    assert result.privacy_events == []


def test_regex_redactor_can_redact_analysis_metadata_like_text(
    redactor: RegexPIIRedactor,
) -> None:
    result = redactor.redact_text("caller_id=555-123-4567 department=billing")

    assert result.redacted_text == "caller_id=[REDACTED_PHONE] department=billing"
    assert result.privacy_events[0].data_type is PrivacyDataType.PHONE


@pytest.mark.parametrize(
    ("raw_text", "placeholder", "data_type"),
    [
        (
            "My email is Tatiana1989 at gmail.com.",
            "[REDACTED_EMAIL]",
            PrivacyDataType.EMAIL,
        ),
        (
            "My other mobile number that I'm using right now is 9876542310.",
            "[REDACTED_PHONE]",
            PrivacyDataType.PHONE,
        ),
        (
            "My date of birth is June 26, 1989.",
            "[REDACTED_DOB]",
            PrivacyDataType.DATE_OF_BIRTH,
        ),
        (
            "My address is 932, 1st Street, apartment A, Las Vegas, Nevada, 88901.",
            "[REDACTED_ADDRESS]",
            PrivacyDataType.ADDRESS,
        ),
        (
            "It's two, three, nine, seven, four, two, three, four, seven, nine.",
            "[REDACTED_ACCOUNT_NUMBER]",
            PrivacyDataType.ACCOUNT_NUMBER,
        ),
        (
            "That's the account number. Yes, it's 2397423479.",
            "[REDACTED_ACCOUNT_NUMBER]",
            PrivacyDataType.ACCOUNT_NUMBER,
        ),
        (
            "The last four digit of your social security number? It's 2465.",
            "[REDACTED_SECURITY_NUMBER]",
            PrivacyDataType.SECURITY_NUMBER,
        ),
        (
            "The code is 345-342.",
            "[REDACTED_VERIFICATION_CODE]",
            PrivacyDataType.VERIFICATION_CODE,
        ),
    ],
)
def test_regex_redactor_redacts_real_transcript_pii_shapes(
    redactor: RegexPIIRedactor,
    raw_text: str,
    placeholder: str,
    data_type: PrivacyDataType,
) -> None:
    result = redactor.redact_text(raw_text)

    assert placeholder in result.redacted_text
    assert result.privacy_events[0].data_type is data_type
    assert result.privacy_events[0].placeholder == placeholder
    assert "Tatiana1989 at gmail.com" not in result.redacted_text
    assert "9876542310" not in result.redacted_text
    assert "June 26, 1989" not in result.redacted_text
    assert "932, 1st Street" not in result.redacted_text
    assert "two, three, nine" not in result.redacted_text
    assert "2465" not in result.redacted_text
    assert "345-342" not in result.redacted_text


def test_regex_redactor_does_not_treat_store_purchase_as_address(
    redactor: RegexPIIRedactor,
) -> None:
    result = redactor.redact_text("I bought clothes for $150 at the BBB store.")

    assert result.redacted_text == "I bought clothes for $150 at the BBB store."
    assert result.privacy_events == []
