# No Raw Audio Retention

The system will not retain original uploaded audio after processing. It keeps the audio hash, audio properties, redacted transcript data, **Call Report** data, **Audit Events**, and **Transcription Cache Entries**, reducing privacy and storage risk while still supporting repeat-upload detection by recomputing the hash.

**Considered Options**

- Retain uploaded audio to support exact replay and future reprocessing, which improves forensic debugging but increases privacy and storage obligations.
- Discard uploaded audio after processing, which limits replay options but better fits the project's privacy posture and lightweight SQLite-based persistence.

**Consequences**

- Reprocessing requires the user to upload or record the audio again.
- **Analysis History** cannot offer audio playback for prior calls.
- Temporary audio files must be cleaned up outside immutable history.
