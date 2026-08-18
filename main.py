"""FlowRank - ponto de entrada."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.config import load_config, resolve_path
from app.gui.main_window import MainWindow
from app.utils.logger import setup_logging


def main() -> int:
    config = load_config()
    log_cfg = config["logging"]
    logger = setup_logging(
        path=resolve_path(log_cfg["path"]),
        level=log_cfg["level"],
        max_bytes=log_cfg["max_bytes"],
        backup_count=log_cfg["backup_count"],
    )
    logger.info("FlowRank iniciando")

    app = QApplication(sys.argv)
    app.setApplicationName("FlowRank")
    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
