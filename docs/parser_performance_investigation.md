# Parser Performance Investigation

Profiling of `core/log_parser.py` throughput on the 4 / 193 / 440 MB logs. No UI,
no correctness changes. Measured with `scripts/profile_parser.py` (stage timers +
cProfile + peak RSS), plus correctness-preserving prototypes for the two biggest
wins.

---

## 1. Timing Breakdown (measured)

| Stage | 4.4 MB | 193 MB | 440 MB | share |
|-------|------:|-------:|-------:|------:|
| 1 file read | 0.00 s | 0.07 s | 0.15 s | ~0.1 % |
| **2 signature chunk scan** | **0.48 s** | **21.34 s** | **46.86 s** | **~41 %** |
| **3 FMT discovery** | **0.24 s** | **9.60 s** | **21.30 s** | **~19 %** |
| **4 record decode + msg construct (pass2)** | **0.28 s** | **15.70 s** | **35.98 s** | **~31 %** |
| 5 DataFrame generation | 0.14 s | 4.93 s | 11.00 s | ~10 % |
| **TOTAL** | **1.15 s** | **51.6 s** | **115.3 s** | 100 % |

- Throughput is essentially **constant at ~368 k rows/s** regardless of size, and the
  **stage shares are identical across all three logs** — the cost is structural, not
  data-dependent.
- **Peak RSS = 12.7× the file size** at every size (193 MB → 2.5 GB, 440 MB → 5.6 GB)
  — the per-record list-of-lists of Python objects.

### Where >80 % of the time goes
```
chunk scan (41 %) + FMT discovery (19 %) + pass2 decode (31 %)  =  91 %
```
The two **O(file-size) byte-by-byte Python scans** (chunk + FMT) alone are **~60 %**.

### Why (root causes, from cProfile)
- **Chunk scan** — `signature_verifier.extract_signed_data` does
  `struct.unpack_from('<I', raw, pos)` at **every byte offset** looking for the chunk
  magic (`else: pos += 1`). 4.3 M `unpack_from` calls for a 4 MB file; ~440 M for the
  440 MB file. Pure O(file bytes) in the interpreter.
- **FMT discovery** — `_pass1_collect_fmt` byte-scans the whole file for the rare
  `A3 95 80` FMT header (`i += 1` until found), even though FMT records are ~100 and
  clustered at the start.
- **pass2 decode** — `_pass2_parse_all` is O(records): per record it does a `struct`
  unpack, a Python scaling loop, `get_instance_col`, a list-comprehension to drop the
  instance column, and a `dict`/`list.append`. 13.2 M iterations for the 440 MB log.
- **Memory** — every value becomes a boxed Python `int`/`float` in a per-record
  `list`, held in per-type `list`s until the DataFrame is built → 12.7× blow-up.

---

## 2. (A) Pure-Python / numpy optimizations

| Technique | Verdict | Evidence / effect |
|-----------|---------|-------------------|
| **`bytes.find()` for the chunk scan** | ★ **do first** | Replace `pos += 1` with `raw.find(CHUNK_MAGIC, pos+1)` (C `memchr`). **Prototype: 0.488 s → 0.0045 s = 110× faster, byte-identical output.** (Note: search only the CHUNK magic per gap; searching the single END magic each iteration is accidentally O(n²).) |
| **`bytes.find()` for FMT discovery** | ★ **do first** | Jump to each `A3 95 80` via `data.find(...)` then validate as today. **Prototype: 0.217 s → 0.0012 s = 182× faster.** |
| **`struct.Struct` caching** | already done | Each FMT's `struct.Struct` is built once in `_build_fmt_struct` and reused — no change needed. |
| **`numpy` vectorized decode** (structured dtype `np.frombuffer`) | recommended | Per-type: gather record bodies, `np.frombuffer` with a structured dtype, scale vectorized, build the DataFrame from the array. **Prototype on the busiest type: 2.6× on decode**, plus it removes the boxed-object memory and speeds DataFrame build. |
| **`memoryview`** | minor | Avoids copies on the per-record `data[o:o+sz]` slices; small once decode is vectorized. |
| **`mmap`** | not worth it | File read is 0.1 % of the time; mmap changes nothing material. |
| **Avoid per-record allocations** | important (memory) | The structured-array path eliminates the 12.7× boxed-object blow-up (numpy is compact) — the main memory fix. |

**Pure-Python ceiling.** Tiers above remove the two byte-scans (~60 %, proven) and
~2–3× of pass2+DataFrame. Projected: **193 MB → ~7–9 s, 440 MB → ~16–20 s**, and a
second, more aggressive rewrite (two-phase: one offset-collection walk + vectorized
per-type decode) could reach **193 MB ≈ 3–4 s, 440 MB ≈ 10–12 s**. But the
**record-walk loop is an irreducible ~13 M Python iterations** for the 440 MB log
(~6–8 s floor just to read each record's length and dispatch). So **pure Python can
hit 193 MB < 5 s, but lands 440 MB at the edge of / just over 10 s.**

---

## 3. (B) Native acceleration — evaluation

The remaining hot kernel after the find-based scans is the **record-walk + decode**
(visit each record, read length, struct-decode the body, scale, route by instance).
A tight byte loop producing typed columns — ideal for native code.

| Option | Fit for this kernel | Perf | Effort / risk | Packaging |
|--------|--------------------|------|---------------|-----------|
| **Cython** ★ | **excellent** — annotate the walk+decode into C, typed pointers, release the GIL, emit numpy arrays | walk+decode for 440 MB **< 2 s** (→ total < 5 s) | **moderate**, incremental, stays in the Python/pandas codebase | builds to `.so`/`.pyd`; fits the existing PyInstaller/wheel + Windows-installer flow cleanly |
| Rust (PyO3 / maturin) | excellent + memory-safe | marginally > Cython | **high** — new toolchain in CI, per-platform wheels, a separate crate to maintain | adds Rust to the Windows build pipeline |
| C++ (pybind11) | excellent | ≈ Rust | high, **memory-unsafe** — risky for parsing untrusted files | manual per-platform build |
| Numba | **poor** — irregular per-type binary formats, `struct`/instance routing don't fit `@njit` homogeneous-loop model; JIT warm-up | n/a | would need a full restructure | n/a |

**Recommendation: Cython** for the one hot kernel (`_pass2` walk+decode → per-type
numpy arrays), if the aggressive targets are firm. It gives the needed margin
(440 MB < 10 s comfortably) with the least toolchain/packaging disruption, keeps the
rest of the parser in Python, and is memory-safe. Rust/C++ are overkill for the gain
here and add CI/packaging burden; Numba does not fit the workload.

---

## 4. Recommended plan (correctness unchanged throughout)

1. **Tier 1 — find-based scans (mandatory, ~free, do now).** `bytes.find()` for the
   chunk scan and FMT discovery. **Removes ~60 % of total time** (proven 110× / 182×,
   identical output). After this: 193 MB ≈ 21 s, 440 MB ≈ 48 s.
2. **Tier 2 — numpy structured-dtype decode + array-built DataFrames.** ~2–3× on the
   remaining pass2 + DataFrame, and **fixes the 12.7× memory blow-up** (→ ~1.5–2×).
   After this: **193 MB ≈ 5–8 s, 440 MB ≈ 12–18 s** (193 MB target met or near).
3. **Tier 3 — Cython walk+decode kernel (only if the firm targets demand it).** The
   one native step. Brings **193 MB ≈ 2–3 s and 440 MB ≈ 4–6 s**, hitting both targets
   (193 < 5 s, 440 < 10 s) with margin.

Correctness is preserved at every tier: the same chunk-boundary contract
(`extract_signed_data` magics/sizes), the same FMT validation, the same instance
routing and field-bounds filtering — only the *mechanism* of scanning/decoding
changes, not the *result*.

### Targets vs tiers
| | now | +T1 | +T2 | +T3 (Cython) | target |
|---|---:|---:|---:|---:|---:|
| 193 MB | 51.6 s | ~21 s | ~5–8 s | **~2–3 s** | < 5 s |
| 440 MB | 115 s | ~48 s | ~12–18 s | **~4–6 s** | < 10 s |

**Bottom line:** the single highest-leverage change is the trivial, proven
`bytes.find()` fix for the two byte-by-byte scans (≈60 % for free). Tier 2 hits the
193 MB target and fixes memory. Hitting **440 MB < 10 s with margin requires one
Cython kernel** for the record walk+decode — recommended over Rust/C++/Numba.
