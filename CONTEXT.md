# Call Center Intelligence System

This context defines the domain language for a call center analysis product that turns call audio into auditable quality and compliance outputs.

The delivery strategy is a focused production slice: real orchestration, contracts, security, persistence, reports, and tests, with pragmatic choices for UI polish, diarization, and local demo performance.

If time is constrained, prioritize security correctness, pipeline correctness, deterministic scoring with evidence, persistence and reports, test coverage, observability, provider breadth, and finally UI polish.

## Language

**Call**:
One uploaded or recorded audio interaction that enters the analysis pipeline, identified by its audio hash and optional metadata.
_Avoid_: Recording, audio file

**Call Analysis**:
The pipeline run and resulting state for a **Call**, whether completed, failed, or flagged for review.
_Avoid_: Job, processing result, run

**Analysis Difference**:
An explanation of why two **Call Analyses** for the same **Call** produced different results.
_Avoid_: Diff, change log

**Analysis Result Comparison**:
A structured comparison of reviewer-relevant output fields between two **Call Reports**.
_Avoid_: Report diff, output diff

**Analysis History**:
The browsable record of prior **Call Analyses** and their reports, statuses, comparisons, and audit summaries.
_Avoid_: All MP3 History, call history

**Pipeline Observability**:
The operational view of **Call Analysis** throughput, outcomes, audit events, and tracing status.
_Avoid_: Analysis history, report browser

**Successful Analysis Execution**:
A **Call Analysis** that produced a **Call Report**, whether routine-completed or requiring **Supervisor Review**.
_Avoid_: Completed analysis, success

**Analysis Configuration**:
The captured conditions under which a **Call Analysis** was produced.
_Avoid_: Config, settings, runtime options

**Analysis Metadata**:
Optional user-provided context associated with a **Call Analysis**.
_Avoid_: Trusted metadata, call submission

**Call Report**:
The assembled artifact generated from a **Call Analysis** for review or download.
_Avoid_: Report, output, artifact

**Report Download**:
A temporary downloadable rendering of a **Call Report**.
_Avoid_: Stored report file, artifact

**Call Summary**:
A factual, non-evaluative description of a **Call**.
_Avoid_: QA summary, evaluation

**Customer Sentiment Trajectory**:
The customer's apparent emotional state across a **Call**, based on the **Redacted Transcript**.
_Avoid_: Sentiment, agent sentiment, call sentiment

**Action Item**:
A concrete follow-up commitment from a **Call**, owned by the agent, customer, or organization.
_Avoid_: Next step, task

**Compliance Flag**:
A specific policy or regulatory concern found in a **Call Analysis**, with severity and **Transcript Evidence**.
_Avoid_: Compliance score, issue

**Compliance Severity**:
The risk level assigned to a **Compliance Flag**.
_Avoid_: Priority, flag level

**Privacy Event**:
Sensitive information appearing in a **Call** or **Analysis Metadata** that requires redaction but is not automatically an agent compliance violation.
_Avoid_: PII finding, compliance flag

**Weighted QA Score**:
The deterministic overall quality score calculated from quality dimension scores and their weights.
_Avoid_: Overall score, LLM score

**QA Rubric**:
The quality evaluation standard used to score a **Call Analysis**.
_Avoid_: Department rubric, scorecard

**LLM Analysis Client**:
The boundary for structured summary and QA analysis over a **Redacted Transcript**.
_Avoid_: Provider switch, model wrapper

**Transcription Stage**:
The **Call Analysis** stage that turns a **Call** into transcript segments.
_Avoid_: Whisper step, speech-to-text adapter

**Supervisor Review**:
A terminal status for a **Call Analysis** whose **Call Report** was produced but requires human attention before routine use.
_Avoid_: Escalation, manual review

**Blocked Analysis**:
A terminal outcome where a **Call Analysis** stops because continuing would be unsafe.
_Avoid_: Failed analysis, error

**Failed Analysis**:
A terminal outcome where a **Call Analysis** cannot produce a **Call Report** because the system could not complete required processing.
_Avoid_: Blocked analysis, error

**Transcription Cache Entry**:
A reusable transcript result keyed by the audio hash of a **Call**.
_Avoid_: Cache, transcript cache

**Transcript Evidence**:
A redacted excerpt from a **Call** transcript with speaker label and timestamp range that supports an analysis claim.
_Avoid_: Citation, quote, reference

**Security Evidence**:
A redacted transcript excerpt used to explain why a **Call Analysis** was blocked for safety.
_Avoid_: Transcript evidence, security log

**Redacted Transcript**:
The privacy-safe transcript text used for analysis, display, reports, and history.
_Avoid_: Clean transcript, scrubbed transcript

**Speaker Role**:
The inferred role of the speaker for a transcript segment.
_Avoid_: Speaker label, diarization label

**Transcript Quality Warning**:
A warning that a **Call** transcript may be unreliable enough to affect downstream analysis.
_Avoid_: Low confidence, bad audio

**Audit Event**:
An immutable timestamped record of a business-significant event during a **Call Analysis**.
_Avoid_: Log, audit log row

## Relationships

- A **Call** can have one or more **Call Analyses** over time if reprocessing is allowed.
- Multiple **Call Analyses** for the same **Call** remain visible in history.
- **Analysis History** is organized around **Call Analyses**, grouped by **Call** when the same audio appears more than once.
- The default **Call Analysis** for a **Call** is the latest usable analysis, while older analyses remain visible.
- **Analysis Metadata** is untrusted until checked for sensitive information.
- **Analysis Metadata** containing ordinary sensitive information is redacted rather than rejected.
- Malicious **Analysis Metadata** can cause a **Blocked Analysis**.
- Prompt injection checks apply to **Analysis Metadata** as well as the **Redacted Transcript**.
- **Analysis Metadata** can provide context but cannot support quality scores or **Compliance Flags**.
- **Pipeline Observability** summarizes operational activity across **Call Analyses** rather than browsing individual **Call Reports**.
- The **LLM Analysis Client** allows OpenAI-backed analysis without changing analysis domain behavior.
- The **Transcription Stage** is a pipeline stage independent of the specific speech-to-text adapter.
- **Successful Analysis Execution** includes completed analyses and analyses requiring **Supervisor Review**.
- A **Call Analysis** produces zero or one **Call Reports**.
- A **Report Download** is generated from a persisted **Call Report** rather than treated as the durable record.
- JSON **Report Downloads** contain the full redacted **Call Report**.
- PDF **Report Downloads** emphasize reviewer-facing summary, scores, flags, privacy events, and evidence.
- A **Call Analysis** records one or more **Audit Events**.
- The application does not delete **Call Analyses**, **Call Reports**, **Audit Events**, or **Transcription Cache Entries** through user workflows.
- Temporary processing artifacts are not part of immutable **Analysis History**.
- Original uploaded audio is not retained after processing.
- **Analysis History** does not provide playback of prior **Calls**.
- Creating a **Call Report** records an **Audit Event**.
- Downloading a **Call Report** records an **Audit Event** only when reviewer or session identity is available.
- A **Transcription Cache Entry** can be reused by multiple **Call Analyses** for identical **Calls**.
- Reusing a **Transcription Cache Entry** does not replace the **Audit Events** for a new **Call Analysis**.
- A **Call Report** uses **Transcript Evidence** to support summary claims, quality scores, and compliance flags.
- A **Call Summary** describes what happened in a **Call** without judging agent performance.
- A **Call Summary** can include a **Customer Sentiment Trajectory**.
- A **Call Summary** can include one or more **Action Items**.
- A **Compliance Flag** is distinct from the compliance quality score.
- The compliance quality score evaluates agent behavior, not customer-created privacy risk.
- A **Privacy Event** can coexist with a **Compliance Flag** when agent behavior mishandles sensitive information.
- **Privacy Events** are visible in **Call Reports** without exposing raw sensitive values.
- High-risk **Privacy Events** can require **Supervisor Review** even without a **Compliance Flag**.
- A **Blocked Analysis** can still record **Privacy Events**.
- A critical **Compliance Severity** requires **Supervisor Review**.
- A **Weighted QA Score** belongs to a **Call Report** and is not supplied by the LLM.
- The system uses one global **QA Rubric**.
- The **QA Rubric** evaluates agent performance, not the entire call experience.
- Each quality dimension score in a **Call Report** requires at least one **Transcript Evidence** item.
- The same **Transcript Evidence** can support multiple claims when each claim explains why that evidence applies.
- **Transcript Evidence** always comes from the **Redacted Transcript**.
- **Transcript Evidence** includes a **Speaker Role** when the speaker can be inferred.
- **Transcript Evidence** with an unknown **Speaker Role** cannot support speaker-specific accountability claims.
- A **Redacted Transcript** is authoritative for user-facing analysis, display, reports, and history.
- Only the **Redacted Transcript** is retained after redaction succeeds.
- A **Blocked Analysis** can include **Security Evidence** but does not include **Transcript Evidence** for QA or compliance claims.
- A **Transcript Quality Warning** can appear on a completed **Call Report** or require **Supervisor Review** when it undermines confidence in the analysis.
- A severe **Transcript Quality Warning** can require **Supervisor Review** without creating a **Compliance Flag**.
- An **Analysis Difference** compares two **Call Analyses** for the same **Call**.
- An **Analysis Difference** is explained by comparing the **Analysis Configurations** of two **Call Analyses**.
- An **Analysis Result Comparison** describes what changed between two **Call Reports**.
- A **Supervisor Review** outcome still has a **Call Report**.
- A **Blocked Analysis** does not produce a **Call Report**.
- A **Failed Analysis** does not produce a **Call Report**.

## Example dialogue

> **Dev:** "If two reviewers upload the same **Call**, do we create two **Call Reports**?"
> **Domain expert:** "We may create two **Call Analyses**, but both can reuse the same **Transcription Cache Entry** because the audio hash is identical."

## Flagged ambiguities

- "call" can refer to the source audio or its analysis output; resolved: **Call** is the source interaction, while **Call Analysis** is the processing result.
- Audio hash identifies reusable transcription work, not a unique **Call Analysis**.
- Safety stops and system failures are distinct; resolved: a prompt injection stop is a **Blocked Analysis**, not a **Failed Analysis**.
- The raw transcript and **Redacted Transcript** are distinct; resolved: the raw transcript may exist transiently for redaction but is not retained after redaction succeeds.
- Prompt injection can block analysis before redaction completes, but any retained or displayed **Security Evidence** is redacted.
