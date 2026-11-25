import shutil
from pathlib import Path

from PySide6.QtCore import Property, QObject, QThread, QTimer, QUrl, Signal, Slot

from nfe_monitor.application import limite
from nfe_monitor.application.baixar_xml import baixar_e_copiar, caminho_livre
from nfe_monitor.application.listar_notas import ITENS_POR_PAGINA, consultar_notas
from nfe_monitor.application.sincronizar import sincronizar_todas
from nfe_monitor.infrastructure import certificados, preferencias
from nfe_monitor.infrastructure.database import notas_repository as repo
from nfe_monitor.infrastructure.database.conexao import conectar
from nfe_monitor.infrastructure.paths import CNPJ
from nfe_monitor.infrastructure.sefaz.parametros import Config
from nfe_monitor.ui.formatters import formatar_brl
from nfe_monitor.ui.models.notas_model import NotasModel


def _fmt_cnpj(c: str) -> str:
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else c


class Tarefa(QObject):
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


class MainViewModel(QObject):
    alterado = Signal()
    relogioChanged = Signal()
    empresasChanged = Signal()
    solicitarPasta = Signal(int)          # QML abre o FolderDialog
    solicitarCiencia = Signal(int, str)   # QML confirma a manifestação
    notificacao = Signal(str)
    erro = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = NotasModel(self)
        self._fornecedor, self._inicio, self._fim = "", None, None
        self._pagina, self._total_paginas, self._total = 0, 1, 0
        self._valor, self._baixados = "R$ 0,00", 0
        self._ocupado, self._status = False, "Pronto"
        self._cert_texto, self._cert_alerta = "Certificado não configurado", True
        self._proxima, self._ultima, self._liberado = "", "", False
        self._empresas: list[repo.Empresa] = []
        self._empresa_filtro = preferencias.carregar().empresa_filtro
        self._tarefas: dict[QThread, Tarefa] = {}

        self._relogio = QTimer(self)
        self._relogio.timeout.connect(self._tick)
        self._relogio.start(1000)

        self._carregar_empresas()
        self.recarregar()
        self.atualizarCertificado()
        self._tick()

    # ---------- Propriedades ----------
    @Property(QObject, constant=True)
    def notas(self): return self._model

    @Property(str, notify=alterado)
    def cnpj(self) -> str:
        if self._empresa_filtro:
            return _fmt_cnpj(self._empresa_filtro)
        if not self._empresas:
            return _fmt_cnpj(CNPJ)
        if len(self._empresas) == 1:
            return _fmt_cnpj(self._empresas[0].cnpj)
        return f"Todas ({len(self._empresas)})"

    @Property("QVariantList", notify=empresasChanged)
    def empresasOpcoes(self) -> list:
        opcoes = [{"id": "", "nome": f"Todas as empresas  ({len(self._empresas)})"}]
        for e in self._empresas:
            nome = e.razao_social or "Sem razão social"
            opcoes.append({"id": e.cnpj, "nome": f"{nome}  ·  {_fmt_cnpj(e.cnpj)}"})
        return opcoes

    @Property(int, notify=empresasChanged)
    def empresaIndice(self) -> int:
        for i, e in enumerate(self._empresas, start=1):
            if e.cnpj == self._empresa_filtro:
                return i
        return 0

    @Property(bool, notify=empresasChanged)
    def multiEmpresa(self) -> bool: return len(self._empresas) > 1

    @Property(int, notify=alterado)
    def pagina(self) -> int: return self._pagina + 1

    @Property(int, notify=alterado)
    def totalPaginas(self) -> int: return self._total_paginas

    @Property(int, notify=alterado)
    def totalNotas(self) -> int: return self._total

    @Property(str, notify=alterado)
    def valorTotal(self) -> str: return self._valor

    @Property(int, notify=alterado)
    def baixados(self) -> int: return self._baixados

    @Property(bool, notify=alterado)
    def ocupado(self) -> bool: return self._ocupado

    @Property(str, notify=alterado)
    def status(self) -> str: return self._status

    @Property(str, notify=alterado)
    def certTexto(self) -> str: return self._cert_texto

    @Property(bool, notify=alterado)
    def certAlerta(self) -> bool: return self._cert_alerta

    @Property(bool, notify=alterado)
    def filtrado(self) -> bool: return bool(self._fornecedor or self._inicio or self._fim)

    @Property(str, notify=relogioChanged)
    def proxima(self) -> str: return self._proxima

    @Property(str, notify=relogioChanged)
    def ultima(self) -> str: return self._ultima

    @Property(bool, notify=relogioChanged)
    def syncLiberado(self) -> bool: return self._liberado

    # ---------- Internos ----------
    def _set_status(self, texto: str, ocupado: bool | None = None) -> None:
        self._status = texto
        if ocupado is not None:
            self._ocupado = ocupado
        self.alterado.emit()
        self._tick()

    def _tick(self) -> None:
        restante = int(limite.segundos_restantes())
        ultima = limite.ultima_sincronizacao()
        self._ultima = f"{ultima:%d/%m/%Y às %H:%M}" if ultima else "Nunca sincronizado"
        if restante > 0:
            h, r = divmod(restante, 3600)
            m, s = divmod(r, 60)
            self._proxima = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            self._proxima = ""
        self._liberado = restante == 0 and not self._ocupado
        self.relogioChanged.emit()

    def _carregar_empresas(self) -> None:
        try:
            con = conectar(Config().banco)
            try:
                self._empresas = repo.listar_empresas(con)
            finally:
                con.close()
        except Exception:  # noqa: BLE001 - sem banco, mantém o CNPJ do paths
            self._empresas = []

        # Empresa salva foi desativada/removida, ou só restou uma: volta para "todas"
        cnpjs = {e.cnpj for e in self._empresas}
        if self._empresa_filtro and (self._empresa_filtro not in cnpjs or len(cnpjs) <= 1):
            self._empresa_filtro = ""
            self._salvar_filtro()
        self.empresasChanged.emit()

    def _salvar_filtro(self) -> None:
        try:
            p = preferencias.carregar()
            p.empresa_filtro = self._empresa_filtro
            preferencias.salvar(p)
        except OSError:
            pass  # não salvar a preferência não impede o uso

    def _executar(self, funcao, ok, falha) -> None:
        thread = QThread(self)
        tarefa = Tarefa(funcao)
        tarefa.moveToThread(thread)
        thread.started.connect(tarefa.run)
        tarefa.concluiu.connect(ok)
        tarefa.falhou.connect(falha)
        tarefa.concluiu.connect(thread.quit)
        tarefa.falhou.connect(thread.quit)
        thread.finished.connect(tarefa.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._tarefas.pop(thread, None))
        self._tarefas[thread] = tarefa
        thread.start()

    def _validar_cert(self) -> bool:
        try:
            certificados.validar_para_uso()
            return True
        except RuntimeError as e:
            self.erro.emit("Certificado", str(e))
            return False

    @staticmethod
    def _pasta_salva() -> Path | None:
        salva = preferencias.carregar().pasta_download
        return Path(salva) if salva and Path(salva).is_dir() else None

    # ---------- Consulta / filtros ----------
    def _consultar(self):
        return consultar_notas(self._fornecedor, self._inicio, self._fim,
                               self._pagina, self._empresa_filtro or None)

    @Slot()
    def recarregar(self) -> None:
        notas, resumo = self._consultar()
        self._total = int(resumo["quantidade"] or 0)
        self._total_paginas = max(1, -(-self._total // ITENS_POR_PAGINA))
        if self._pagina >= self._total_paginas:
            self._pagina = self._total_paginas - 1
            notas, resumo = self._consultar()
        self._valor = formatar_brl(resumo["valor_total"] or 0)
        self._baixados = int(resumo["baixados"] or 0)
        self._model.carregar(notas)
        self.alterado.emit()

    @Slot(str)
    def selecionarEmpresa(self, cnpj: str) -> None:
        cnpj = "".join(c for c in (cnpj or "") if c.isdigit())
        if cnpj == self._empresa_filtro or self._ocupado:
            self.empresasChanged.emit()  # devolve o seletor ao valor atual
            return
        self._empresa_filtro = cnpj
        self._salvar_filtro()
        self._pagina = 0
        self.empresasChanged.emit()
        self.recarregar()

    @Slot(str, str, str)
    def aplicarFiltros(self, fornecedor: str, inicio_iso: str, fim_iso: str) -> None:
        self._fornecedor = fornecedor.strip()
        self._inicio = inicio_iso or None
        self._fim = fim_iso or None
        self._pagina = 0
        self.recarregar()

    @Slot()
    def limparFiltros(self) -> None:
        self.aplicarFiltros("", "", "")

    @Slot(int)
    def irPagina(self, delta: int) -> None:
        nova = self._pagina + delta
        if 0 <= nova < self._total_paginas and not self._ocupado:
            self._pagina = nova
            self.recarregar()

    # ---------- Certificado ----------
    @Slot()
    def atualizarCertificado(self) -> None:
        try:
            cert = certificados.selecionado()
        except (RuntimeError, OSError, ValueError, KeyError):
            cert = None
        if cert is None:
            self._cert_texto, self._cert_alerta = "Certificado não configurado", True
        else:
            self._cert_texto = f"{cert.titular.split(':')[0]} · {cert.situacao} até {cert.validade:%d/%m/%Y}"
            self._cert_alerta = cert.dias_restantes <= certificados.AVISO_DIAS
        self._carregar_empresas()  # chamado ao salvar as Configurações
        self.recarregar()
        self.alterado.emit()

    # ---------- Sincronização ----------
    @Slot()
    def sincronizar(self) -> None:
        if self._ocupado or limite.segundos_restantes() > 0 or not self._validar_cert():
            return
        limite.registrar_disparo()
        self._set_status("Sincronizando com a SEFAZ…", True)
        self._executar(lambda: sincronizar_todas(Config()), self._sync_ok, self._sync_erro)

    def _sync_ok(self, resultados) -> None:
        if not resultados:
            self._set_status("Nenhuma empresa cadastrada", False)
            self.erro.emit("Sincronização", "Cadastre uma empresa em ⚙ Configurações.")
            return

        novas = sum(r.novas for r in resultados)
        esperas = [r for r in resultados if r.status == "espera"]
        erros = [r for r in resultados if r.status == "erro"]

        partes = [f"{novas} nova(s)"]
        if esperas:
            partes.append(f"{len(esperas)} em espera")
        if erros:
            partes.append(f"{len(erros)} com erro")
        resumo = " · ".join(partes)

        self._carregar_empresas()
        self._set_status(f"Concluído: {resumo}", False)
        self.recarregar()
        self.notificacao.emit(f"✓ {resumo}")

        if erros:
            self.erro.emit("Sincronização",
                           "\n".join(f"{_fmt_cnpj(r.cnpj)}: {r.detalhe}" for r in erros))

    def _sync_erro(self, mensagem: str) -> None:
        self._set_status("Falha na sincronização", False)
        self.recarregar()
        self.erro.emit("Sincronização", mensagem)

    # ---------- XML ----------
    @Slot(int)
    def acaoXml(self, linha: int) -> None:
        if self._ocupado or self._model.nota(linha) is None:
            return
        pasta = self._pasta_salva()
        if pasta is None:
            self.solicitarPasta.emit(linha)
        else:
            self._prosseguir(linha, pasta)

    @Slot(int, str)
    def continuarComPasta(self, linha: int, url: str) -> None:
        self._prosseguir(linha, Path(QUrl(url).toLocalFile()))

    def _prosseguir(self, linha: int, pasta: Path) -> None:
        nota = self._model.nota(linha)
        if nota is None:
            return
        if nota["xml_baixado"]:
            origem = Path(nota["caminho_xml"] or "")
            if not origem.is_file():
                self.erro.emit("Salvar XML", f"O arquivo não foi encontrado em:\n{origem}")
                return
            try:
                destino = caminho_livre(pasta, f"{nota['chave']}.xml")
                shutil.copy2(origem, destino)
            except OSError as e:
                self.erro.emit("Salvar XML", f"Não foi possível salvar o arquivo:\n{e}")
                return
            self._set_status(f"XML salvo em {destino}")
            self.notificacao.emit("✓ XML salvo")
            return

        if not self._validar_cert():
            return
        if nota["manifestacao"] != "ciencia":
            self.solicitarCiencia.emit(linha, str(pasta))
            return
        self._baixar(nota["chave"], pasta)

    @Slot(int, str)
    def confirmarCiencia(self, linha: int, pasta: str) -> None:
        nota = self._model.nota(linha)
        if nota is not None:
            self._baixar(nota["chave"], Path(pasta))

    def _baixar(self, chave: str, pasta: Path) -> None:
        self._set_status("Baixando XML…", True)
        self._executar(lambda: baixar_e_copiar(chave, pasta), self._download_ok, self._download_erro)

    def _download_ok(self, destino: Path) -> None:
        self._set_status(f"XML salvo em {destino}", False)
        self.recarregar()
        self.notificacao.emit("✓ XML baixado e salvo")

    def _download_erro(self, mensagem: str) -> None:
        self._set_status("Falha ao baixar o XML", False)
        self.recarregar()
        self.erro.emit("Baixar XML", mensagem)

    # ---------- Janela ----------
    @Slot(result=bool)
    def podeFechar(self) -> bool:
        return not self._ocupado
