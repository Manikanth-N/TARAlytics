import subprocess
import sys
import os


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    icon = os.path.join(base, 'assets', 'icon.ico')

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--windowed',
        '--name=ArduPilot Log Analyzer',
        f'--icon={icon}',
        '--hidden-import=cryptography',
        '--hidden-import=cryptography.hazmat.primitives.asymmetric.ed25519',
        '--hidden-import=cryptography.hazmat.backends.openssl',
        '--hidden-import=PyQt6.QtOpenGL',
        '--hidden-import=PyQt6.QtOpenGLWidgets',
        '--collect-all=pyqtgraph',
        '--collect-all=OpenGL',
        '--collect-all=PyQt6',
        '--noconfirm',
        os.path.join(base, 'main.py'),
    ]
    print('Running PyInstaller...')
    subprocess.run(cmd, check=True, cwd=base)
    print('EXE built: dist/ArduPilot Log Analyzer.exe')


if __name__ == '__main__':
    main()
