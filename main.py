import ctypes
import sys

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from nfe_monitor.infrastructure.paths import recurso
from nfe_monitor.ui.themes.theme_manager import ThemeManager
from nfe_monitor.ui.viewmodels.config_viewmodel import ConfigViewModel
from nfe_monitor.ui.viewmodels.main_viewmodel import MainViewModel

APP_ID = "nfemonitor.desktop.1"  # identifica o app na barra de tarefas do Windows
ICONE = "nfe_monitor/ui/assets/icon.png"


def _registrar_app_windows() -> None:
    """Sem isso, o Windows agrupa com o python.exe e mostra o ícone do Python."""
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except (AttributeError, OSError):
            pass


def _aplicar_icone(app: QGuiApplication) -> None:
    caminho = recurso(ICONE)
    if caminho.is_file():
        app.setWindowIcon(QIcon(str(caminho)))  # barra de título + barra de tarefas
    else:
        print("Nada encontrado")


def main() -> int:
    _registrar_app_windows()  # precisa vir antes de criar a aplicação/janela
    QCoreApplication.setOrganizationName("NFeMonitor")
    QCoreApplication.setApplicationName("NF-e Monitor")
    QQuickStyle.setStyle("Basic")  # personalização total dos controles

    app = QGuiApplication(sys.argv)
    _aplicar_icone(app)
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
