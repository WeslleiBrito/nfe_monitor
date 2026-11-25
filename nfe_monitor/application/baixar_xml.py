import logging
import shutil
from datetime import datetime
from pathlib import Path

from nfe_monitor.domain.resumo import FUSO
from nfe_monitor.infrastructure.database import notas_repository as repo
from nfe_monitor.infrastructure.database.conexao import conectar
from nfe_monitor.infrastructure.paths import CNPJ, PASTA_XML
from nfe_monitor.infrastructure.sefaz import cliente, distribuicao
from nfe_monitor.infrastructure.sefaz.manifestacao import (
    CSTAT_DUPLICIDADE, CSTATS_CIENCIA_OK, ErroEvento, enviar_ciencia,
)
from nfe_monitor.infrastructure.sefaz.parametros import Config

__all__ = [
    "ErroEvento", "manifestar_ciencia", "baixar_xml_completo", "obter_xml",
    "caminho_livre", "baixar_e_copiar",
]

log = logging.getLogger("nfe_monitor")


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
                    repo.salvar_completo(con, resumo, doc.xml, PASTA_XML)
                    repo.registrar_operacao(con, "consulta_chave", chave, inicio, "ok",
                                            f"{lote.cstat} {lote.motivo}")
                return PASTA_XML / f"{chave}.xml"

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
        origem = obter_xml(con, CNPJ, chave, cfg)
    finally:
        con.close()
    destino = caminho_livre(pasta, f"{chave}.xml")
    shutil.copy2(origem, destino)
    return destino
