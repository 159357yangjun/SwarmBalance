# P1.5 Research evidence freeze – 2026-10-10

This is an immutable, standalone **evidence copy manifest**, not a change to the simulation model.

## Long-lived archive location

Persistent ChatGPT File Library: `/SwarmBalance Evidence/SwarmBalance_P1_evidence_archive.zip`, together with `/SwarmBalance Evidence/SwarmBalance_P1_evidence_manifest.json`. Library upload succeeded; Google Drive upload did **not** succeed (provider rejected file reference); do not claim a Google Drive backup. Transfer the archive to institutional/public long-term object storage only with separate approval if needed. Artifacts in GitHub Actions have 30-day retention; the Library copy is the preserved snapshot.

| Inner ZIP member | Bytes | SHA-256 | GitHub run |
|---|---:|---|---|
| `P1_2_calibration_run38021072705.zip` | 7688 | `2f03c2545eb16918324027ee6915b2feed87a4d07c1be2dd1b2d6af560aa06f2` | 38021072705 |
| `P1_2_full_report.zip` | 228602 | `d7618f7a891b61b4e0a23d9004845916f1d29ef7ed121f48fc671006d5fdf832` | 38021072705 |
| `P1_4_full_shadow_report.zip` | 21166056 | `1a66c2bfe24cecfd3be30d3d8f3df840f753ba145ccc873d2b45b515ff70d347` | 38022786312 |

All 3 ZIP archives passed ZIP CRC checks before bundling. The final archive has these 3 original GitHub artifact ZIP files unmodified (nested) plus JSON manifest. `P1_2_full_report.zip` holds 126 entries; `P1_4_full_shadow_report.zip` holds 156 entries including compressed per-leg traces. Original model commits: P1.2 `f0f70f553dba76b54b02acc835561af1b8c4a25a`, P1.4 `d71d0f81cb44c896b0845e43eb82e42874cf0c6d`.

P1.3's 60-episode CSV and statistics JSON are committed separately on `p1-b-paired-analysis-v1` (`47c6e4582cd175151769ae8dd68383da805d3b3c`). This snapshot does not contain extra independent raw flight tests. E0/E1 frozen historical evidence was not edited or overwritten.

## Verification instructions

1. Extract outer `SwarmBalance_P1_evidence_archive.zip`.
2. SHA-256 each inner ZIP; compare hashes above and/or `SwarmBalance_P1_evidence_manifest.json`.
3. Run ZIP integrity verification against each inner ZIP.
4. Inspect `all_runs.csv` (P1.2) and `P1_B_SHADOW_PAIRS.csv`/ `P1_B_SHADOW_REPORT.json` (P1.4). Verify 60 episodes, 30 paired tapes, and 3 profiles; refer to original Action job logs for runtime proof.
5. Treat the archive as source evidence, not as validation against aircraft real-world measurements.

## Remaining limitations

- File Library snapshot success is not proof that files are independently hosted in the project's repo or object storage.
- This archive contains aggregate and per-leg experimental *simulator* traces. It does not prove safety after battery shortfall or physical accuracy.
- Future archiving of other historical E0/E1 artifacts is a separate task; **do not** claim they were archived here.
