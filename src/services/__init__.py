"""Cross-cutting services used by agents and UI."""

from src.services.analytics import DailyTrendRow, PipelineAnalyticsService
from src.services.audit import AuditSink, InMemoryAuditSink
from src.services.comparison import (
    AnalysisComparison,
    AnalysisComparisonError,
    AnalysisComparisonService,
    ConfigurationDifference,
    DimensionDelta,
    ReportComparison,
)
from src.services.history import (
    AnalysisHistoryRow,
    AnalysisHistoryService,
    CallHistoryGroup,
    filter_history_rows,
    max_flag_severity,
)
from src.services.llm_analysis import (
    AnalysisLLMClient,
    MockAnalysisClient,
    OpenAIAnalysisClient,
)
from src.services.report_downloads import (
    JsonReportDownload,
    PdfReportDownload,
    ReportDownloadError,
    ReportDownloadService,
)
from src.services.transcription import (
    FasterWhisperTranscriptionClient,
    MockTranscriptionClient,
    OpenAIDiarizedTranscriptionClient,
    TranscriptionClient,
)

__all__ = [
    "AnalysisComparison",
    "AnalysisComparisonError",
    "AnalysisComparisonService",
    "AnalysisHistoryRow",
    "AnalysisHistoryService",
    "AnalysisLLMClient",
    "AuditSink",
    "CallHistoryGroup",
    "ConfigurationDifference",
    "DailyTrendRow",
    "DimensionDelta",
    "PipelineAnalyticsService",
    "ReportComparison",
    "FasterWhisperTranscriptionClient",
    "InMemoryAuditSink",
    "JsonReportDownload",
    "MockAnalysisClient",
    "OpenAIAnalysisClient",
    "OpenAIDiarizedTranscriptionClient",
    "PdfReportDownload",
    "ReportDownloadError",
    "ReportDownloadService",
    "MockTranscriptionClient",
    "TranscriptionClient",
    "filter_history_rows",
    "max_flag_severity",
]
