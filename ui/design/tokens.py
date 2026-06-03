"""
Design tokens for TARAlytics.

Single source of truth for all colors, typography, spacing, and layout
constants. Every widget imports `T` from this module and references tokens
via dot notation (e.g. `T.brand.blue`, `T.layout.nav_rail_width`).

Colors are derived from the Tara UAV logo: `brand.blue` (#1A9FD5) is the
exact eagle-badge fill; surface tones are desaturated/darkened descendants
of that blue.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class _Surface:
    base:     str = '#060E18'
    panel:    str = '#0C1620'
    card:     str = '#111B28'
    elevated: str = '#182333'


@dataclass(frozen=True)
class _Border:
    subtle:  str = '#1A2A3E'
    default: str = '#233347'
    active:  str = '#2A4A6B'


@dataclass(frozen=True)
class _Brand:
    blue:        str = '#1A9FD5'
    blue_bright: str = '#22AADF'
    blue_deep:   str = '#0D6FA0'
    white:       str = '#FFFFFF'


@dataclass(frozen=True)
class _Text:
    primary:   str = '#E8EDF5'
    secondary: str = '#7A8FA8'
    muted:     str = '#3D5268'
    data:      str = '#C8D8E8'
    accent:    str = '#1A9FD5'


@dataclass(frozen=True)
class _Status:
    nominal:  str = '#00C896'
    caution:  str = '#FFB300'
    critical: str = '#FF3D3D'
    info:     str = '#1A9FD5'
    inactive: str = '#3D5268'


@dataclass(frozen=True)
class _Font:
    brand: str = 'Rajdhani'
    data:  str = 'JetBrains Mono'


@dataclass(frozen=True)
class _Size:
    xs:  int = 10
    sm:  int = 11
    md:  int = 13
    lg:  int = 15
    xl:  int = 18
    x2l: int = 24


@dataclass(frozen=True)
class _Weight:
    regular:  int = 400
    semibold: int = 600
    bold:     int = 700


@dataclass(frozen=True)
class _Spacing:
    px4:  int = 4
    px8:  int = 8
    px12: int = 12
    px16: int = 16
    px24: int = 24
    px32: int = 32
    px48: int = 48


@dataclass(frozen=True)
class _Layout:
    nav_rail_width:       int = 64    # Sprint-1 adjustment: 48 -> 64
    app_header_height:    int = 56
    flight_bar_height:    int = 28
    module_header_height: int = 40
    status_bar_height:    int = 28


@dataclass(frozen=True)
class _Duration:
    micro:    int = 60
    fast:     int = 150
    standard: int = 200
    medium:   int = 300


@dataclass(frozen=True)
class Tokens:
    surface:  _Surface  = field(default_factory=_Surface)
    border:   _Border   = field(default_factory=_Border)
    brand:    _Brand    = field(default_factory=_Brand)
    text:     _Text     = field(default_factory=_Text)
    status:   _Status   = field(default_factory=_Status)
    font:     _Font     = field(default_factory=_Font)
    size:     _Size     = field(default_factory=_Size)
    weight:   _Weight   = field(default_factory=_Weight)
    spacing:  _Spacing  = field(default_factory=_Spacing)
    layout:   _Layout   = field(default_factory=_Layout)
    duration: _Duration = field(default_factory=_Duration)


T = Tokens()
