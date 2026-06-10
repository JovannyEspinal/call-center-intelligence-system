"""SQLite schema for durable analysis history."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.models import TRANSCRIPTION_CACHE_VERSION


class Base(DeclarativeBase):
    """Base class for database rows."""


class CallRow(Base):
    """A source call keyed by audio hash."""

    __tablename__ = "calls"

    audio_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime]

    analyses: Mapped[list[CallAnalysisRow]] = relationship(
        back_populates="call",
        cascade="all, delete-orphan",
    )
    transcription_cache_entry: Mapped[TranscriptionCacheRow | None] = relationship(
        back_populates="call",
        cascade="all, delete-orphan",
    )


class CallAnalysisRow(Base):
    """A pipeline execution for a call."""

    __tablename__ = "call_analyses"

    analysis_id: Mapped[str] = mapped_column(String, primary_key=True)
    audio_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("calls.audio_hash"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String, index=True)
    configuration_json: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(index=True)

    call: Mapped[CallRow] = relationship(back_populates="analyses")
    report: Mapped[CallReportRow | None] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
    )


class CallReportRow(Base):
    """Persisted redacted report JSON for a successful analysis execution."""

    __tablename__ = "call_reports"

    analysis_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("call_analyses.analysis_id"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String, index=True)
    weighted_score: Mapped[float] = mapped_column(Float, index=True)
    report_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(index=True)

    analysis: Mapped[CallAnalysisRow] = relationship(back_populates="report")


class AuditEventRow(Base):
    """Append-only audit event row."""

    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    analysis_id: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String, index=True)
    details_json: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(index=True)


class TranscriptionCacheRow(Base):
    """Reusable redacted transcript keyed by call audio hash."""

    __tablename__ = "transcription_cache_entries"

    audio_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("calls.audio_hash"),
        primary_key=True,
    )
    redacted_transcript_json: Mapped[str] = mapped_column(Text)
    privacy_events_json: Mapped[str] = mapped_column(Text, default="[]")
    cache_version: Mapped[str] = mapped_column(
        String,
        default=TRANSCRIPTION_CACHE_VERSION,
    )
    created_at: Mapped[datetime] = mapped_column(index=True)

    call: Mapped[CallRow] = relationship(back_populates="transcription_cache_entry")
