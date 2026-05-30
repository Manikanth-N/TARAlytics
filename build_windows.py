"""
Build script for TARAlytics.

On Windows:
    python build_windows.py

On Linux (Docker/Wine):
    python build_windows.py --docker

Output:  dist/TARAlytics/TARAlytics.exe  (Windows)
         dist/TARAlytics/TARAlytics      (Linux test build)
"""
import subprocess
import sys
import os
import argparse


BASE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(BASE, 'TARAlytics.spec')
DIST = os.path.join(BASE, 'dist', 'TARAlytics')


def build_native():
    """Run PyInstaller using the current Python (Windows or Linux)."""
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        SPEC,
        '--noconfirm',
        '--clean',
    ]
    print('Running PyInstaller...')
    print(' '.join(cmd))
    subprocess.run(cmd, check=True, cwd=BASE)

    exe = os.path.join(DIST, 'TARAlytics.exe' if sys.platform == 'win32' else 'TARAlytics')
    if os.path.exists(exe):
        print(f'\nBuild successful: {exe}')
    else:
        # Folder still created — list contents
        print(f'\nBuild complete. Output folder: {DIST}')
        for f in os.listdir(DIST):
            print(f'  {f}')


def build_docker():
    """Build Windows .exe via Docker + Wine (run on Linux)."""
    image = 'taralytics-builder'
    out_dir = os.path.join(BASE, 'dist')
    os.makedirs(out_dir, exist_ok=True)

    print('Step 1/2 — Building Docker image (first run takes ~5 min to download Wine)...')
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


def main():
    parser = argparse.ArgumentParser(description='Build TARAlytics executable')
    parser.add_argument('--docker', action='store_true',
                        help='Build Windows .exe via Docker+Wine (Linux hosts)')
    args = parser.parse_args()

    if args.docker:
        build_docker()
    else:
        build_native()


if __name__ == '__main__':
    main()
