import sys

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from nfe_monitor.infrastructure.paths import recurso
from nfe_monitor.ui.themes.theme_manager import ThemeManager
from nfe_monitor.ui.viewmodels.config_viewmodel import ConfigViewModel
from nfe_monitor.ui.viewmodels.main_viewmodel import MainViewModel


def main() -> int:
    QCoreApplication.setOrganizationName("NFeMonitor")
    QCoreApplication.setApplicationName("NF-e Monitor")
    QQuickStyle.setStyle("Basic")  # personalização total dos controles

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()

    tema = ThemeManager(app)
    view_model = MainViewModel()
    config = ConfigViewModel()
    config.salvo.connect(view_model.atualizarCertificado)

    ctx = engine.rootContext()
    ctx.setContextProperty("Theme", tema)
    ctx.setContextProperty("viewModel", view_model)
    ctx.setContextProperty("config", config)

    engine.load(QUrl.fromLocalFile(str(recurso("nfe_monitor/ui/qml/Main.qml"))))
    if not engine.rootObjects():
        return 1

    codigo = app.exec()
    del engine  # destrói o QML antes dos view models
    return codigo


if __name__ == "__main__":
    sys.exit(main())
