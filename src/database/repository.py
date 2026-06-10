"""Public persistence facade for analysis history and audit data."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.database.repositories import (
    AnalysisHistoryRepository,
    AuditEventRepository,
    CallAnalysisRepository,
    CallHistoryEntry,
    CallReportRepository,
    CallRepository,
    TranscriptionCacheRepository,
)
from src.models import (
    AuditEvent,
    Call,
    CallAnalysis,
    CallReport,
    TranscriptionCacheEntry,
)


class AnalysisRepository:
    """Single persistence entrypoint used by graph, services, and UI."""

    def __init__(self, session: Session) -> None:
        self.session = session
        calls = CallRepository(session)
        analyses = CallAnalysisRepository(session, calls)

        self.calls = calls
        self.analyses = analyses
        self.history = AnalysisHistoryRepository(session, analyses)
        self.reports = CallReportRepository(session)
        self.audit = AuditEventRepository(session)
        self.transcription_cache = TranscriptionCacheRepository(session, calls)

    def get_or_create_call(self, audio_hash: str) -> Call:
        return self.calls.get_or_create_call(audio_hash)

    def save_analysis(self, analysis: CallAnalysis) -> CallAnalysis:
        return self.analyses.save_analysis(analysis)

    def get_analysis(self, analysis_id: str) -> CallAnalysis | None:
        return self.analyses.get_analysis(analysis_id)

    def analysis_count_for_call(self, audio_hash: str) -> int:
        return self.analyses.analysis_count_for_call(audio_hash)

    def list_analyses_for_call(self, audio_hash: str) -> list[CallAnalysis]:
        return self.analyses.list_analyses_for_call(audio_hash)

    def list_analysis_history(self) -> list[CallHistoryEntry]:
        return self.history.list_analysis_history()

    def save_report(self, report: CallReport) -> CallReport:
        return self.reports.save_report(report)

    def get_report(self, analysis_id: str) -> CallReport | None:
        return self.reports.get_report(analysis_id)

    def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return self.audit.append_audit_event(event)

    def recent_audit_events(
        self,
        *,
        limit: int = 20,
        analysis_id: str | None = None,
    ) -> list[AuditEvent]:
        return self.audit.recent_audit_events(limit=limit, analysis_id=analysis_id)

    def audit_event_count(self, *, analysis_id: str | None = None) -> int:
        return self.audit.audit_event_count(analysis_id=analysis_id)

    def save_transcription_cache_entry(
        self,
        entry: TranscriptionCacheEntry,
    ) -> TranscriptionCacheEntry:
        return self.transcription_cache.save_transcription_cache_entry(entry)

    def get_transcription_cache_entry(
        self,
        audio_hash: str,
        *,
        expected_cache_version: str | None = None,
    ) -> TranscriptionCacheEntry | None:
        if expected_cache_version is None:
            return self.transcription_cache.get_transcription_cache_entry(audio_hash)
        return self.transcription_cache.get_transcription_cache_entry(
            audio_hash,
            expected_cache_version=expected_cache_version,
        )

    def commit(self) -> None:
        self.session.commit()
