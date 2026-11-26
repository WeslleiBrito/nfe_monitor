import logging
import shutil
from pathlib import Path

from PySide6.QtCore import Property, QObject, QThread, QTimer, QUrl, Signal, Slot

from nfe_monitor.application import limite
from nfe_monitor.application.baixar_xml import (
    ChaveInvalida, analisar_chave, baixar_e_copiar, baixar_por_chave, caminho_livre,
    extrair_chave, situacao_chave,
)
from nfe_monitor.application.listar_notas import ITENS_POR_PAGINA, consultar_notas
from nfe_monitor.application.sincronizar import EsperaSefaz, Resultado
from nfe_monitor.application.sincronizar import sincronizar as sincronizar_empresa
from nfe_monitor.infrastructure import certificados, preferencias
from nfe_monitor.infrastructure.database import notas_repository as repo
from nfe_monitor.infrastructure.database.conexao import conectar
from nfe_monitor.infrastructure.sefaz.parametros import Config
from nfe_monitor.ui.formatters import formatar_brl
from nfe_monitor.ui.models.notas_model import NotasModel

log = logging.getLogger("nfe_monitor")

SEM_EMPRESA = "não cadastrado"


def _fmt_cnpj(c: str) -> str:
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else c


def _problema_cert(thumb: str, indice: dict) -> str | None:
    """Motivo pelo qual o certificado não pode ser usado, ou None se estiver ok."""
    if not thumb:
        return "nenhum certificado definido (nem o padrão)"
    cert = indice.get(thumb)
    if cert is None:
        return "certificado não está instalado no Windows"
    if cert.vencido:
        return f"certificado venceu em {cert.validade:%d/%m/%Y}"
    return None


def _sincronizar_lista(cnpjs: list[str], bloqueadas: list[Resultado]) -> list[Resultado]:
    """Roda na thread: sincroniza só as empresas com certificado válido."""
    cfg = Config()
    resultados = []
    for cnpj in cnpjs:
        res = Resultado(cnpj)
        try:
            res.novas = sincronizar_empresa(cnpj, cfg)
        except EsperaSefaz as e:
            res.status, res.detalhe = "espera", str(e)
        except Exception as e:  # noqa: BLE001 - uma falha não interrompe as demais
            res.status, res.detalhe = "erro", str(e)
            log.exception("Falha ao sincronizar %s", cnpj)
        resultados.append(res)
    return resultados + bloqueadas


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
    chaveChanged = Signal()
    solicitarPasta = Signal(int)                 # QML abre o FolderDialog
    solicitarCiencia = Signal(int, str)          # QML confirma a manifestação
    solicitarPastaChave = Signal(str)            # idem, para download por chave
    solicitarCienciaChave = Signal(str, str)
    chaveConcluida = Signal()                    # QML limpa o campo da chave
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
        self._chave_info = None
        self._chave_msg = ""
        self._cnpj_da_chave: dict[str, str] = {}

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
            return SEM_EMPRESA
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

    @Property(str, notify=chaveChanged)
    def chavePrevia(self) -> str: return self._chave_msg

    @Property(bool, notify=chaveChanged)
    def chaveValida(self) -> bool: return self._chave_info is not None

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
        except Exception:  # noqa: BLE001 - sem banco, a tela mostra "não cadastrado"
            self._empresas = []

        # Empresa salva foi desativada/removida, ou só restou uma: volta para "todas"
        cnpjs = {e.cnpj for e in self._empresas}
        if self._empresa_filtro and (self._empresa_filtro not in cnpjs or len(cnpjs) <= 1):
            self._empresa_filtro = ""
            self._salvar_filtro()
        self.empresasChanged.emit()
        self.alterado.emit()

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

    @staticmethod
    def _pasta_salva() -> Path | None:
        salva = preferencias.carregar().pasta_download
        return Path(salva) if salva and Path(salva).is_dir() else None

    def _copiar_local(self, origem: Path, pasta: Path, chave: str) -> bool:
        if not origem.is_file():
            self.erro.emit("Salvar XML", f"O arquivo não foi encontrado em:\n{origem}")
            return False
        try:
            destino = caminho_livre(pasta, f"{chave}.xml")
            shutil.copy2(origem, destino)
        except OSError as e:
            self.erro.emit("Salvar XML", f"Não foi possível salvar o arquivo:\n{e}")
            return False
        self._set_status(f"XML salvo em {destino}")
        self.notificacao.emit("✓ XML salvo")
        return True

    # ---------- Certificados por empresa ----------
    @staticmethod
    def _padrao() -> str:
        return preferencias.carregar().thumbprint.strip().upper()

    def _indice_certs(self) -> dict | None:
        """Lê os certificados do Windows uma vez. None = falha já mostrada ao usuário."""
        try:
            return {c.thumbprint: c for c in certificados.listar()}
        except (certificados.ErroCertificados, OSError) as e:
            self.erro.emit("Certificado", f"Não foi possível ler os certificados:\n{e}")
            return None

    def _thumb_da_empresa(self, e: repo.Empresa | None) -> str:
        thumb = (e.thumbprint if e and e.thumbprint else "") or self._padrao()
        return thumb.strip().replace(" ", "").upper()

    def _avaliar_empresas(self, indice: dict) -> tuple[list[str], list[Resultado]]:
        """Separa as empresas em (aptas, bloqueadas por certificado)."""
        aptas, bloqueadas = [], []
        for e in self._empresas:
            problema = _problema_cert(self._thumb_da_empresa(e), indice)
            if problema:
                bloqueadas.append(Resultado(e.cnpj, status="erro", detalhe=problema.capitalize()))
            else:
                aptas.append(e.cnpj)
        return aptas, bloqueadas

    def _empresa_por_cnpj(self, cnpj: str) -> repo.Empresa | None:
        return next((e for e in self._empresas if e.cnpj == cnpj), None)

    def _empresa_da_nota(self, nota: dict) -> repo.Empresa | None:
        cnpj = nota.get("empresa_cnpj")
        if cnpj:
            return self._empresa_por_cnpj(cnpj)
        return self._empresas[0] if len(self._empresas) == 1 else None

    def _validar_cert_empresa(self, empresa: repo.Empresa | None) -> bool:
        indice = self._indice_certs()
        if indice is None:
            return False
        problema = _problema_cert(self._thumb_da_empresa(empresa), indice)
        if problema:
            dono = (f"{empresa.razao_social or 'Empresa'} ({_fmt_cnpj(empresa.cnpj)})"
                    if empresa else "Empresa da nota")
            self.erro.emit("Certificado",
                           f"{dono}: {problema}.\nAbra as Configurações e ajuste o certificado.")
            return False
        return True

    def _validar_cert_nota(self, nota: dict) -> bool:
        return self._validar_cert_empresa(self._empresa_da_nota(nota))

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
        self._carregar_empresas()  # chamado ao salvar as Configurações
        try:
            indice = {c.thumbprint: c for c in certificados.listar()}
        except (RuntimeError, OSError, ValueError, KeyError):
            indice = {}

        cert = indice.get(self._padrao())
        if cert is None:
            self._cert_texto, self._cert_alerta = "Certificado não configurado", True
        else:
            self._cert_texto = f"{cert.titular.split(':')[0]} · {cert.situacao} até {cert.validade:%d/%m/%Y}"
            self._cert_alerta = cert.dias_restantes <= certificados.AVISO_DIAS

        # Certificados próprios das empresas: vencidos, ausentes ou perto de vencer
        problemas = 0
        for e in self._empresas:
            thumb = self._thumb_da_empresa(e)
            c = indice.get(thumb)
            if _problema_cert(thumb, indice) or (c and c.dias_restantes <= certificados.AVISO_DIAS):
                problemas += 1
        if problemas:
            self._cert_texto += f"  ·  {problemas} empresa(s) com problema"
            self._cert_alerta = True

        self.recarregar()
        self.alterado.emit()

    # ---------- Sincronização ----------
    @Slot()
    def sincronizar(self) -> None:
        if self._ocupado or limite.segundos_restantes() > 0:
            return
        self._carregar_empresas()
        if not self._empresas:
            self._sync_ok([])
            return

        indice = self._indice_certs()
        if indice is None:
            return
        aptas, bloqueadas = self._avaliar_empresas(indice)
        if not aptas:
            # Nada vai à SEFAZ, então o intervalo de 1h não é consumido.
            self.erro.emit("Certificado",
                           "Nenhuma empresa tem certificado válido:\n"
                           + "\n".join(f"{_fmt_cnpj(r.cnpj)}: {r.detalhe}" for r in bloqueadas))
            return

        limite.registrar_disparo()
        self._set_status("Sincronizando com a SEFAZ…", True)
        self._executar(lambda: _sincronizar_lista(aptas, bloqueadas),
                       self._sync_ok, self._sync_erro)

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

    # ---------- XML (lista) ----------
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
            self._copiar_local(Path(nota["caminho_xml"] or ""), pasta, nota["chave"])
            return

        if not self._validar_cert_nota(nota):
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

    # ---------- XML por chave ----------
    @Slot(str, result=str)
    def analisarChave(self, texto: str) -> str:
        """Valida enquanto digita/bipa. Retorna a chave normalizada (ou "")."""
        texto = (texto or "").strip()
        self._chave_info, self._chave_msg = None, ""
        if texto:
            chave = extrair_chave(texto)
            if chave:
                self._chave_info = analisar_chave(chave)
                self._chave_msg = "✓  " + self._chave_info.resumo()
            else:
                try:
                    analisar_chave(texto)
                except ChaveInvalida as e:
                    self._chave_msg = f"✕  {e}"
        self.chaveChanged.emit()
        return self._chave_info.chave if self._chave_info else ""

    @Slot(str, result=bool)
    def baixarChave(self, texto: str) -> bool:
        if self._ocupado or not self.analisarChave(texto):
            return False
        chave = self._chave_info.chave
        pasta = self._pasta_salva()
        if pasta is None:
            self.solicitarPastaChave.emit(chave)
        else:
            self._prosseguir_chave(chave, pasta)
        return True

    @Slot(str, str)
    def continuarChaveComPasta(self, chave: str, url: str) -> None:
        self._prosseguir_chave(chave, Path(QUrl(url).toLocalFile()))

    def _prosseguir_chave(self, chave: str, pasta: Path) -> None:
        try:
            sit = situacao_chave(chave)
        except Exception:  # noqa: BLE001 - sem banco, trata como nota nova
            sit = None

        if sit and sit["caminho"] and Path(sit["caminho"]).is_file():
            if self._copiar_local(Path(sit["caminho"]), pasta, chave):
                self._limpar_chave()
            return

        self._carregar_empresas()
        if sit and sit["empresa_cnpj"]:
            empresa = self._empresa_por_cnpj(sit["empresa_cnpj"])
        elif self._empresa_filtro:
            empresa = self._empresa_por_cnpj(self._empresa_filtro)
        elif len(self._empresas) == 1:
            empresa = self._empresas[0]
        else:
            empresa = None
            self.erro.emit("Baixar por chave",
                           "Nenhuma empresa cadastrada." if not self._empresas else
                           "Selecione no seletor do topo qual empresa é a destinatária da nota.")
            return
        if empresa is None:
            self.erro.emit("Baixar por chave", "A empresa desta nota não está ativa.")
            return
        if not self._validar_cert_empresa(empresa):
            return

        self._cnpj_da_chave[chave] = empresa.cnpj
        if not (sit and sit["ciencia"]):
            self.solicitarCienciaChave.emit(chave, str(pasta))
            return
        self._baixar_chave(chave, pasta)

    @Slot(str, str)
    def confirmarCienciaChave(self, chave: str, pasta: str) -> None:
        if chave in self._cnpj_da_chave:
            self._baixar_chave(chave, Path(pasta))

    def _baixar_chave(self, chave: str, pasta: Path) -> None:
        cnpj = self._cnpj_da_chave.pop(chave, "")
        self._set_status("Baixando XML pela chave…", True)
        self._executar(lambda: baixar_por_chave(chave, cnpj, pasta),
                       self._chave_ok, self._download_erro)

    def _chave_ok(self, destino: Path) -> None:
        self._download_ok(destino)
        self._limpar_chave()

    def _limpar_chave(self) -> None:
        self._chave_info, self._chave_msg = None, ""
        self.chaveChanged.emit()
        self.chaveConcluida.emit()

    # ---------- Janela ----------
    @Slot(result=bool)
    def podeFechar(self) -> bool:
        return not self._ocupado
