"""Conexão com a instância do Excel já aberta (COM / pywin32)."""

from __future__ import annotations

from typing import Any

from app.utils.logger import get_logger

log = get_logger("excel.connector")

try:  # pywin32 só existe no Windows; os testes rodam sem ele
    import pythoncom
    import win32com.client
except ImportError:  # pragma: no cover
    pythoncom = None
    win32com = None


class ExcelUnavailable(RuntimeError):
    pass


def com_initialize() -> None:
    if pythoncom is not None:
        pythoncom.CoInitialize()


def com_uninitialize() -> None:
    if pythoncom is not None:
        try:
            pythoncom.CoUninitialize()
        except Exception:  # pragma: no cover - encerramento best effort
            pass


class ExcelConnector:
    """Anexa-se a um Excel já em execução, sem abrir/salvar arquivos."""

    def __init__(self) -> None:
        self._app: Any = None

    @property
    def app(self) -> Any:
        return self._app

    @property
    def connected(self) -> bool:
        return self._app is not None

    def connect(self) -> Any:
        if win32com is None:
            raise ExcelUnavailable("pywin32 não disponível neste ambiente")
        try:
            app = win32com.client.GetActiveObject("Excel.Application")
        except Exception as exc:  # noqa: BLE001
            self._app = None
            raise ExcelUnavailable(f"Excel não encontrado em execução: {exc}") from exc
        self._app = app
        log.info("Excel conectado (%d workbook(s) aberto(s))", self.workbook_count())
        return app

    def ensure(self) -> Any:
        if self._app is None or not self.is_alive():
            return self.connect()
        return self._app

    def is_alive(self) -> bool:
        if self._app is None:
            return False
        try:
            _ = self._app.Workbooks.Count
            return True
        except Exception:  # noqa: BLE001
            return False

    def workbook_count(self) -> int:
        try:
            return int(self._app.Workbooks.Count)
        except Exception:  # noqa: BLE001
            return 0

    def workbooks(self) -> list:
        try:
            return [self._app.Workbooks(i + 1) for i in range(self.workbook_count())]
        except Exception as exc:  # noqa: BLE001
            raise ExcelUnavailable(f"Falha ao listar workbooks: {exc}") from exc

    def disconnect(self) -> None:
        self._app = None
