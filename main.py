import sys
import os

os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('ArduPilot Log Analyzer')
    app.setOrganizationName('ArduPilotAnalyzer')

    icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'icon.ico')
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    app.setStyle('Fusion')

    from PyQt6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor('#1e1e2e'))
    palette.setColor(QPalette.ColorRole.WindowText, QColor('#e0e0e0'))
    palette.setColor(QPalette.ColorRole.Base, QColor('#13131f'))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor('#1a1a2e'))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor('#2a2a3e'))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor('#e0e0e0'))
    palette.setColor(QPalette.ColorRole.Text, QColor('#e0e0e0'))
    palette.setColor(QPalette.ColorRole.Button, QColor('#2a2a3e'))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor('#e0e0e0'))
    palette.setColor(QPalette.ColorRole.BrightText, QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.Link, QColor('#4a90d9'))
    palette.setColor(QPalette.ColorRole.Highlight, QColor('#0d6efd'))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor('#ffffff'))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
