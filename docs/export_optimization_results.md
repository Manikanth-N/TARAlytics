# Signal Export Optimization — Results (P0 + P1)

Implements the approved recommendations from
[the investigation](export_performance_investigation.md). All acceptance criteria met.
Suite 397 → **406 passing**.

---

## Benchmark — before vs after (full-flight, 1600×900, 300 k pts/signal)

| signals | before render (ms) | after on-screen (ms) | after export 2× (ms) | file-write (ms) | PNG KB | **speedup** |
|--------:|------------------:|---------------------:|---------------------:|----------------:|-------:|------------:|
| 1 | 100 | 2 | 3 | 3.6 | 9 | **42×** |
| 5 | 484 | 8 | 9 | 5.1 | 23 | **58×** |
| 20 | 1932 | **30** | 28 | 8.9 | 45 | **65×** |
| 50 | 5032 | 72 | 70 | 8.2 | 46 | **70×** |

*on-screen* = `grab()` at 1× (dark live theme); *export 2×* = `render_export_pixmap`
(light theme + legend, 2× DPI). Both now well under the budget; the former 5 s freeze
for 50 signals is gone.

---

## P0 — implemented

**1. Downsampling + clip-to-view.** `setDownsampling(auto=True, mode='peak')` +
`setClipToView(True)` on the main plot and each curve (and peak downsampling on the
range overview). Render only the visible range, peak-decimated to screen pixels —
**visually lossless** (min/max preserved per pixel), full-resolution data retained in
memory for analysis.
- *Acceptance:* latency cut **42–70×** (≥ 20× ✓); **20-signal full-flight = 30 ms**
  (< 100 ms ✓); no visible degradation (peak mode) ✓.

**2. Legend in exported images.** An in-plot pyqtgraph legend, auto-populated from
signal names, is **hidden during live use** (the StatsLegend already labels on screen)
and **shown only for the export render**, so every exported image is self-describing.
- *Acceptance:* exported images carry a labelled legend → usable in reports/PowerPoint
  without manual annotation ✓.

**3. Export light theme.** The export renders with a **white background, dark axis
labels/ticks, and a light legend**, then restores the live dark theme; UI chrome
(crosshair, tooltip) is hidden for a clean report image.
- *Acceptance:* white background, dark labels, print-readable ✓.

## P1 — implemented

**4. Clipboard image export.** A **Copy** toolbar button (and context-menu item) puts
the print-theme plot image on the clipboard (`clipboard().setPixmap(...)`) for direct
paste into PowerPoint/docs.

**5. 2× / 4× DPI.** A **DPI selector** (1× / 2× / 4×, default 2×) drives both PNG export
and clipboard; the plot is re-rendered at the chosen scale via a scaled `QPainter` for
crisp print/large-slide output (verified width scales exactly 2×/4×).

**SVG:** not pursued (per instruction); pyqtgraph's `SVGExporter` also crashes on these
plots.

---

## Investigation questions — now
- **Re-rendered during export?** Yes, but render is now ~30–70 ms (downsampled), not
  seconds.
- **UI blocking?** No longer a concern — even 50 signals export in ~70 ms.
- **Workspace updates triggered?** Still none (export emits no cursor/data signals).
- **Pixel-identical?** The 1× *on-screen* grab still matches the visible plot; the
  *export* is intentionally a light-theme + legend render (a report artifact), not a
  copy of the dark screen.

## Tests (`tests/test_export.py`, +9)
Downsampling/clip enabled (+ full-resolution data retained), legend
populated/hidden/updated, light-theme export with white bg + theme restore, DPI
scaling 2×/4×, legend shown during export render, clipboard image, default 2× DPI.
