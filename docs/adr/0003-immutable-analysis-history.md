# Immutable Analysis History

User workflows will not delete **Call Analyses**, **Call Reports**, **Audit Events**, or **Transcription Cache Entries**. This preserves auditability and reviewer trust, while any local demo cleanup remains an explicit developer maintenance action outside the application workflow.

**Considered Options**

- Add delete/reset actions to simplify local demo cleanup, which improves convenience but weakens the audit model.
- Keep analysis history immutable from the application, which better matches the append-only audit requirement and regulated-domain posture.

**Consequences**

- **Analysis History** can be trusted as a durable review trail.
- **Audit Events** remain append-only and are not modified or removed by user actions.
- Local cleanup must be clearly separated from reviewer-facing application behavior.
