from pathlib import Path

from PySide6.QtCore import Property, QObject, QThread, QUrl, Signal, Slot

from nfe_monitor.application import empresas
from nfe_monitor.infrastructure import certificados, preferencias
from nfe_monitor.infrastructure.database import notas_repository as repo
from nfe_monitor.infrastructure.database.conexao import conectar
from nfe_monitor.infrastructure.sefaz.parametros import Config


def _fmt_cnpj(c: str | None) -> str:
    if not c or len(c) != 14:
        return c or "sem CNPJ"
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


class _Tarefa(QObject):
    concluiu = Signal(object)
    falhou = Signal(str)

    def __init__(self, funcao) -> None:
        super().__init__()
        self._funcao = funcao

    def run(self) -> None:
        try:
            resultado = self._funcao()
        except Exception as erro:  # noqa: BLE001 - repassa qualquer falha à tela
            self.falhou.emit(str(erro))
        else:
            self.concluiu.emit(resultado)


class ConfigViewModel(QObject):
    alterado = Signal()
    salvo = Signal()
    erro = Signal(str)
    cadastrado = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._certs: list[dict] = []
        self._empresas: list[dict] = []
        self._thumb = ""
        self._pasta = ""
        self._ocupado = False
        self._tarefas: dict[QThread, _Tarefa] = {}

    # ---------- Propriedades ----------
    @Property("QVariantList", notify=alterado)
    def certificados(self) -> list[dict]: return self._certs

    @Property("QVariantList", notify=alterado)
    def empresas(self) -> list[dict]: return self._empresas

    @Property(str, notify=alterado)
    def thumbprint(self) -> str: return self._thumb

    @Property(str, notify=alterado)
    def pasta(self) -> str: return self._pasta

    @Property(bool, notify=alterado)
    def ocupado(self) -> bool: return self._ocupado

    # ---------- Carga ----------
    @Slot()
    def carregar(self) -> None:
        prefs = preferencias.carregar()
        self._thumb, self._pasta = prefs.thumbprint.upper(), prefs.pasta_download
        try:
            lista = certificados.listar()
        except RuntimeError as e:
            self.erro.emit(str(e))
            lista = []
        self._certs = [self._cert_dict(c) for c in lista]
        self._carregar_empresas()
        self.alterado.emit()

    def _cert_dict(self, c: certificados.Certificado) -> dict:
        marcas = []
        if c.thumbprint == self._thumb:
            marcas.append("ATUAL")
        if c.vencido:
            marcas.append("VENCIDO")
        elif c.dias_restantes <= certificados.AVISO_DIAS:
            marcas.append("VENCE LOGO")
        if not c.tem_chave:
            marcas.append("SEM CHAVE")
        extra = f"  [{', '.join(marcas)}]" if marcas else ""
        return {
            "id": c.thumbprint,
            "nome": f"{c.titular} · {_fmt_cnpj(c.cnpj)}{extra}",
            "cnpj": _fmt_cnpj(c.cnpj),
            "validade": f"{c.validade:%d/%m/%Y}",
            "situacao": c.situacao,
            "alerta": c.vencido or c.dias_restantes <= certificados.AVISO_DIAS or not c.tem_chave,
        }

    def _carregar_empresas(self) -> None:
        try:
            con = conectar(Config().banco)
            try:
                lista = repo.listar_empresas(con, somente_ativas=False)
            finally:
                con.close()
        except Exception as e:  # noqa: BLE001 - mostra na tela em vez de derrubar
            self.erro.emit(f"Não foi possível ler as empresas: {e}")
            lista = []
        self._empresas = [
            {
                "cnpj": _fmt_cnpj(e.cnpj),
                "nome": e.razao_social or "(sem nome)",
                "uf": e.uf or "--",
                "completa": bool(e.completa),
                "ativo": bool(e.ativo),
            }
            for e in lista
        ]

    # ---------- Cadastro ----------
    @Slot(str, str)
    def cadastrar(self, thumbprint: str, uf: str) -> None:
        if self._ocupado:
            return
        if not thumbprint:
            self.erro.emit("Selecione um certificado.")
            return
        uf = uf.strip().upper() or None
        self._ocupado = True
        self.alterado.emit()

        thread = QThread(self)
        tarefa = _Tarefa(lambda: empresas.cadastrar_por_certificado(
            thumbprint, uf=uf, definir_padrao=False))
        tarefa.moveToThread(thread)
        thread.started.connect(tarefa.run)
        tarefa.concluiu.connect(self._cadastro_ok)
        tarefa.falhou.connect(self._cadastro_erro)
        tarefa.concluiu.connect(thread.quit)
        tarefa.falhou.connect(thread.quit)
        thread.finished.connect(tarefa.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._tarefas.pop(thread, None))
        self._tarefas[thread] = tarefa
        thread.start()

    def _cadastro_ok(self, res) -> None:
        e = res.empresa
        linhas = [f"✓ {'Cadastrada' if res.nova else 'Atualizada'}: "
                  f"{e.razao_social or '(sem nome)'} ({e.uf or 'sem UF'})"]
        linhas += [f"⚠ {a}" for a in res.avisos]
        self._ocupado = False
        self._carregar_empresas()
        self.alterado.emit()
        self.cadastrado.emit("\n".join(linhas))

    def _cadastro_erro(self, mensagem: str) -> None:
        self._ocupado = False
        self.alterado.emit()
        self.erro.emit(mensagem)

    # ---------- Preferências ----------
    @Slot(str, result=str)
    def caminhoDe(self, url: str) -> str:
        return str(Path(QUrl(url).toLocalFile()))

    @Slot(str, str, result=bool)
    def salvar(self, thumbprint: str, pasta: str) -> bool:
        if not thumbprint:
            self.erro.emit("Selecione um certificado.")
            return False
        prefs = preferencias.carregar()
        prefs.thumbprint, prefs.pasta_download = thumbprint, pasta
        preferencias.salvar(prefs)
        self._thumb, self._pasta = thumbprint.upper(), pasta
        self.alterado.emit()
        self.salvo.emit()
        return True
