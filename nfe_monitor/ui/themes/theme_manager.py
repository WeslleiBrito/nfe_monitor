from typing import Any

from PySide6.QtCore import Property, QObject, QSettings, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication

from nfe_monitor.ui.themes.catalog import SYSTEM_ID, THEMES, resolve_theme

_CHAVE = "aparencia/tema"


class ThemeManager(QObject):
    themeChanged = Signal()

    def __init__(self, app: QGuiApplication, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        self._hints = app.styleHints()
        valor = str(self._settings.value(_CHAVE, SYSTEM_ID))
        self._selecionado = valor if valor in THEMES else SYSTEM_ID
        self._hints.colorSchemeChanged.connect(self._ao_mudar_sistema)
        self._dados: dict[str, Any] = {}
        self._aplicar()

    def _sistema_escuro(self) -> bool:
        return self._hints.colorScheme() == Qt.ColorScheme.Dark

    def _aplicar(self) -> None:
        self._dados = resolve_theme(self._selecionado, self._sistema_escuro()).to_qml()
        self.themeChanged.emit()

    def _ao_mudar_sistema(self, *_: object) -> None:
        if self._selecionado == SYSTEM_ID:
            self._aplicar()

    @Property("QVariantMap", notify=themeChanged)
    def t(self) -> dict[str, Any]:
        return self._dados

    @Property(str, notify=themeChanged)
    def selecionado(self) -> str:
        return self._selecionado

    @Property("QVariantList", notify=themeChanged)
    def opcoes(self) -> list[dict[str, str]]:
        modo = "escuro" if self._sistema_escuro() else "claro"
        return [{"id": SYSTEM_ID, "nome": f"Seguir o sistema ({modo})"}] + [
            {"id": t.id, "nome": t.nome} for t in THEMES.values()
        ]

    @Slot(str)
    def selecionar(self, theme_id: str) -> None:
        if theme_id != SYSTEM_ID and theme_id not in THEMES:
            return
        self._selecionado = theme_id
        self._settings.setValue(_CHAVE, theme_id)
        self._aplicar()

    @Slot()
    def alternar(self) -> None:
        """Atalho da barra lateral: percorre os temas em ciclo."""
        ids = [SYSTEM_ID, *THEMES.keys()]
        self.selecionar(ids[(ids.index(self._selecionado) + 1) % len(ids)])
