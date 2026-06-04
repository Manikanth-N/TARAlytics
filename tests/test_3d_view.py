"""3D replay perception tests (P2) — automatic vertical exaggeration.

A flight far wider than it is tall reads flat at a 1:1 Z scale, so the 3D view scales
Z up (capped) while telemetry/colour keep the TRUE altitude. Only the data-level
factor is unit-tested here; the on-screen result needs a real GPU display.
"""
import pytest

from ui.tab_3d_view import auto_z_exag


class TestVerticalExaggeration:
    def test_wide_flat_flight_gets_exaggerated(self):
        # 57 m wide, 14 m tall (log 12-like) → ~×2
        assert auto_z_exag(57.0, 14.0, False) == pytest.approx(2.0, abs=0.1)
        # very wide, low climb → capped at ×6
        assert auto_z_exag(500.0, 5.0, False) == 6.0

    def test_tall_flight_not_exaggerated(self):
        # already tall (log 02-like: 0.1 m wide, 10 m tall) → ×1
        assert auto_z_exag(0.1, 10.0, False) == 1.0

    def test_stationary_uses_fixed_factor(self):
        assert auto_z_exag(0.5, 0.5, True) == 5.0
