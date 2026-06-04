"""Centralized verification classification — the single source of truth.

The verifier (`core.signature_verifier.full_verify`) emits one of seven *operational*
states. This module owns, for each state, the display label, color, semantic tone, and
the human-facing copy (short message, operational meaning, investigator guidance) that
every UI surface and every export consumes. No other module should hard-code a
verification state string or a verification color.

Operational states (approved 2026-06-04):
    VERIFIED   complete signed log, chain + Ed25519 valid
    PARTIAL    signed log interrupted before closure; chain valid for written chunks
    UNSIGNED   standard unsigned DataFlash log (not an error)
    INVALID    chain mismatch / signature failure / post-signing modification
    CORRUPTED  verification records malformed or unreadable
    UNKNOWN    not attempted (no public key loaded); chain may still be evaluated
    WRONG_KEY  a key is loaded but does not match this aircraft/log
"""
from __future__ import annotations
from dataclasses import dataclass

# ── Operational states ──────────────────────────────────────────────────────────
VERIFIED  = 'VERIFIED'
PARTIAL   = 'PARTIAL'
UNSIGNED  = 'UNSIGNED'
INVALID   = 'INVALID'
CORRUPTED = 'CORRUPTED'
UNKNOWN   = 'UNKNOWN'
WRONG_KEY = 'WRONG_KEY'

ALL_STATES = (VERIFIED, PARTIAL, UNSIGNED, INVALID, CORRUPTED, UNKNOWN, WRONG_KEY)

# Theme-aligned hexes (mirror ui/design/tokens status colors so theme-aware surfaces
# can use these directly via QColor):
#   #00C896 status.nominal · #FFB300 status.caution · #FF3D3D status.critical
#   #7A8FA8 text.secondary  · #E65100 orange (user-action, distinct from red)
_GREEN, _AMBER, _RED, _MUTED, _ORANGE = '#00C896', '#FFB300', '#FF3D3D', '#7A8FA8', '#E65100'


@dataclass(frozen=True)
class StateInfo:
    state: str
    label: str                  # display label (human-facing)
    tone: str                   # semantic severity: good|warn|bad|neutral|muted
    color: str                  # theme-aligned hex (dark surfaces / QColor)
    fg: str                     # badge foreground (light/print theme)
    bg: str                     # badge background (light/print theme)
    short_msg: str              # one-line operational summary
    operational_meaning: str    # what it means for the data
    investigator_guidance: str  # what the user should do / how to read it


_MODEL = {
    VERIFIED: StateInfo(
        VERIFIED, 'VERIFIED', 'good', _GREEN, '#198754', '#d1e7dd',
        'Complete signed log — integrity confirmed.',
        'Hash chain and Ed25519 signature both validated over a complete signed log.',
        'Log is complete and cryptographically intact. No integrity concerns.'),
    PARTIAL: StateInfo(
        PARTIAL, 'PARTIAL', 'warn', _AMBER, '#856404', '#fff3cd',
        'Signed log interrupted before closure.',
        'Signed log interrupted before closure (no END record / trailer). Hash-chain '
        'integrity is confirmed for all written chunks; the final Ed25519 signature is '
        'unavailable because log closure was not completed.',
        'Common cause is battery disconnect or power loss. Telemetry remains available '
        'and usable. Integrity is confirmed for all written chunks; absence of closure '
        'is expected for an in-flight power loss and is not, by itself, evidence of '
        'tampering.'),
    UNSIGNED: StateInfo(
        UNSIGNED, 'UNSIGNED', 'neutral', _MUTED, '#6c757d', '#e2e3e5',
        'Standard unsigned DataFlash log.',
        'No signature structures are present. This is a standard unsigned DataFlash log.',
        'Not an error. Cryptographic verification does not apply to unsigned logs.'),
    INVALID: StateInfo(
        INVALID, 'INVALID', 'bad', _RED, '#dc3545', '#f8d7da',
        'Signature validation failed — treat data as untrusted.',
        'Signature structures are present and verification was attempted, but a '
        'hash-chain mismatch, signature failure, or post-signing modification was '
        'detected.',
        'Possible tampering or corruption. Treat the data as untrusted and preserve the '
        'original file for forensic review.'),
    CORRUPTED: StateInfo(
        CORRUPTED, 'CORRUPTED', 'bad', _RED, '#dc3545', '#f8d7da',
        'Verification records malformed — integrity undeterminable.',
        'Verification structures are malformed or unreadable; integrity cannot be '
        'determined.',
        'The log may be physically damaged. Recover a clean copy if possible — integrity '
        'cannot be asserted from this file.'),
    UNKNOWN: StateInfo(
        UNKNOWN, 'UNKNOWN', 'muted', _MUTED, '#856404', '#fff3cd',
        'Verification not performed — no public key loaded.',
        'Verification has not been attempted because no public key is loaded. The keyless '
        'hash chain may still be evaluated.',
        "User action required: load the unit's public key to confirm the signature."),
    WRONG_KEY: StateInfo(
        WRONG_KEY, 'WRONG KEY', 'warn', _ORANGE, '#e65100', '#ffe0b2',
        'Public key does not match this aircraft.',
        "A public key is loaded but it does not match this log's unit (key fingerprint "
        'mismatch).',
        'User action required: load the correct public key for this aircraft, then '
        're-verify. Distinct from UNKNOWN (no key loaded).'),
}

# Legacy → operational, for defensive normalization of any pre-migration state string
# (old in-memory snapshots, persisted JSON, external callers). The engine no longer
# emits these, but normalization keeps every surface safe.
_LEGACY = {
    'NOT_LOADED': UNKNOWN, 'NOT_SIGNED': UNSIGNED, 'UNVERIFIED': UNKNOWN,
    'STRUCTURE_ERROR': CORRUPTED, 'TAMPERED': INVALID, 'KEY_MISMATCH': WRONG_KEY,
    'TRUNCATED': PARTIAL, 'ERROR': CORRUPTED, '': UNKNOWN,
}


def normalize_state(state: str) -> str:
    """Map any state string (operational or legacy) to a canonical operational state."""
    if state in _MODEL:
        return state
    return _LEGACY.get(state, UNKNOWN)


def info(state: str) -> StateInfo:
    return _MODEL[normalize_state(state)]


def label(state: str) -> str:
    return info(state).label


def color(state: str) -> str:
    return info(state).color


def tone(state: str) -> str:
    return info(state).tone


def badge_colors(state: str) -> tuple:
    """(foreground, background) hex pair for light/print badges."""
    i = info(state)
    return i.fg, i.bg


def _get(result, key, default=None):
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def verification_basis(result) -> list:
    """Build the 'Verification Basis' lines from a verify result (dict or VerifyResult).

    Describes *what was checked* — chunk count + chain status, closure (END record),
    and signature availability — in operational language. Safe on partial results.
    """
    state = normalize_state(_get(result, 'state', UNKNOWN))
    chunks = _get(result, 'chain_chunks', 0) or 0
    algo = (_get(result, 'algo_name', '') or '').strip()
    # chain_valid: keyless chain integrity for the chunks present; fall back to chain_ok
    cv = _get(result, 'chain_valid', None)
    if cv is None:
        cv = _get(result, 'chain_ok', False)
    closed = _get(result, 'closed', None)

    lines = []
    if chunks:
        algoname = (algo.split('+')[0].strip() if algo else 'hash-chain') or 'hash-chain'
        verb = 'validated' if cv else 'present — chain mismatch detected'
        lines.append(f'{chunks:,} {algoname} hash-chain chunks {verb}.')
    elif state in (UNSIGNED,):
        lines.append('No signature structures present.')
    elif state in (CORRUPTED,):
        lines.append('Verification records could not be parsed.')

    if closed is True:
        lines.append('END record present.')
    elif closed is False:
        lines.append('END record not present.')

    if state == VERIFIED:
        lines.append('Ed25519 signature valid.')
    elif state == PARTIAL:
        lines.append('Final Ed25519 signature unavailable (log not closed).')
    elif state == INVALID:
        lines.append('Signature / hash-chain validation failed.')
    elif state == WRONG_KEY:
        lines.append('Key fingerprint does not match this log.')
    elif state == UNKNOWN:
        lines.append('Signature not checked — no public key loaded.')

    return lines
