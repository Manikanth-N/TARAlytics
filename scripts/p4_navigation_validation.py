"""
P4 navigation validation — count module switches before/after the Investigation
Workspace for four investigations.

Each investigation is modeled as the ordered sequence of *surfaces* the investigator
must view (realistic: look at A, then B, then back to A to move the cursor, …). A
"navigation action" is a nav-rail module switch.

BEFORE (single-module stack): every time the needed surface lives in a different
module than the current one, that's a switch. The Context dock is always visible and
never costs a switch.

AFTER (workspace): open Workspace + pick a layout = 2 actions; thereafter a surface
that is in the active layout (or the bottom Timeline transport, or the Context dock)
costs 0; a surface outside the layout is a pop-out = 1 action (once).
"""

# surface -> module it lives in (BEFORE). 'dock'/'transport' are always-visible.
SURFACE_MODULE = {
    'signals': 'Signals', 'ekf': 'Signals', 'gps': 'Signals', 'attitude': 'Signals',
    'horizon': 'Situation', 'rc': 'Situation',
    'map': 'Map', 'events': 'Events', 'timeline': 'Timeline', 'replay': 'Replay',
    'verify': 'Verify', 'evidence': 'Evidence', 'debrief': 'Debrief',
    'context': 'dock', 'time': 'transport',
}

WORKSPACE_LAYOUTS = {
    'Pilot Analysis': {'signals', 'attitude', 'ekf', 'gps', 'horizon', 'rc'},
    'Accident Investigation': {'signals', 'attitude', 'ekf', 'gps', 'map', 'events'},
    'Certification': {'evidence', 'verify', 'timeline'},
}
ALWAYS_VISIBLE = {'context', 'timeline', 'time'}   # dock + bottom transport

# Realistic surface-view sequences per investigation (start at Debrief landing).
SCENARIOS = {
    'Pilot over-control': (
        ['debrief', 'signals', 'horizon', 'rc', 'signals', 'horizon', 'rc',
         'signals', 'horizon', 'rc', 'signals'],
        'Pilot Analysis'),
    'Oscillation (4 Hz roll)': (
        ['debrief', 'signals', 'horizon', 'timeline', 'signals', 'horizon',
         'signals', 'timeline', 'horizon', 'signals'],
        'Pilot Analysis'),
    'GPS anomaly': (
        ['debrief', 'events', 'map', 'gps', 'map', 'ekf', 'events', 'map', 'gps'],
        'Accident Investigation'),
    'Crash reconstruction': (
        ['debrief', 'timeline', 'events', 'map', 'attitude', 'horizon', 'replay',
         'map', 'attitude', 'events', 'horizon', 'replay', 'map', 'attitude'],
        'Accident Investigation'),
}


def count_before(seq):
    switches, cur = 0, 'Debrief'
    for s in seq:
        m = SURFACE_MODULE[s]
        if m in ('dock', 'transport'):
            continue
        if m != cur:
            switches += 1
            cur = m
    return switches


def count_after(seq, layout):
    covered = WORKSPACE_LAYOUTS[layout] | ALWAYS_VISIBLE
    actions = 2                      # open Workspace + pick layout
    popped = set()
    for s in seq:
        if s == 'debrief':
            continue                 # the verdict that sent you here; not a workspace nav
        if s in covered or s in popped:
            continue
        actions += 1                 # pop-out (or one-time layout change) for this surface
        popped.add(s)
    return actions


def main():
    print(f'{"investigation":<26}{"before":>8}{"after":>7}{"reduction":>11}  layout')
    print('-' * 72)
    tb = ta = 0
    for name, (seq, layout) in SCENARIOS.items():
        b = count_before(seq); a = count_after(seq, layout)
        red = (b - a) / b * 100 if b else 0
        tb += b; ta += a
        print(f'{name:<26}{b:>8}{a:>7}{red:>10.0f}%  {layout}')
    print('-' * 72)
    print(f'{"TOTAL":<26}{tb:>8}{ta:>7}{(tb-ta)/tb*100:>10.0f}%')
    print(f'\nTarget: >=50% reduction.  Achieved overall: {(tb-ta)/tb*100:.0f}%  '
          f'({"PASS" if (tb-ta)/tb >= 0.5 else "FAIL"})')


if __name__ == '__main__':
    main()
