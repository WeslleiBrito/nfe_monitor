import logging
import sys
from dataclasses import dataclass, replace
from datetime import datetime

from nfe_monitor.domain.resumo import FUSO
from nfe_monitor.infrastructure.database import notas_repository as repo
from nfe_monitor.infrastructure.database.conexao import UF_CODIGO, conectar
from nfe_monitor.infrastructure.paths import PASTA_XML
from nfe_monitor.infrastructure.sefaz import cliente, distribuicao
from nfe_monitor.infrastructure.sefaz.parametros import Config

__all__ = [
    "CSTATS_OK", "MINUTOS_FIM_FILA", "MINUTOS_656",
    "EsperaSefaz", "CnpjInvalido", "Resultado",
    "cnpj_valido", "sincronizar", "sincronizar_todas",
]

log = logging.getLogger("nfe_monitor")

CSTATS_OK = (distribuicao.CSTAT_SEM_DOCS, distribuicao.CSTAT_COM_DOCS)
MINUTOS_FIM_FILA = 60  # regra da SEFAZ: aguardar 1h ao zerar a fila
MINUTOS_656 = 60


class EsperaSefaz(RuntimeError):
    """A SEFAZ pediu para aguardar (656) ou a empresa ainda está no intervalo de espera."""


class CnpjInvalido(ValueError):
    """CNPJ com dígito verificador errado ou não cadastrado."""


@dataclass
class Resultado:
    cnpj: str
    novas: int = 0
    status: str = "ok"          # ok, espera ou erro
    detalhe: str = ""


def cnpj_valido(cnpj: str) -> bool:
    """Confere formato e dígitos verificadores do CNPJ."""
    if len(cnpj) != 14 or not cnpj.isdigit() or len(set(cnpj)) == 1:
        return False

    def dv(base: str) -> str:
        pesos = list(range(len(base) - 7, 1, -1)) + list(range(9, 1, -1))
        resto = sum(int(d) * p for d, p in zip(base, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = dv(cnpj[:12])
    return cnpj[12:] == d1 + dv(cnpj[:12] + d1)


def _config_da_empresa(e: repo.Empresa, cfg: Config) -> Config:
    """Usa o certificado e a UF da empresa; o que faltar vem do Config atual."""
    return replace(
        cfg,
        thumbprint=e.thumbprint or cfg.thumbprint,
        uf_autor=UF_CODIGO[e.uf] if e.uf else cfg.uf_autor,
    )


def _processar_lote(con, cnpj: str, lote: distribuicao.Lote) -> int:
    novas = 0
    for doc in lote.docs:
        if doc.tipo == "resumo":
            if repo.inserir_resumo(con, distribuicao.ler_resumo(doc.xml), cnpj):
                novas += 1
        elif doc.tipo == "completo":
            r = distribuicao.ler_completo(doc.xml)
            if repo.salvar_completo(con, r, doc.xml, PASTA_XML, cnpj):
                novas += 1
    return novas


def sincronizar(cnpj: str, cfg: Config | None = None, forcar: bool = False) -> int:
    """Consulta a distribuição a partir do último NSU. Retorna quantas notas novas entraram."""
    cnpj = "".join(c for c in cnpj if c.isdigit())
    if not cnpj_valido(cnpj):
        raise CnpjInvalido(f"CNPJ inválido: {cnpj or '(vazio)'}")

    cfg = cfg or Config()
    con = conectar(cfg.banco)
    inicio = datetime.now(FUSO)
    novas = 0
    try:
        empresa = repo.obter_empresa(con, cnpj)
        if empresa is None:
            raise CnpjInvalido(f"CNPJ {cnpj} não está cadastrado")
        if not forcar and (ate := repo.bloqueada_ate(con, cnpj)):
            raise EsperaSefaz(f"Aguardando a SEFAZ até {ate:%d/%m %H:%M}")

        cfg_emp = _config_da_empresa(empresa, cfg)
        ult = repo.ler_ult_nsu(con, cnpj)
        log.info("Consultando %s a partir do NSU %s", cnpj, ult)

        while True:
            lote = distribuicao.ler_lote(cliente.consultar(cnpj, ult, cfg_emp))

            if lote.cstat == distribuicao.CSTAT_ESPERA:
                with con:
                    ate = repo.bloquear_empresa(con, cnpj, MINUTOS_656)
                    repo.registrar_operacao(con, "sincronizacao", None, inicio, "erro",
                                            f"{cnpj}: 656 {lote.motivo}")
                raise EsperaSefaz(f"{lote.motivo} (liberado às {ate:%H:%M})")
            if lote.cstat not in CSTATS_OK:
                raise RuntimeError(f"SEFAZ respondeu cStat {lote.cstat}: {lote.motivo}")

            # Lote e NSU na mesma transação: se falhar no meio, nada é perdido.
            with con:
                novas += _processar_lote(con, cnpj, lote)
                repo.salvar_ult_nsu(con, cnpj, lote.ult_nsu, lote.max_nsu)

            log.info("Lote %s: cStat=%s, %d docs, NSU %s/%s",
                     cnpj, lote.cstat, len(lote.docs), lote.ult_nsu, lote.max_nsu)

            if lote.cstat == distribuicao.CSTAT_SEM_DOCS or lote.ult_nsu == lote.max_nsu:
                with con:
                    repo.bloquear_empresa(con, cnpj, MINUTOS_FIM_FILA)
                break
            if lote.ult_nsu == ult:  # NSU não avançou: evita laço infinito
                break
            ult = lote.ult_nsu

        with con:
            repo.registrar_operacao(con, "sincronizacao", None, inicio, "ok",
                                    f"{cnpj}: {novas} novas")
    except (EsperaSefaz, CnpjInvalido):
        raise
    except Exception as e:
        with con:
            repo.registrar_operacao(con, "sincronizacao", None, inicio, "erro",
                                    f"{cnpj}: {e}"[:500])
        raise
    finally:
        con.close()

    return novas


def sincronizar_todas(cfg: Config | None = None) -> list[Resultado]:
    """Sincroniza todas as empresas ativas. Uma falha não interrompe as demais."""
    cfg = cfg or Config()
    con = conectar(cfg.banco)
    try:
        cnpjs = [e.cnpj for e in repo.listar_empresas(con)]
    finally:
        con.close()

    resultados = []
    for cnpj in cnpjs:
        res = Resultado(cnpj)
        try:
            res.novas = sincronizar(cnpj, cfg)
        except EsperaSefaz as e:
            res.status, res.detalhe = "espera", str(e)
        except Exception as e:
            res.status, res.detalhe = "erro", str(e)
            log.exception("Falha ao sincronizar %s", cnpj)
        resultados.append(res)
    return resultados


def _main(argv: list[str]) -> int:
    forcar = "--forcar" in argv
    args = [a for a in argv if a != "--forcar"]

    if len(args) > 1:
        print("Uso: python -m nfe_monitor.application.sincronizar [CNPJ] [--forcar]")
        return 1

    if args:
        try:
            print(f"Notas novas: {sincronizar(args[0], forcar=forcar)}")
            return 0
        except CnpjInvalido as e:
            log.error("%s", e)
            return 1
        except EsperaSefaz as e:
            log.warning("SEFAZ pediu espera: %s", e)
            return 2
        except Exception as e:
            log.error("Falha na sincronização: %s", e)
            return 3

    resultados = sincronizar_todas()
    if not resultados:
        print("Nenhuma empresa cadastrada.")
        return 1
    for r in resultados:
        print(f"{r.cnpj}  {r.status:<7} novas={r.novas}  {r.detalhe}")
    return 0 if all(r.status != "erro" for r in resultados) else 3


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(_main(sys.argv[1:]))
