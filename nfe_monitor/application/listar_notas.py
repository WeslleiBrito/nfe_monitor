from nfe_monitor.infrastructure.database import notas_repository as repo
from nfe_monitor.infrastructure.database.conexao import conectar
from nfe_monitor.infrastructure.paths import DB

__all__ = ["ITENS_POR_PAGINA", "consultar_notas"]

ITENS_POR_PAGINA = 50


def consultar_notas(fornecedor: str, inicio: str | None, fim: str | None,
                    pagina: int, empresa_cnpj: str | None = None) -> tuple[list[dict], dict]:
    """Consulta somente a página pedida e calcula as métricas dos filtros ativos.

    empresa_cnpj vazio ou None = notas de todas as empresas.
    """
    con = conectar(DB)
    try:
        return repo.buscar_pagina(con, fornecedor, inicio, fim,
                                  ITENS_POR_PAGINA, pagina * ITENS_POR_PAGINA,
                                  empresa_cnpj or None)
    finally:
        con.close()
