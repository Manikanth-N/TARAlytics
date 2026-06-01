import sys
import os
import logging
from pathlib import Path

os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from ui.main_window import MainWindow


def _setup_logging():
    log_dir = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'TARAlytics' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / 'taralytics.log'
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
        ],
    )
    return log_dir


def main():
    log_dir = _setup_logging()
    logger = logging.getLogger('taralytics')
    logger.info('TARAlytics starting — logs at %s', log_dir)

    app = QApplication(sys.argv)
    app.setApplicationName('TARAlytics Log Analyzer')
    app.setOrganizationName('TARA UAV')

    icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'icon.ico')
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    app.setStyle('Fusion')

    from PyQt6.QtCore import QSettings
    from ui.main_window import _dark_palette, _light_palette
    is_dark = QSettings('TARAlyticsAnalyzer', 'MainWindow').value('is_dark', True, type=bool)
    app.setPalette(_dark_palette() if is_dark else _light_palette())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
