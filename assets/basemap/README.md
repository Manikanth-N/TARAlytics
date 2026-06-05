# Bundled basemap assets

These files give TARAlytics offline geographic context (decision: offline-first,
works on first launch, no mandatory downloads):

| File | What | Size | Source |
|---|---|---|---|
| `world-base.pmtiles` | z0–z7 raster world base (roads, rivers, place names) | ~150–300 MB | OpenStreetMap (ODbL) |
| `ourairports/airports.csv` | aerodromes | ~3 MB | OurAirports (public domain) |
| `ourairports/runways.csv` | runways | ~2 MB | OurAirports (public domain) |
| `ATTRIBUTION.txt` | licensing / credits (always committed) | — | — |

The data files are **build artifacts** (git-ignored) — generate them before
packaging with:

```
python scripts/build_basemap_assets.py
```

This requires network access **at build time only**; the resulting application
needs no network to review a log. PyInstaller bundles this directory via
`TARAlytics.spec` (`('assets/basemap', 'assets/basemap')`), and the Inno Setup
installer copies the whole bundle, so the assets land beside the executable.

At runtime the app resolves these via `core/basemap/assets.py`; user-imported
region packs and per-flight extracts in `~/.taralytics/maps` take priority.
