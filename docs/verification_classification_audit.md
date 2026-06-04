# Verification Classification — Audit & Proposed Mapping

> **Status: AUDIT ONLY — no code changed.** Implementation is gated on approval of the
> classification matrix in §4. Decisions already taken are recorded in §0.

## 0. Decisions taken (review gate)

| # | Question | Decision |
|---|---|---|
| Q1 | Complete signed log, **no key loaded** | **UNKNOWN**, with message noting the keyless hash chain is intact and prompting to load the key |
| Q2 | **Wrong key** for this unit | **Keep `WRONG_KEY` as a distinct state** (7 operational states total, not 6) — it is a distinct, actionable user error vs "no key at all" |
| Q3 | Verifier hash-chain scan performance | **Port the `bytes.find()` (T1) optimization** to `_scan_hash_chain` in the same change |
| Q4 | Next step | **Save this audit and stop.** No code changes until the matrix below is approved |

Final operational state set (**7**): `VERIFIED`, `PARTIAL`, `UNSIGNED`, `INVALID`,
`CORRUPTED`, `UNKNOWN`, `WRONG_KEY`.

---

## 1. Executive summary

The verifier emits **7 raw engine states** that are surfaced almost verbatim across 9 UI
surfaces. Two are actively misleading:

- **`STRUCTURE_ERROR`** is a single bucket for *three unrelated root causes* — clean
  power-loss truncation, post-signing tampering, and malformed records. Log
  `00000011.BIN` (truncated, but with a **fully valid 48,705-chunk hash chain**) is shown
  identically to a tampered file.
- **`NOT_SIGNED`** reads as a failure to non-experts when it is a normal unsigned
  DataFlash log.

Crucially, **`full_verify()` returns at `check_structure()` *before* scanning the hash
chain**, so today it is structurally incapable of telling truncation from corruption.
That ordering is the root technical defect behind the misclassification.

---

## 2. Pipeline audit — every state and where it originates

**Data flow:** `full_verify(raw, pubkey)` → returns `dict{state,…}` → `VerifyRunnable.run`
emits it → `MainWindow._on_verify_done` → `AppState.set_verification()` builds
`VerifyResult` → `verification_changed` → **7 subscribers**.

### Every state the engine can produce

| State | Emitted at | Trigger |
|---|---|---|
| `NOT_LOADED` | `VerifyResult` default (`ui/app_state.py:33`) | Nothing loaded yet |
| `NOT_SIGNED` | `core/signature_verifier.py:357` | `raw[:2] != A5 01` |
| `STRUCTURE_ERROR` | `core/signature_verifier.py:370` | `check_structure()` fails — **3 sub-causes below** |
| `UNVERIFIED` | `core/signature_verifier.py:383` | `pubkey is None` |
| `VERIFIED` | `core/signature_verifier.py:303` / `:332` | Chain + Ed25519 valid |
| `KEY_MISMATCH` | `:295` / `:312` / `:338` | Bad key file, or fingerprint mismatch (wrong key) |
| `TAMPERED` | `:339` | Fingerprint plausible but all signature checks fail |

### `check_structure()` sub-causes folded into `STRUCTURE_ERROR` (`:145-163`)

1. `"Trailer magic missing — file truncated"` → **actually truncation** (log 11)
2. `"STRUCTURE CORRUPT … bytes added or removed after signing"` → **actually tampering**
3. `"File too small to contain trailer"` → **actually malformed/corrupt**

### The display surfaces and how each renders state today

| Surface | File | Current treatment |
|---|---|---|
| Verify tab badge + detail | `ui/widgets/signature_panel.py:203` | Raw state as badge text; `colors.py` STATE_BADGE_COLORS |
| Debrief panel | `ui/modules/mod_debrief.py:306` | `StatusBadge`, raw `result.state` |
| Context dock | `ui/widgets/cursor_dock.py:300` | `state.replace('_',' ')`; STRUCTURE_ERROR→caution, **unknowns→red** |
| Flight header | `ui/widgets/flight_header.py:62` | `StatusBadge` |
| Timeline canvas | `ui/widgets/timeline_canvas.py:617` | STRUCTURE_ERROR→**"partial / truncated"** (caution) ⚠ inconsistent |
| Workspace summary | `ui/modules/mod_workspace.py:49` | `StatusBadge` + lines |
| Evidence / PDF | `core/evidence_export.py:158`, `:209` | **Dumps raw `verification_state` string** |

`StatusBadge.COLORS` (`ui/widgets/badge.py:18`) only knows
VERIFIED/UNVERIFIED/TAMPERED/NOT_LOADED — **STRUCTURE_ERROR, NOT_SIGNED, KEY_MISMATCH fall
through to muted grey with no fill**, so on three of seven surfaces a corrupt log and an
unsigned log look identical. The mission overlay shows **no** verification text.

> **Inconsistency already in the tree:** `timeline_canvas._draw_verify` already renders
> `STRUCTURE_ERROR` as *"partial / truncated"* (amber), while `cursor_dock` and
> `signature_panel` render it red/critical. The codebase already disagrees with itself
> about what STRUCTURE_ERROR means — this proposal resolves that.

---

## 3. STRUCTURE_ERROR deep-dive — empirical evidence

| Log | Size | Signed magic | Trailer `1HCH` | Chunks | Hash chain | END record | Current → | Correct |
|---|---|---|---|---|---|---|---|---|
| `00000002` | 4.4 MB | ✓ | ✓ | 1,098 | valid | present | VERIFIED | **VERIFIED** |
| `00000011` | 193 MB | ✓ | **✗** | 48,705 | **valid** | **missing** | STRUCTURE_ERROR | **PARTIAL** |
| `00000012` | 440 MB | ✓ | ✓ | 110,766 | valid | present | (would VERIFY) | **VERIFIED** |

> Correction to a prior session note: **log 12 is a complete signed log, not unsigned.**
> Only log 11 is truncated.

**Log 11 is textbook battery-disconnect truncation:** the signed header and 48,705 chunk
records are all present and the hash chain is internally consistent end-to-end; the flight
simply ended before the END record + trailer were written. The data is fully usable and
its integrity *up to the truncation point* is cryptographically confirmable **without even
needing the public key** (the Blake2b chain is keyless; only the final Ed25519 signature
needs the key, and there is no final signature on a truncated log).

**Discriminator the new engine must apply when `check_structure` fails:**

```
scan hash chain (even on structure failure):
  chunks>0 AND chain.ok AND end_rec is None AND msg≈"trailer missing/truncated"  → PARTIAL
  chunks>0 AND NOT chain.ok (a chunk hash mismatched)                            → INVALID
  trailer present BUT data_start+data_len ≠ body length                          → INVALID (tamper)
  chunks==0 / unparseable records / file too small                              → CORRUPTED
```

---

## 4. Classification matrix  ← **APPROVAL GATE**

| Current State | Root Cause | Proposed State | User Message |
|---|---|---|---|
| `VERIFIED` | Chain valid + Ed25519 valid + END present | **VERIFIED** | "Signature valid. Complete signed log — integrity confirmed." |
| `STRUCTURE_ERROR` (trailer missing, chain valid, no END) | Power loss / battery disconnect before closure | **PARTIAL** | "Signed log interrupted before closure. Common cause: battery disconnect or power loss. Integrity confirmed up to interruption; telemetry remains available." |
| `STRUCTURE_ERROR` ("bytes added/removed after signing") | Signed range altered post-signing | **INVALID** | "Signed content was modified after signing. Possible tampering or corruption — treat data as untrusted." |
| `STRUCTURE_ERROR` ("file too small" / unparseable records) | Malformed verification structures | **CORRUPTED** | "Verification records are malformed and cannot be parsed. Log may be damaged." |
| `TAMPERED` | Fingerprint plausible, all signature checks fail | **INVALID** | "Signature validation failed. Possible tampering or corruption." |
| `NOT_SIGNED` | No `A5 01` magic | **UNSIGNED** | "Standard unsigned DataFlash log. No signature present — this is not an error." |
| `UNVERIFIED` (no key) | No public key loaded | **UNKNOWN** | "Verification not performed — no public key loaded. Hash chain intact ({n} chunks); load the unit's public key to confirm the signature." |
| `KEY_MISMATCH` | Wrong public key for this unit | **WRONG_KEY** | "Loaded public key does not match this log's unit. Load the correct key for this aircraft to verify." |
| `NOT_LOADED` | No log loaded yet | **UNKNOWN** | "No log loaded." |

**Color semantics:** VERIFIED green · PARTIAL amber · UNSIGNED neutral grey · INVALID red ·
CORRUPTED red · UNKNOWN muted grey · WRONG_KEY orange (distinct from red INVALID — it is a
*user* error, not a *log* failure). This makes "amber = usable but incomplete" distinct
from "red = do not trust" — the distinction log 11 needs.

---

## 5. UI mockups

**Context dock / header badges (one-liners):**
```
 Before                          After
 ● STRUCTURE ERROR   (red/grey)  ◐ PARTIAL          (amber)
 ● NOT SIGNED        (grey)      ○ UNSIGNED         (neutral)
 ● UNVERIFIED        (grey)      ○ UNKNOWN          (muted)
 ● TAMPERED          (red)       ● INVALID          (red)
 ● KEY_MISMATCH      (grey)      ◑ WRONG KEY        (orange)
```

**Verify tab (signature panel) — PARTIAL on log 11:**
```
┌─ Log Verification ─────────────────────────────────────────┐
│  ◐  PARTIAL                                                 │
│     Signed log interrupted before closure.                 │
│     Common cause: battery disconnect or power loss.        │
│     Integrity confirmed up to interruption.                │
│                                                            │
│  Algorithm     Blake2b-256 + Ed25519-Blake2b               │
│  Hash chain    48,705 chunks ✔  (valid up to interruption) │
│  Closure       END record / trailer  — not written         │
│  Signature     not present (log did not close)             │
│  Public key    SN-01_log_public_key.dat                    │
│  Telemetry     ✔ available — 48,705 chunks decoded         │
└────────────────────────────────────────────────────────────┘
```

**Verify tab — UNKNOWN (complete log, no key) per Q1:**
```
┌─ Log Verification ─────────────────────────────────────────┐
│  ○  UNKNOWN                                                 │
│     Verification not performed — no public key loaded.     │
│                                                            │
│  Hash chain    110,766 chunks ✔  (intact)                  │
│  Signature     not checked — load the unit's public key    │
│  Action        [ Load public key… ]                        │
└────────────────────────────────────────────────────────────┘
```

**Debrief panel — PARTIAL:**
```
◐ PARTIAL · Blake2b-256 + Ed25519-Blake2b
  48,705 chunks verified · log interrupted before closure
  Integrity confirmed to interruption — telemetry usable
```

**Evidence / PDF report (replaces the bare `| Verification | STRUCTURE_ERROR |`):**
```
## Verification

  Status               PARTIAL
  Operational meaning  Signed log interrupted before closure (no END
                       record). Hash chain valid for all 48,705 written
                       chunks. Common cause: battery disconnect / power loss.
  Investigator         Data is admissible up to the interruption point;
  guidance             integrity is cryptographically confirmed for the
                       written range. Absence of closure is expected for an
                       in-flight power loss and is NOT evidence of tampering.
                       To rule out tampering of the written range, confirm
                       the 48,705-chunk chain (shown valid here).
```

---

## 6. Required code changes (spec — not yet implemented)

1. **`core/signature_verifier.py` — `full_verify()` (the only logic change):**
   - On `check_structure` failure, **scan the hash chain before returning** and branch
     into PARTIAL / INVALID / CORRUPTED per §3.
   - Add `chain_valid` (keyless chain integrity, = `chain['ok']`) and `closed`
     (`end_rec is not None`) to the result dict so surfaces can say "valid up to
     interruption."
   - Rename terminal states: `NOT_SIGNED→UNSIGNED`, `UNVERIFIED→UNKNOWN`,
     `TAMPERED→INVALID`, `KEY_MISMATCH→WRONG_KEY` (per Q2, kept distinct).
   - **Q3:** port the `bytes.find()` (T1 memchr) optimization from `extract_signed_data`
     into `_scan_hash_chain` so PARTIAL detection on large truncated logs stays fast.

2. **New `core/verification_model.py`** (centralization): one table mapping each of the 7
   states → `{label, color, short_msg, operational_meaning, investigator_guidance}`. All
   surfaces consume this instead of hard-coding strings/colors. Removes the current 7-way
   duplication across `badge.py`, `colors.py`, `cursor_dock`, `timeline_canvas`.

3. **Display surfaces** (text/color only, driven by the model): `badge.py` COLORS,
   `colors.py` STATE_BADGE_COLORS, `cursor_dock._refresh_verify`,
   `timeline_canvas._draw_verify`, `signature_panel.update_verification`,
   `mod_debrief._on_verify`, `mod_workspace.refresh`.

4. **`core/evidence_export.py`** — replace the raw-state dump at `:158` and `:209` with the
   3-line Status / Operational meaning / Investigator guidance block.

5. **`ui/app_state.py` `AppState.set_verification` + `VerifyResult`** — carry the new
   `chain_valid` / `closed` fields through.

No change needed to `VerifyRunnable`, parser, analytics, snapshots, or workspace plumbing —
they are state-agnostic carriers.

---

## 7. Migration plan (phased, low-risk)

- **Phase 0 — model:** add `core/verification_model.py` + the classification table. No
  behavior change. New unit tests assert each sample log maps correctly (02→VERIFIED,
  11→PARTIAL, 12→VERIFIED; synthetic tamper→INVALID; unsigned→UNSIGNED; no-key→UNKNOWN;
  wrong-key→WRONG_KEY).
- **Phase 1 — engine:** implement the chain-scan-on-structure-failure branch + state
  renames + the `bytes.find()` scan optimization. Keep a `LEGACY_STATE_MAP` so any
  consumer still resolves.
- **Phase 2 — surfaces:** point all 7 displays + evidence export at the model. Pure
  presentation.
- **Phase 3 — tests:** update `test_signature_verifier.py` (asserts
  NOT_SIGNED/UNVERIFIED/STRUCTURE_ERROR/TAMPERED/KEY_MISMATCH at lines 108-130),
  `test_p2_evidence.py`, `test_cursor_dock.py`, `test_failure_sprint.py` to the new
  states; add the PARTIAL/log-11 regression.

---

## 8. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Mislabeling tamper as PARTIAL (security false-negative) | Low | **High** | PARTIAL requires `chain.ok==True AND end_rec is None`. Any chunk mismatch → INVALID. Trailer-present + length-mismatch → INVALID. Truncation and tampering are structurally distinct. |
| `_scan_hash_chain` now runs on truncated logs → slow on huge files | Med | Med | **Q3 accepted:** port the `bytes.find()` T1 optimization into `_scan_hash_chain` in the same change. |
| State-string churn breaks external/test consumers | High | Low | `LEGACY_STATE_MAP` + phased migration; all consumers are in-repo. |
| Users read "PARTIAL/amber" as "trustworthy" | Low | Med | Message explicitly scopes integrity to "up to interruption"; INVALID stays red. |
| Evidence/PDF wording implies admissibility we cannot guarantee | Low | Med | "Investigator guidance" is framed as procedure ("confirm the chain"), not a legal conclusion. Recommend a domain reviewer sign off on the copy. |
| WRONG_KEY vs UNKNOWN confusion | Low | Low | Distinct color (orange) + message ("load the correct key for this aircraft"). |

---

## 9. Verification continuity check

Analytics, evidence generation, workspace, and debrief consume `verification_state` only
as an opaque string for display; none branch on specific values for computation. Renaming
states is therefore presentation-safe. The one functional change (chain scan on structure
failure) only *adds* information to the result dict — existing fields keep their meaning.
Phase-3 tests pin this.

---

## 10. Recommendation

Approve the §4 matrix (or annotate changes). On approval, implement Phases 0–3 as one
reviewed change; expect updates to ~7 display files + the engine + evidence export + ~4
test files, all behind the centralized `verification_model`.
