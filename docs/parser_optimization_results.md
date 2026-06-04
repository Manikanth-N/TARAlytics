# Parser Optimization Results (T1 + T2)

Implementation of the [performance investigation](parser_performance_investigation.md)
recommendations. **All targets met without native code.** Output is value-identical;
all 344 tests pass unchanged.

---

## Targets vs. achieved

| | target | achieved (440 MB) | |
|---|---|---|---|
| 193 MB parse | < 5 s | **2.88 s** | ✓ |
| 440 MB parse | < 10 s | **6.91 s** | ✓ |
| 440 MB peak RSS | < 2 GB | **1.46 GB** | ✓ |

---

## Timing (clean, per-process)

| log | baseline (T0) | +T1 find-scans | +T2 vectorized | total speedup |
|-----|-----:|-----:|-----:|-----:|
| 4 MB | 1.15 s | 0.45 s | **0.14 s** | 8.2× |
| 193 MB | 51.6 s | 22.8 s | **2.88 s** | **17.9×** |
| 440 MB | 115.3 s | 50.5 s | **6.91 s** | **16.7×** |

## Peak RSS

| log | baseline | +T2 | reduction |
|-----|-----:|-----:|-----:|
| 193 MB | 2.5 GB (12.7×) | **0.83 GB (4.3×)** | 3.0× |
| 440 MB | 5.6 GB (12.7×) | **1.46 GB (3.3×)** | 3.8× |

---

## T1 — `bytes.find()` scans (commit `09788c5`)

Replaced the two O(file-size) byte-by-byte Python scans with C-level `bytes.find()`:
- `signature_verifier.extract_signed_data` — jump to the next CHUNK record via
  `find(CHUNK_MAGIC)` instead of `pos += 1`.
- `log_parser._pass1_collect_fmt` — jump to each `A3 95 80` FMT header via `find()`.

**Byte-identical output**, validated on all three logs (`scripts/validate_t1.py`):

| | chunk scan | FMT discovery |
|---|---|---|
| 4 MB | 105× | 106× |
| 193 MB | 103× | 245× |
| 440 MB | 111× | 245× |

## T2 — numpy structured-dtype decode (commit `8ab6cfe`)

Replaced the per-record `pass2` walk + list-of-lists DataFrame build with:
1. **One lean offset-collection walk** — per `type_id`, the body-start offsets (same
   header/length/skip rules as before, no decoding).
2. **Per-type vectorized decode** — a packed structured `np.dtype` matching the
   `'<'`-packed struct; bytes gathered in `int32`-indexed **chunks** and viewed as the
   dtype; vectorized `c/C` (÷100) and `L` (÷1e7) scaling; `n/N/Z/a` decode; instance
   routing by splitting on the integer instance column.
3. **Existing filters unchanged** (`_apply_filters`): TimeUS range + `TimeS`,
   `FIELD_BOUNDS` clamp, `|x| < 1e9` float sanity.

**Memory:** the original file bytes are freed once the signed data is extracted; the
chunked `int32` gather bounds the transient; compact numpy dtypes replace boxed Python
objects (12.7× → 3.3× the file).

**Correctness:** proven **value-identical** to the old pipeline on 4/193/440 MB
(`scripts/validate_t2.py` compares every key, shape, and column NaN-aware). Chunk
exclusion, FMT validation, instance routing, and field-bounds behavior are preserved
exactly; only dtypes are more compact (e.g. `uint16`/`float32` instead of boxed
`int`/`float`), which the value comparison and the full suite confirm is equivalent.

---

## Conclusion
Pure-Python + numpy hits every target with margin (440 MB: 6.9 s / 1.46 GB). The
record-walk floor that the investigation flagged turned out to be comfortably within
budget once decoding/DataFrame-building were vectorized, so **the Cython decode kernel
is not required** and was not implemented (per instruction). ~17× faster end-to-end,
3.8× less memory, output unchanged.

Tools: `scripts/profile_parser.py` (stage profiler), `scripts/validate_t1.py`,
`scripts/validate_t2.py` (correctness + timing), `scripts/measure_parse.py`
(clean per-process RSS/timing).
