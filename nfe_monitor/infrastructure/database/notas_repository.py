import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from nfe_monitor.domain.resumo import FUSO, Resumo
from nfe_monitor.infrastructure.database.conexao import UF_CODIGO

__all__ = [
    "NSU_ZERO", "Empresa",
    "salvar_empresa", "obter_empresa", "listar_empresas", "desativar_empresa",
    "ler_ult_nsu", "salvar_ult_nsu", "bloquear_empresa", "bloqueada_ate", "empresas_prontas",
    "inserir_resumo", "salvar_completo", "registrar_operacao",
    "atualizar_manifestacao", "tem_ciencia", "buscar_pagina",
]

NSU_ZERO = "0" * 15
_FMT = "%Y-%m-%d %H:%M:%S"


def _agora() -> str:
    return datetime.now(FUSO).strftime(_FMT)


def _cursor(con: sqlite3.Connection) -> sqlite3.Cursor:
    """Cursor com acesso por nome, sem alterar o row_factory da conexão."""
    cur = con.cursor()
    cur.row_factory = sqlite3.Row
    return cur


# ---------------------------------------------------------------- empresas
@dataclass
class Empresa:
    cnpj: str
    razao_social: str | None = None
    uf: str | None = None
    thumbprint: str | None = None
    origem: str = "windows"
    ativo: bool = True

    @property
    def completa(self) -> bool:
        """Cadastro pronto para consultar a SEFAZ."""
        return bool(self.uf and self.thumbprint)

    @property
    def c_uf_autor(self) -> str:
        if not self.uf:
            raise ValueError(f"Empresa {self.cnpj} sem UF cadastrada")
        return UF_CODIGO[self.uf]


def _para_empresa(r: sqlite3.Row) -> Empresa:
    return Empresa(r["cnpj"], r["razao_social"], r["uf"], r["thumbprint"],
                   r["origem"], bool(r["ativo"]))


def salvar_empresa(con: sqlite3.Connection, e: Empresa) -> None:
    if len(e.cnpj) != 14 or not e.cnpj.isdigit():
        raise ValueError(f"CNPJ inválido: {e.cnpj}")
    if e.uf is not None and e.uf not in UF_CODIGO:
        raise ValueError(f"UF inválida: {e.uf}")
    con.execute(
        """INSERT INTO empresas (cnpj, razao_social, uf, thumbprint, origem, ativo)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(cnpj) DO UPDATE SET
               razao_social = excluded.razao_social, uf = excluded.uf,
               thumbprint = excluded.thumbprint, origem = excluded.origem,
               ativo = excluded.ativo""",
        (e.cnpj, e.razao_social, e.uf, e.thumbprint, e.origem, int(e.ativo)),
    )
    con.execute(
        "INSERT OR IGNORE INTO controle_nsu (cnpj, ult_nsu, atualizado_em) VALUES (?, ?, ?)",
        (e.cnpj, NSU_ZERO, _agora()),
    )


def obter_empresa(con: sqlite3.Connection, cnpj: str) -> Empresa | None:
    r = _cursor(con).execute("SELECT * FROM empresas WHERE cnpj = ?", (cnpj,)).fetchone()
    return _para_empresa(r) if r else None


def listar_empresas(con: sqlite3.Connection, somente_ativas: bool = True) -> list[Empresa]:
    sql = "SELECT * FROM empresas" + (" WHERE ativo = 1" if somente_ativas else "")
    return [_para_empresa(r) for r in _cursor(con).execute(sql + " ORDER BY razao_social")]


def desativar_empresa(con: sqlite3.Connection, cnpj: str) -> None:
    """Para de monitorar sem apagar as notas já baixadas."""
    con.execute("UPDATE empresas SET ativo = 0 WHERE cnpj = ?", (cnpj,))


# ---------------------------------------------------------------- NSU e bloqueio
def ler_ult_nsu(con: sqlite3.Connection, cnpj: str) -> str:
    row = con.execute("SELECT ult_nsu FROM controle_nsu WHERE cnpj = ?", (cnpj,)).fetchone()
    return row[0] if row else NSU_ZERO


def salvar_ult_nsu(con: sqlite3.Connection, cnpj: str, nsu: str,
                   max_nsu: str | None = None) -> None:
    con.execute(
        """INSERT INTO controle_nsu (cnpj, ult_nsu, max_nsu, atualizado_em) VALUES (?, ?, ?, ?)
           ON CONFLICT(cnpj) DO UPDATE SET
               ult_nsu       = excluded.ult_nsu,
               max_nsu       = COALESCE(excluded.max_nsu, controle_nsu.max_nsu),
               atualizado_em = excluded.atualizado_em""",
        (cnpj, nsu.zfill(15), max_nsu.zfill(15) if max_nsu else None, _agora()),
    )


def bloquear_empresa(con: sqlite3.Connection, cnpj: str, minutos: int = 60) -> datetime:
    """Chamar quando a SEFAZ retornar cStat 656 (consumo indevido)."""
    ate = datetime.now(FUSO) + timedelta(minutes=minutos)
    con.execute(
        """INSERT INTO controle_nsu (cnpj, ult_nsu, bloqueado_ate) VALUES (?, ?, ?)
           ON CONFLICT(cnpj) DO UPDATE SET bloqueado_ate = excluded.bloqueado_ate""",
        (cnpj, NSU_ZERO, ate.strftime(_FMT)),
    )
    return ate


def bloqueada_ate(con: sqlite3.Connection, cnpj: str) -> datetime | None:
    """Retorna até quando a empresa está bloqueada, ou None se estiver livre."""
    row = con.execute("SELECT bloqueado_ate FROM controle_nsu WHERE cnpj = ?", (cnpj,)).fetchone()
    if not row or not row[0] or row[0] <= _agora():
        return None
    return datetime.strptime(row[0], _FMT).replace(tzinfo=FUSO)


def empresas_prontas(con: sqlite3.Connection) -> list[Empresa]:
    """Empresas ativas, com cadastro completo e fora do bloqueio."""
    return [e for e in listar_empresas(con)
            if e.completa and bloqueada_ate(con, e.cnpj) is None]


# ---------------------------------------------------------------- notas
def inserir_resumo(con: sqlite3.Connection, r: Resumo,
                   empresa_cnpj: str | None = None) -> bool:
    """Insere o resumo se a nota ainda não existir. Retorna True se foi nova."""
    cur = con.execute(
        """INSERT OR IGNORE INTO nfe
           (chave, empresa_cnpj, emitente_cnpj, emitente_nome, data_emissao,
            valor, situacao, protocolo, tipo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'resumo')""",
        (r.chave, empresa_cnpj, r.emitente_cnpj, r.emitente_nome, r.data_emissao,
         str(r.valor), r.situacao, r.protocolo),
    )
    return cur.rowcount == 1


def salvar_completo(con: sqlite3.Connection, r: Resumo, xml: str, pasta: Path,
                    empresa_cnpj: str | None = None) -> bool:
    """Grava o XML em disco e a nota no banco. Retorna True se a nota era nova."""
    existia = con.execute("SELECT 1 FROM nfe WHERE chave = ?", (r.chave,)).fetchone() is not None

    destino = pasta / empresa_cnpj if empresa_cnpj else pasta
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"{r.chave}.xml"
    caminho.write_text(xml, encoding="utf-8")

    con.execute(
        """INSERT INTO nfe (chave, empresa_cnpj, emitente_cnpj, emitente_nome, data_emissao,
                            valor, situacao, protocolo, tipo, caminho_xml)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completo', ?)
           ON CONFLICT(chave) DO UPDATE SET
               tipo         = 'completo',
               caminho_xml  = excluded.caminho_xml,
               protocolo    = excluded.protocolo,
               situacao     = excluded.situacao,
               empresa_cnpj = COALESCE(nfe.empresa_cnpj, excluded.empresa_cnpj)""",
        (r.chave, empresa_cnpj, r.emitente_cnpj, r.emitente_nome, r.data_emissao,
         str(r.valor), r.situacao, r.protocolo, str(caminho)),
    )
    return not existia


def registrar_operacao(con: sqlite3.Connection, tipo: str, chave: str | None,
                       inicio: datetime, status: str, detalhe: str | None = None) -> None:
    """Grava uma linha de controle de tempo. O commit fica a cargo de quem chama."""
    con.execute(
        """INSERT INTO operacoes (tipo, chave, inicio, fim, status, detalhe)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (tipo, chave, inicio.strftime(_FMT), _agora(), status, detalhe),
    )


def atualizar_manifestacao(con: sqlite3.Connection, chave: str, situacao: str) -> None:
    con.execute("UPDATE nfe SET manifestacao = ? WHERE chave = ?", (situacao, chave))


def tem_ciencia(con: sqlite3.Connection, chave: str) -> bool:
    row = con.execute("SELECT manifestacao FROM nfe WHERE chave = ?", (chave,)).fetchone()
    return row is not None and row[0] == "ciencia"


# ---------------------------------------------------------------- consulta da tela
def _condicoes(fornecedor: str, inicio: str | None, fim: str | None,
               empresa_cnpj: str | None = None):
    condicoes, parametros = [], []
    if empresa_cnpj:
        condicoes.append("empresa_cnpj = ?")
        parametros.append(empresa_cnpj)
    if fornecedor.strip():
        condicoes.append("emitente_nome LIKE ?")
        parametros.append(f"%{fornecedor.strip()}%")
    if inicio:
        condicoes.append("data_emissao >= ?")
        parametros.append(f"{inicio} 00:00:00")
    if fim:
        condicoes.append("data_emissao <= ?")
        parametros.append(f"{fim} 23:59:59")
    where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
    return where, parametros


def buscar_pagina(con: sqlite3.Connection, fornecedor: str, inicio: str | None,
                  fim: str | None, limite: int, deslocamento: int,
                  empresa_cnpj: str | None = None) -> tuple[list[dict], dict]:
    """Retorna as notas da página e as métricas dos filtros ativos."""
    where, parametros = _condicoes(fornecedor, inicio, fim, empresa_cnpj)
    cur = _cursor(con)
    notas = cur.execute(
        f"""SELECT chave, empresa_cnpj, emitente_nome AS emitente, valor, data_emissao,
                   manifestacao, caminho_xml, caminho_xml IS NOT NULL AS xml_baixado
            FROM nfe {where}
            ORDER BY data_emissao DESC LIMIT ? OFFSET ?""",
        [*parametros, limite, deslocamento],
    ).fetchall()
    resumo = cur.execute(
        f"""SELECT COUNT(*) AS quantidade,
                   COALESCE(SUM(CAST(valor AS REAL)), 0) AS valor_total,
                   COALESCE(SUM(CASE WHEN caminho_xml IS NOT NULL THEN 1 ELSE 0 END), 0) AS baixados
            FROM nfe {where}""",
        parametros,
    ).fetchone()
    return [dict(n) for n in notas], dict(resumo)
