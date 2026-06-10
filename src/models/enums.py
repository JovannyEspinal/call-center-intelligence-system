"""Shared enumerations for domain contracts."""

from __future__ import annotations

from enum import StrEnum


class AnalysisStatus(StrEnum):
    """Terminal status for a call analysis."""

    COMPLETED = "completed"
    SUPERVISOR_REVIEW = "supervisor_review"
    BLOCKED = "blocked"
    FAILED = "failed"


class SpeakerRole(StrEnum):
    """Inferred speaker role for transcript segments and evidence."""

    AGENT = "agent"
    CUSTOMER = "customer"
    UNKNOWN = "unknown"


class ComplianceSeverity(StrEnum):
    """Risk level assigned to a compliance flag."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResolutionStatus(StrEnum):
    """Factual resolution state extracted from a call."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    ESCALATED = "escalated"


class CallPhase(StrEnum):
    """Coarse position of a sentiment observation within a call."""

    OPENING = "opening"
    MIDDLE = "middle"
    CLOSING = "closing"


class SentimentTrend(StrEnum):
    """Deterministic direction of the customer sentiment trajectory."""

    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"
    UNKNOWN = "unknown"


class LLMProvider(StrEnum):
    """Supported LLM provider choices."""

    MOCK = "mock"
    OPENAI = "openai"
    GEMINI = "gemini"
    GROQ = "groq"


class PrivacyDataType(StrEnum):
    """Sensitive data categories detected and redacted by the system."""

    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    EMAIL = "email"
    PHONE = "phone"
    DATE_OF_BIRTH = "date_of_birth"
    ADDRESS = "address"
    ACCOUNT_NUMBER = "account_number"
    SECURITY_NUMBER = "security_number"
    VERIFICATION_CODE = "verification_code"


class AuditAction(StrEnum):
    """Business-significant pipeline events recorded in the audit trail."""

    ANALYSIS_STARTED = "analysis_started"
    INTAKE_COMPLETED = "intake_completed"
    TRANSCRIPTION_COMPLETED = "transcription_completed"
    TRANSCRIPTION_CACHE_USED = "transcription_cache_used"
    PROMPT_INJECTION_BLOCKED = "prompt_injection_blocked"
    PII_REDACTION_COMPLETED = "pii_redaction_completed"
    SUMMARY_COMPLETED = "summary_completed"
    QA_COMPLETED = "qa_completed"
    REPORT_CREATED = "report_created"
    SUPERVISOR_REVIEW_REQUIRED = "supervisor_review_required"
    ANALYSIS_FAILED = "analysis_failed"
    REPORT_DOWNLOADED = "report_downloaded"


class AudioFormat(StrEnum):
    """Supported audio container formats."""

    WAV = "wav"
    MP3 = "mp3"
    FLAC = "flac"
    M4A = "m4a"


class QADimension(StrEnum):
    """Quality dimensions from the global QA rubric."""

    PROFESSIONALISM = "professionalism"
    EMPATHY = "empathy"
    PROBLEM_RESOLUTION = "problem_resolution"
    COMPLIANCE = "compliance"
    COMMUNICATION_CLARITY = "communication_clarity"


QA_DIMENSION_WEIGHTS: dict[QADimension, float] = {
    QADimension.PROFESSIONALISM: 0.15,
    QADimension.EMPATHY: 0.20,
    QADimension.PROBLEM_RESOLUTION: 0.30,
    QADimension.COMPLIANCE: 0.20,
    QADimension.COMMUNICATION_CLARITY: 0.15,
}
