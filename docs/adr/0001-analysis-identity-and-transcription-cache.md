# Analysis Identity and Transcription Cache

We will treat a **Call** as source audio that can have multiple **Call Analyses**, while the audio hash identifies reusable transcription work through a **Transcription Cache Entry**. This preserves analysis history when the same audio is reprocessed with different prompts, rubrics, model providers, scoring formulas, or application versions, instead of silently overwriting prior results.

**Considered Options**

- Use the audio hash as the unique identity for both the **Call** and the **Call Analysis**, which simplifies storage but loses meaningful historical differences.
- Allow multiple **Call Analyses** for the same **Call**, which requires explicit comparison metadata but preserves auditability and reviewer trust.

**Consequences**

- **Analysis History** is organized around **Call Analyses**, grouped by **Call**.
- Each **Call Analysis** captures an **Analysis Configuration** so differences can be explained later.
- Reusing a **Transcription Cache Entry** does not skip the audit trail for a new **Call Analysis**.
