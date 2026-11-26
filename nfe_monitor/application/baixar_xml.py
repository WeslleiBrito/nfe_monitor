import logging
import re
import shutil
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nfe_monitor.application.sincronizar import _config_da_empresa
from nfe_monitor.domain.resumo import FUSO
from nfe_monitor.infrastructure.database import notas_repository as repo
from nfe_monitor.infrastructure.database.conexao import conectar
from nfe_monitor.infrastructure.paths import PASTA_XML
from nfe_monitor.infrastructure.sefaz import cliente, distribuicao
from nfe_monitor.infrastructure.sefaz.manifestacao import (
    CSTAT_DUPLICIDADE, CSTATS_CIENCIA_OK, ErroEvento, enviar_ciencia,
)
from nfe_monitor.infrastructure.sefaz.parametros import Config

__all__ = [
    "ErroEvento", "manifestar_ciencia", "baixar_xml_completo", "obter_xml",
    "empresa_da_nota", "caminho_livre", "baixar_e_copiar",
    "ChaveInvalida", "InfoChave", "analisar_chave", "extrair_chave",
    "situacao_chave", "baixar_por_chave",
]

log = logging.getLogger("nfe_monitor")

UFS = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}

LIMITE_POR_HORA = 10  # consultas por chave, por CNPJ, por hora (proteção contra 656)
_consultas: dict[str, deque] = defaultdict(deque)


# ---------- Chave de acesso ----------
class ChaveInvalida(ValueError):
    pass


@dataclass(frozen=True)
class InfoChave:
    chave: str
    uf: str
    emissao: str
    cnpj_emitente: str
    serie: int
    numero: int

    def resumo(self) -> str:
        c = self.cnpj_emitente
        cnpj = f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
        return f"NF {self.numero} · Série {self.serie} · CNPJ {cnpj} · {self.uf} · {self.emissao}"


def _dv(base43: str) -> int:
    soma, peso = 0, 2
    for d in reversed(base43):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    r = 11 - soma % 11
    return 0 if r >= 10 else r


def analisar_chave(texto: str) -> InfoChave:
    d = re.sub(r"\D", "", texto or "")
    if len(d) != 44:
        raise ChaveInvalida(f"A chave tem {len(d)} dígitos; são necessários 44.")
    if _dv(d[:43]) != int(d[43]):
        raise ChaveInvalida("Dígito verificador não confere. Leia ou digite novamente.")
    uf = UFS.get(d[:2])
    if uf is None:
        raise ChaveInvalida(f"Código de UF inválido: {d[:2]}.")
    if not 1 <= int(d[4:6]) <= 12:
        raise ChaveInvalida("Mês de emissão inválido na chave.")
    modelo = d[20:22]
    if modelo == "65":
        raise ChaveInvalida("Esta é uma NFC-e (modelo 65); a SEFAZ não a distribui por chave.")
    if modelo != "55":
        raise ChaveInvalida(f"Modelo {modelo} não é NF-e (55).")
    return InfoChave(
        chave=d, uf=uf, emissao=f"{d[4:6]}/20{d[2:4]}", cnpj_emitente=d[6:20],
        serie=int(d[22:25]), numero=int(d[25:34]),
    )


def extrair_chave(texto: str) -> str | None:
    """Procura uma chave válida de 44 dígitos em qualquer texto (aceita espaços e pontos)."""
    for trecho in re.finditer(r"\d[\d\s.\-/]*\d", texto or ""):
        d = re.sub(r"\D", "", trecho.group())
        for i in range(len(d) - 43):
            try:
                return analisar_chave(d[i:i + 44]).chave
            except ChaveInvalida:
                continue
    return None


def situacao_chave(chave: str) -> dict | None:
    """Estado local da nota (sem SEFAZ). None = nota não está no banco."""
    con = conectar(Config().banco)
    try:
        row = con.execute(
            "SELECT empresa_cnpj, caminho_xml FROM nfe WHERE chave = ?", (chave,)
        ).fetchone()
        if row is None:
            return None
        return {"empresa_cnpj": row[0] or "", "caminho": row[1] or "",
                "ciencia": bool(repo.tem_ciencia(con, chave))}
    finally:
        con.close()


def _registrar_consulta(cnpj: str) -> None:
    agora, fila = time.monotonic(), _consultas[cnpj]
    while fila and agora - fila[0] > 3600:
        fila.popleft()
    if len(fila) >= LIMITE_POR_HORA:
        minutos = int((3600 - (agora - fila[0])) // 60) + 1
        raise ErroEvento(f"Limite de {LIMITE_POR_HORA} consultas por chave/hora atingido. "
                         f"Tente novamente em {minutos} min.")
    fila.append(agora)


# ---------- Fluxo existente ----------
def empresa_da_nota(con, chave: str) -> repo.Empresa:
    """Descobre a empresa monitorada que recebeu a nota."""
    row = con.execute("SELECT empresa_cnpj FROM nfe WHERE chave = ?", (chave,)).fetchone()
    cnpj = row[0] if row else None

    if not cnpj:
        # Nota antiga sem empresa: só dá para deduzir se houver uma única empresa ativa.
        ativas = repo.listar_empresas(con)
        if len(ativas) != 1:
            raise ErroEvento("Não foi possível identificar a empresa desta nota.")
        cnpj = ativas[0].cnpj

    return _empresa_valida(con, cnpj)


def _empresa_valida(con, cnpj: str) -> repo.Empresa:
    empresa = repo.obter_empresa(con, cnpj)
    if empresa is None:
        raise ErroEvento(f"Empresa {cnpj} não está cadastrada.")
    if not empresa.completa:
        raise ErroEvento(f"Cadastro da empresa {cnpj} incompleto (UF ou certificado).")
    return empresa


def _caminho_salvo(con, chave: str, padrao: Path) -> Path:
    row = con.execute("SELECT caminho_xml FROM nfe WHERE chave = ?", (chave,)).fetchone()
    return Path(row[0]) if row and row[0] else padrao


def manifestar_ciencia(con, cnpj: str, chave: str, cfg: Config) -> None:
    inicio = datetime.now(FUSO)
    try:
        cstat, motivo = enviar_ciencia(chave, cnpj, cfg)
    except Exception as e:
        with con:
            repo.registrar_operacao(con, "ciencia", chave, inicio, "erro", str(e))
        raise

    if cstat in CSTATS_CIENCIA_OK or cstat == CSTAT_DUPLICIDADE:
        with con:
            repo.atualizar_manifestacao(con, chave, "ciencia")
            repo.registrar_operacao(con, "ciencia", chave, inicio, "ok", f"{cstat} {motivo}")
        log.info("Ciência registrada para %s: %s %s", chave, cstat, motivo)
        return

    with con:
        repo.registrar_operacao(con, "ciencia", chave, inicio, "erro", f"{cstat} {motivo}")
    raise ErroEvento(f"A SEFAZ recusou a ciência: {cstat} - {motivo}")


def baixar_xml_completo(con, cnpj: str, chave: str, cfg: Config) -> Path:
    inicio = datetime.now(FUSO)
    try:
        corpo = cliente.consultar_chave(cnpj, chave, cfg)
        lote = distribuicao.ler_lote(corpo, exigir_nsu=False)

        if lote.cstat == distribuicao.CSTAT_ESPERA:
            raise ErroEvento(f"SEFAZ pediu espera (656): {lote.motivo}")
        if lote.cstat not in (distribuicao.CSTAT_SEM_DOCS, distribuicao.CSTAT_COM_DOCS):
            raise ErroEvento(f"SEFAZ respondeu cStat {lote.cstat}: {lote.motivo}")

        for doc in lote.docs:
            if doc.tipo != "completo":
                continue
            resumo = distribuicao.ler_completo(doc.xml)
            if resumo.chave == chave:
                with con:
                    repo.salvar_completo(con, resumo, doc.xml, PASTA_XML, cnpj)
                    repo.registrar_operacao(con, "consulta_chave", chave, inicio, "ok",
                                            f"{lote.cstat} {lote.motivo}")
                return _caminho_salvo(con, chave, PASTA_XML / cnpj / f"{chave}.xml")

        raise ErroEvento(
            "A SEFAZ não retornou o XML completo desta nota. "
            f"Resposta: {lote.cstat} {lote.motivo}"
        )
    except Exception as e:
        with con:
            repo.registrar_operacao(con, "consulta_chave", chave, inicio, "erro", str(e))
        raise


def obter_xml(con, cnpj: str, chave: str, cfg: Config | None = None) -> Path:
    """Fluxo completo para uma nota resumo: ciência (se preciso) e depois o XML completo."""
    cfg = cfg or Config()
    if not repo.tem_ciencia(con, chave):
        manifestar_ciencia(con, cnpj, chave, cfg)
    return baixar_xml_completo(con, cnpj, chave, cfg)


def caminho_livre(pasta: Path, nome: str) -> Path:
    destino = pasta / nome
    base, ext, n = destino.stem, destino.suffix, 1
    while destino.exists():
        destino = pasta / f"{base} ({n}){ext}"
        n += 1
    return destino


def baixar_e_copiar(chave: str, pasta: Path) -> Path:
    cfg = Config()
    con = conectar(cfg.banco)
    try:
        empresa = empresa_da_nota(con, chave)
        cfg_emp = _config_da_empresa(empresa, cfg)
        origem = obter_xml(con, empresa.cnpj, chave, cfg_emp)
    finally:
        con.close()
    destino = caminho_livre(Path(pasta), f"{chave}.xml")
    shutil.copy2(origem, destino)
    return destino


# ---------- Download por chave digitada/bipada ----------
def baixar_por_chave(chave: str, cnpj: str, pasta: Path) -> Path:
    """Baixa uma NF-e pela chave, mesmo que ela ainda não tenha chegado pela sincronização."""
    chave = analisar_chave(chave).chave
    cfg = Config()
    con = conectar(cfg.banco)
    try:
        row = con.execute("SELECT empresa_cnpj, caminho_xml FROM nfe WHERE chave = ?",
                          (chave,)).fetchone()
        if row and row[1] and Path(row[1]).is_file():
            origem = Path(row[1])  # já baixado: nenhuma consulta à SEFAZ
        else:
            empresa = empresa_da_nota(con, chave) if row and row[0] else _empresa_valida(con, cnpj)
            cfg_emp = _config_da_empresa(empresa, cfg)
            _registrar_consulta(empresa.cnpj)
            try:
                origem = obter_xml(con, empresa.cnpj, chave, cfg_emp)
            except ErroEvento as e:
                raise ErroEvento(
                    f"{e}\n\nConfira se a empresa {empresa.cnpj} é a destinatária desta nota."
                ) from e
            with con:  # nota nova: grava a ciência que não tinha registro para atualizar
                repo.atualizar_manifestacao(con, chave, "ciencia")
    finally:
        con.close()
    destino = caminho_livre(Path(pasta), f"{chave}.xml")
    shutil.copy2(origem, destino)
    return destino
