# Signal Export — Performance & Quality Investigation

Measurement only (no optimization). Exercises the **real** PlotterTab export path
(`self._plot.grab()` → `pixmap.save()`). Harness: `scripts/profile_export.py`. Canvas
1600×900, 300 k points/signal over a 1200 s flight, pyqtgraph 0.14.0.

## What exists
- **PNG**: `self._plot.grab()` (re-renders the widget into a pixmap) → `pixmap.save(path,'PNG')`.
- **CSV**: masks the visible X-range and writes a DataFrame.
- **SVG**: **not implemented** (pyqtgraph has `SVGExporter`, but it **crashes** on this
  plot — `ValueError` in coordinate parsing — so it is not viable as-is).
- **Clipboard (image)**: **not implemented** (only tooltip *text* is copied);
  `clipboard().setPixmap(self._plot.grab())` works and would be a one-line add.

---

## 1. Timing table (PNG export)

| signals | window | visible pts | render ms | write ms | total ms | PNG KB |
|--------:|-------:|------------:|----------:|---------:|---------:|-------:|
| 1 | 10 s | 2.5 k | 73 | 1.5 | 74 | 8 |
| 1 | full | 300 k | 100 | 1.7 | 101 | 9 |
| 5 | 10 s | 12.5 k | 257 | 1.7 | 258 | 10 |
| 5 | full | 1.5 M | 484 | 1.8 | 486 | 13 |
| 20 | 10 s | 50 k | 1074 | 2.0 | 1076 | 13 |
| 20 | full | 6 M | 1932 | 1.6 | 1933 | 10 |
| 50 | 10 s | 125 k | 2554 | 1.6 | 2556 | 12 |
| 50 | 1 min | 750 k | 3449 | 2.0 | 3451 | 16 |
| 50 | 10 min | 7.5 M | 3675 | 1.6 | 3677 | 10 |
| 50 | full | 15 M | **5032** | 1.4 | **5034** | 8 |

- **Render time dominates total** (≈ 99.9 %); **file-write is ~1.5–2 ms** always — the
  PNG is tiny (8–17 KB; it's mostly thin lines).
- **Render scales ~linearly with signal count** (~70 ms per curve) and secondarily with
  visible points (full vs 10 s adds ~30–90 %). 50 signals × full flight = **5 s**.

## 2. Memory
Peak-RSS spikes on the **first** export at each new signal count (the undownsampled
render buffers): **+13 / +43 / +179 / +456 MB** for 1 / 5 / 20 / 50 signals; repeat
exports at the same count add ~0 (buffers reused). The PNG file itself is negligible.

## 3. Render time / 4. File-write time
Render = the `grab()` repaint (above). File-write = `QPixmap.save` ≈ **2 ms**
regardless of signals/window. **The bottleneck is rendering, not I/O.**

---

## Investigation questions

| Question | Answer |
|----------|--------|
| Are plots re-rendered during export? | **Yes** — `grab()` repaints the scene each time (no cached pixmap). |
| Can the visible plot buffer be reused? | **Not today** — there is no cached last-paint; `grab()` re-renders. It does reuse the laid-out *scene* (no data re-fetch), so the cost is paint, not data. |
| Does export block the UI? | **Yes** — `grab()`+`save()` run synchronously on the GUI thread. 50 signals = a **5 s freeze**. |
| Does export trigger workspace updates? | **No** — export emits **zero** `cursor_time_changed`/`data_changed` signals (measured); nothing else updates. |
| Are exported images pixel-identical to the visible plot? | **Yes** — two grabs of the same view are byte-identical, and `grab()` *is* the visible render. (`ImageExporter`/SVG render at a different resolution → **not** pixel-identical.) |

---

## Bottleneck analysis

**Root cause: the plot renders every point — downsampling is off.** The plotter never
calls `setDownsampling`/`setClipToView`, so a full-flight 50-signal view rasterises
15 M points each export. The single measured proof:

> 20 signals, full flight — `grab()` **1342 ms** undownsampled → **31 ms** with
> `setDownsampling(auto=True, mode='peak')` + `setClipToView(True)` = **~43× faster**,
> visually lossless at screen/export resolution.

`ImageExporter` (1194 ms for 20 signals) is **no faster** and is not pixel-identical;
it is not the answer. The cost is the paint of undownsampled points.

---

## Quality review (PDF / PowerPoint / print)

| Aspect | Finding |
|--------|---------|
| **Legend** | ❌ **Not in the export.** The legend is a separate `StatsLegend` widget, not part of `self._plot`, so `grab()` produces coloured lines **with no labels** — you cannot tell which signal is which in the image. |
| **Background** | ❌ **Dark** (`#1e1e2e`). Great on screen, poor on paper (wastes ink, low contrast), and clashes with light PDF/PPT/slides. |
| **Resolution** | ⚠️ Widget-size raster (~96 DPI). Sharp on screen, **pixelates** when scaled up in print/PowerPoint. |
| **Timestamps** | ⚠️ X-axis is **relative seconds** (`Time (s)`, `t − t_offset`); no absolute flight time / `HH:MM:SS` for report context. |
| Pixel fidelity | ✅ Exactly matches the on-screen plot. |

**Verdict:** functionally exports, but the **missing legend** and **dark background**
make the current PNG poor for documents/print.

---

## Recommended optimizations (in priority order — not yet applied)

1. **Enable downsampling + clip-to-view** (`setDownsampling(auto=True, mode='peak')`,
   `setClipToView(True)`). ~43× faster render, **fixes the UI freeze and the memory
   spike**, visually lossless. *The one change that matters most.*
2. **Put the legend in the export** — add an in-plot pyqtgraph legend, or composite the
   `StatsLegend` into the exported image. Critical for readability.
3. **Light/print export theme** — render the export with a white background + dark
   lines (an "Export for report/print" path) for PDF/PPT/paper.
4. **Wire clipboard-image export** — `clipboard().setPixmap(self._plot.grab())`
   (one-liner) for paste-into-PowerPoint.
5. **High-DPI export option** — render at 2–3× (devicePixelRatio or a target width) for
   crisp print/large slides.
6. **Absolute-time axis option** for report exports.
7. **Do not ship pyqtgraph `SVGExporter`** (crashes); if vector output is needed, use a
   matplotlib backend or fix the coordinate bug.
8. Threaded file-write is **not** worth it (~2 ms); once downsampling lands, the whole
   export is ~30–60 ms and the UI-blocking concern disappears.

**Headline:** export is render-bound because downsampling is off; enabling it is a ~40×
win and removes the UI freeze, after which the real gaps are **quality** (legend,
background, DPI) rather than speed.
