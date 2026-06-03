# AP_Logger Secure-Log Format Study
## Authoritative reference review (source of truth: `AP_Logger/`)

Performed before finalizing Sprint-1.2 parser corrections, per directive to treat
the logger implementation as authoritative rather than reverse-engineering logs.

---

## 1. Secure Log Format Analysis

### 1.1 Standard DataFlash record format (from `AP_Logger/LogStructure.h`)
```c
#define HEAD_BYTE1  0xA3
#define HEAD_BYTE2  0x95
#define LOG_PACKET_HEADER       uint8_t head1, head2, msgid;   // 3 bytes
#define LOG_PACKET_HEADER_LEN   3

struct PACKED log_Format {        // the FMT message (msgid 128)
    LOG_PACKET_HEADER;            // 3
    uint8_t type;                 // 1
    uint8_t length;               // 1
    char name[4];                 // 4
    char format[16];              // 16
    char labels[64];              // 64
};                               // = 89 bytes total
```
- **Every record begins with `A3 95 <msgid>`.**
- **FMT records are exactly `sizeof(log_Format) = 89` bytes.** Verified two ways:
  (a) struct arithmetic above; (b) the log's own first FMT record self-reports
  `length = 89`.

### 1.2 Format-type table (authoritative, `AP_Logger/README.md`)
`a b B h H i I f d n N Z L M q Q g` + legacy `c C e E`. Notable:
- `L` = int32 lat/lng, value ÷ 1e7.
- `c/C` = int16/uint16 × 100 ; `e/E` = int32/uint32 × 100 (legacy).
- `g` = float16.
- `n`=char[4], `N`=char[16], `Z`=char[64], `a`=int16[32].

### 1.3 Secure-signing layer — NOT in `AP_Logger/`
`AP_Logger/` is **stock ArduPilot logging**. An exhaustive search found **no**
HCH1 / SLOG / `1HCH` / blake2 / ed25519 / hash-chain / private-key code. The
secure-signing pipeline (chunk magic `0x48434831`, end magic `SLOG`, trailer
`1HCH`, Ed25519-Blake2b) is a **separate layer** applied around the stock log.

Therefore, for the *signing* format the authoritative reference remains
`core/signature_verifier.py`, **cross-validated against the actual log bytes**
(done below). For the *record/FMT* format, `AP_Logger/` is authoritative.

`AP_Logger/AP_Logger_File.h` confirms `HAL_LOGGER_WRITE_CHUNK_SIZE = 4096`, which
matches the observed 4096-byte spacing of secure chunk records.

---

## 2. Encoding / Decoding Data Flow

```
ENCODE (vehicle):
  messages (A3 95 id | body) ──▶ write buffer (4096-byte chunks)
        │
        ├─ FMT catalog written first (log_Format, 89 B each)
        │
   SECURE SIGNING LAYER (separate, not in AP_Logger):
        every chunk of data ──▶ insert CHUNK record:
              [ "HCH1"(4) | offset(4) | length(4) | hash(32) ] = 44 B
        at end ──▶ END record [ "SLOG"(4) | final_hash(32) | sig_len(1) | sig(64) ] = 101 B
        file head ──▶ signed header (A5 01 ... ) 64 B
        file tail ──▶ trailer "1HCH" + data_start + data_len ... = 145 B

  on-disk layout:
   [hdr 64][data_a][HCH1 rec@4096][data_b][HCH1 rec@8192]…[SLOG][trailer 145]
            └─ chunk(off,ln) points back at data_a ─┘

DECODE (TARAlytics):
  raw bytes ──▶ verifier: scan HCH1/SLOG, re-hash ranges, check Ed25519  (UNCHANGED)
            └─▶ parser:  MUST parse only the data ranges, excluding the 44 B
                         HCH1 records and the SLOG/trailer/header
  parsed DataFrames ──▶ metrics / plotter / replay / health
```

---

## 3. Parser-to-Logger Consistency Review

| Aspect | Logger (authoritative) | Current parser | Verdict |
|--------|------------------------|----------------|---------|
| Record header | `A3 95 msgid` (3 B) | same | ✅ |
| FMT record size | **89 B** (`sizeof(log_Format)`) | strides `3+87 = 90` | ❌ **off-by-one** |
| FMT body fields | type1,len1,name4,fmt16,labels64 = 86 | reads 86 B correctly | ✅ (only the *stride* is wrong) |
| `L` scaling | int32 ÷ 1e7 | `SCALE_L` ÷ 1e7 | ✅ |
| `c/C` scaling | int16/uint16 × 100 | `SCALE_C` ÷ 100 | ✅ |
| `e/E` | int32/uint32 × 100 (legacy) | `e`→float32; `E` **absent** | ⚠ discrepancy (see §5) |
| `g` (float16) | half-float | **absent** from FORMAT_MAP | ⚠ discrepancy (see §5) |
| Chunk records in data | inserted every 4096 B (44 B each) | **not excluded** → leak into data | ❌ **sentinel leak** |
| Chunk magic | `0x48434831` ("HCH1") | verifier matches | ✅ (verifier) |
| End/trailer | `SLOG` / `1HCH` 145 B | verifier matches | ✅ (verifier) |

---

## 4. Compatibility of Sprint-1.2 Fixes with the Logger

1. **FMT stride → 89.** Matches `sizeof(log_Format)` and the FMT's self-reported
   `length`. Authoritative-correct. Applies to all logs (signed/unsigned/truncated).
2. **Chunk exclusion.** Parse only the data ranges referenced by the verifier's
   chunk scan (`off, ln`), skipping the 44-byte HCH1 records and the SLOG/trailer.
   Reuses the verifier's chunk detection (no duplicate magic constants). On a
   **truncated** log (no SLOG/trailer, e.g. `00000011.BIN`) the chunk records are
   still present, so data ranges are still recoverable — fix degrades gracefully.
   On an **unsigned** log (no `A5 01`) there are no chunk records, so the parser
   uses the whole stream unchanged.
3. Both fixes are independent and additive; together validated to yield 92 types,
   0 sentinels, ATT/POS/RATE/XKF restored on the reference log.

---

## 5. Discrepancies Found (beyond the two approved fixes)

These are **documented, not yet actioned** (would be a separate parser-format
completeness item; they do **not** affect logs `00000002` which uses none of the
unknown chars):

- **`E` (uint32×100) missing** from `FORMAT_MAP` → any message using `E` fails to
  parse entirely. Fix: add `E`→uint32 with ÷100 scaling.
- **`g` (float16) missing** → messages using `g` fail. Fix: add `g`→struct `e`
  (2-byte half-float).
- **`e` mapped to float32**, but README lists `e` = int32×100. Needs empirical
  confirmation per-message before changing (current mapping may be intentional for
  modern logs; changing it risks regressing working fields). Used by GPS/GPA/XKF1/
  ORGN/CTUN in the reference log. **Flagged for verification, not changed.**

### Roadmap update
A follow-up **Sprint-1.3 — Parser Format Completeness** is proposed to add `E`/`g`
and resolve the `e` semantics with evidence. Not bundled into Sprint-1.2 to keep
the correctness release focused and its blast radius bounded.

---

## 6. Conclusion
`AP_Logger/` confirms the two Sprint-1.2 fixes are authoritative-correct:
FMT records are 89 bytes (not 90), and secure chunk records are 4096-spaced 44-byte
insertions that must be excluded from the data pass. The signing format is external
to `AP_Logger/`; the existing verifier remains its reference and already agrees with
the on-disk bytes. Three additional format-type discrepancies are documented for a
scoped follow-up.
