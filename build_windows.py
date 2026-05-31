"""
Build script for TARAlytics.

Usage
-----
On Windows (native):
    python build_windows.py               # PyInstaller only
    python build_windows.py --installer   # PyInstaller + Inno Setup installer

On Linux (via Docker/Wine cross-compile):
    python build_windows.py --docker      # PyInstaller inside Wine
    (Inno Setup is Windows-only; run --installer on a real Windows machine or in CI)

Output
------
    dist/TARAlytics/           PyInstaller bundle (the app itself)
    dist/installer/            Inno Setup .exe installer  (if --installer)
"""
import subprocess
import sys
import os
import shutil
import argparse

BASE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(BASE, 'TARAlytics.spec')
DIST_APP = os.path.join(BASE, 'dist', 'TARAlytics')
DIST_INSTALLER = os.path.join(BASE, 'dist', 'installer')
ISS_SCRIPT = os.path.join(BASE, 'installer', 'TARAlytics.iss')

# ── Inno Setup candidate paths ────────────────────────────────────────────────
ISCC_CANDIDATES = [
    r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    r'C:\Program Files\Inno Setup 6\ISCC.exe',
    r'C:\Program Files (x86)\Inno Setup 5\ISCC.exe',
]


def _find_iscc() -> str:
    """Return path to ISCC.exe or raise if not found."""
    for path in ISCC_CANDIDATES:
        if os.path.isfile(path):
            return path
    if shutil.which('ISCC') or shutil.which('ISCC.exe'):
        return 'ISCC.exe'
    raise FileNotFoundError(
        'Inno Setup Compiler (ISCC.exe) not found.\n'
        'Download from https://jrsoftware.org/isinfo.php and install it, '
        'then re-run with --installer.'
    )


def _read_version() -> str:
    """Read version from VERSION file, falling back to 1.0.0."""
    vfile = os.path.join(BASE, 'VERSION')
    if os.path.isfile(vfile):
        return open(vfile).read().strip()
    return '1.0.0'


# ── Build steps ───────────────────────────────────────────────────────────────

def build_pyinstaller():
    """Run PyInstaller using the current Python (Windows or Linux)."""
    cmd = [sys.executable, '-m', 'PyInstaller', SPEC, '--noconfirm', '--clean']
    print('=' * 60)
    print('Step 1/2 — PyInstaller')
    print('=' * 60)
    print(' '.join(cmd))
    subprocess.run(cmd, check=True, cwd=BASE)

    exe = os.path.join(DIST_APP, 'TARAlytics.exe' if sys.platform == 'win32' else 'TARAlytics')
    if os.path.exists(exe):
        print(f'\nApp bundle ready: {exe}')
    else:
        print(f'\nApp bundle ready: {DIST_APP}/')


def build_installer(version=None):
    """Compile the Inno Setup installer from the PyInstaller output."""
    if sys.platform != 'win32':
        print('WARNING: Inno Setup only runs on Windows — skipping installer build.')
        return

    if not os.path.isdir(DIST_APP):
        raise RuntimeError(
            f'{DIST_APP} does not exist. Run PyInstaller first (omit --installer-only).'
        )

    iscc = _find_iscc()
    ver = version or _read_version()
    os.makedirs(DIST_INSTALLER, exist_ok=True)

    cmd = [iscc, f'/DAppVersion={ver}', ISS_SCRIPT]
    print()
    print('=' * 60)
    print('Step 2/2 — Inno Setup Installer')
    print('=' * 60)
    print(f'Version : {ver}')
    print(' '.join(cmd))
    subprocess.run(cmd, check=True, cwd=BASE)

    # Report the output file
    for fname in sorted(os.listdir(DIST_INSTALLER)):
        if fname.endswith('.exe'):
            print(f'\nInstaller ready: {os.path.join(DIST_INSTALLER, fname)}')


def build_docker():
    """Build Windows .exe via Docker + Wine (run on Linux)."""
    image = 'taralytics-builder'
    out_dir = os.path.join(BASE, 'dist')
    os.makedirs(out_dir, exist_ok=True)

    print('Step 1/2 — Building Docker image (first run downloads Wine, ~5 min)...')
    subprocess.run(
        ['docker', 'build', '-f', 'Dockerfile.build', '-t', image, '.'],
        check=True, cwd=BASE,
    )

    print('Step 2/2 — Running PyInstaller inside Wine...')
    subprocess.run(
        ['docker', 'run', '--rm', '-v', f'{out_dir}:/out', image],
        check=True, cwd=BASE,
    )

    exe = os.path.join(out_dir, 'TARAlytics', 'TARAlytics.exe')
    if os.path.exists(exe):
        print(f'\nBuild successful: {exe}')
    else:
        print(f'\nBuild complete. Check {out_dir}/TARAlytics/')


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Build TARAlytics — PyInstaller bundle and optional Windows installer.'
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--docker', action='store_true',
        help='Cross-compile Windows .exe via Docker+Wine (Linux hosts only).'
    )
    group.add_argument(
        '--installer-only', action='store_true',
        help='Skip PyInstaller; only compile the Inno Setup installer from an existing dist/.'
    )
    parser.add_argument(
        '--installer', action='store_true',
        help='Also build the Inno Setup installer after PyInstaller finishes (Windows only).'
    )
    parser.add_argument(
        '--version', default=None,
        help='Version string to embed in the installer (e.g. 1.2.3). '
             'Defaults to content of VERSION file.'
    )
    args = parser.parse_args()

    if args.docker:
        build_docker()
    elif args.installer_only:
        build_installer(version=args.version)
    else:
        build_pyinstaller()
        if args.installer:
            build_installer(version=args.version)


if __name__ == '__main__':
    main()
