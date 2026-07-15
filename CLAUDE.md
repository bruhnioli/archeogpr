# Archaeological GPR Project Rules

- Raw OGPR files are read-only.
- Never overwrite or modify source radar files.
- Never hardcode binary offsets from a sample file.
- Read all offsets, sizes and data types from descriptors.
- Radar axis order is slice, channel, sample.
- Every processing function must preserve input data.
- Every future processing operation must record parameters and warnings.
- Every filter must be optional.
- Every filter must expose the removed or difference component for QC.
- AGC products must never be used for quantitative amplitude analysis.
- F-K filtering must never be enabled by default.
- Depth conversion requires an explicit propagation velocity.
- Header CRS metadata must not be assumed correct without validation.
- Do not automatically interpret anomalies as archaeological objects.
- Do not implement processing algorithms until their sprint is explicitly requested.
- An automatically detected time-zero/pick/onset is a signal-processing reference, never an independently calibrated physical measurement — say so explicitly wherever it is reported.
- Time-domain shifts (time-zero and beyond) must be channel-wide and constant, never independently fitted per trace, unless a future sprint explicitly requests otherwise.
- A shift/parameter that exceeds a configured limit must never be clipped silently. The default policy is to abort with a clear error before touching any data; clipping is only permitted via an explicit opt-in (`overflow_policy="clip"`), and any result produced that way must be marked non-canonical (`valid_for_downstream_processing=False`) and must never overwrite a canonical output without human review. (Revised in Sprint 2.1 — see `ADR_002_TimeZero_Reference_and_Shift_Policy.md`; the earlier "always clip" policy silently produced misaligned channels in the real Sprint 2 run.)

# Obsidian Knowledge Base Rules

- The Obsidian vault is located at:
  `obsidian/ArchaeoGPR_Vault/`

- At the start of a new session, read only:
  1. `obsidian/ArchaeoGPR_Vault/01_PROJECT_STATE/00_Claude_Context.md`
  2. `obsidian/ArchaeoGPR_Vault/01_PROJECT_STATE/01_Current_Project_State.md`
  3. `obsidian/ArchaeoGPR_Vault/01_PROJECT_STATE/02_Next_Development_Sprint.md`
  4. The active sprint note under `obsidian/ArchaeoGPR_Vault/02_SPRINTS/`

- Do not read the entire vault unless the task requires it.
- Code and passing tests are the source of truth.
- The vault must reflect the actual implementation state.
- Never mark an unimplemented feature as completed.
- Update the active sprint note after meaningful work.
- Create a session log after every substantial development session.
- Record important architectural decisions as ADRs.
- Store links to generated outputs; do not copy large binary outputs into the vault.
- Update `00_Claude_Context.md` whenever the active sprint, working features, risks or next task changes.
- A task is not complete until relevant vault notes are synchronized.
