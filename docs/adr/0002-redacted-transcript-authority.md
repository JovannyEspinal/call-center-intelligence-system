# Redacted Transcript Authority

After redaction succeeds, the system will treat the **Redacted Transcript** as authoritative for analysis, display, reports, history, and comparison. Raw transcript text and raw sensitive values are not retained; the system keeps only redacted transcript content and **Privacy Event** metadata needed to explain what was protected.

**Considered Options**

- Persist raw transcripts and redact only at display or LLM boundaries, which improves forensic debugging but expands privacy risk.
- Retain only the **Redacted Transcript** after redaction succeeds, which reduces privacy exposure while preserving enough evidence for review.

**Consequences**

- **Transcript Evidence** and **Security Evidence** always use redacted text.
- **Call Reports** can show where sensitive information appeared without exposing raw values.
- Debugging redaction behavior must rely on tests, redaction metadata, and audit events rather than retained raw PII.
