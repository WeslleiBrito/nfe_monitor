import sqlite3
from pathlib import Path

from nfe_monitor.infrastructure.sefaz.distribuicao import normalizar_data

__all__ = ["SCHEMA", "UF_CODIGO", "conectar"]

UF_CODIGO = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16",
    "TO": "17", "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25",
    "PE": "26", "AL": "27", "SE": "28", "BA": "29", "MG": "31", "ES": "32",
    "RJ": "33", "SP": "35", "PR": "41", "SC": "42", "RS": "43", "MS": "50",
    "MT": "51", "GO": "52", "DF": "53",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS empresas (
    cnpj          TEXT PRIMARY KEY,
    razao_social  TEXT,
    uf            TEXT,              -- sigla; NULL até o cadastro ser completado
    thumbprint    TEXT,              -- certificado no repositório do Windows
    origem        TEXT NOT NULL DEFAULT 'windows',   -- 'windows' ou caminho do .pfx
    ativo         INTEGER NOT NULL DEFAULT 1,
    criado_em     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS nfe (
    chave              TEXT PRIMARY KEY,
    empresa_cnpj       TEXT,            -- empresa monitorada que recebeu a nota
    emitente_cnpj      TEXT NOT NULL,
    emitente_nome      TEXT,
    data_emissao       TEXT,            -- 'AAAA-MM-DD HH:MM:SS', horário de Brasília
    valor              TEXT,            -- guardado como texto para preservar casas decimais
    situacao           TEXT,            -- cSitNFe no resumo; cStat do protocolo no completo
    protocolo          TEXT,
    manifestacao       TEXT NOT NULL DEFAULT 'pendente',
    caminho_xml        TEXT,            -- preenchido só quando o XML completo foi baixado
    tipo               TEXT NOT NULL DEFAULT 'resumo',  -- 'resumo' ou 'completo'
    criado_em          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS controle_nsu (
    cnpj           TEXT PRIMARY KEY,
    ult_nsu        TEXT NOT NULL,
    max_nsu        TEXT,
    bloqueado_ate  TEXT,             -- 'AAAA-MM-DD HH:MM:SS'; preenchido após cStat 656
    atualizado_em  TEXT
);
CREATE TABLE IF NOT EXISTS operacoes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo     TEXT NOT NULL,      -- sincronizacao, ciencia, consulta_chave, download_xml
    chave    TEXT,               -- NULL em sincronizacao
    inicio   TEXT NOT NULL,      -- 'AAAA-MM-DD HH:MM:SS', horário de Brasília
    fim      TEXT NOT NULL,
    status   TEXT NOT NULL,      -- ok ou erro
    detalhe  TEXT                -- cStat e motivo, ou mensagem de erro
);
"""

INDICES = """
CREATE INDEX IF NOT EXISTS ix_nfe_empresa ON nfe(empresa_cnpj);
"""


def conectar(caminho: Path) -> sqlite3.Connection:
    con = sqlite3.connect(caminho)
    con.executescript(SCHEMA)
    _migrar(con)
    con.executescript(INDICES)
    return con


def _colunas(con: sqlite3.Connection, tabela: str) -> set[str]:
    return {linha[1] for linha in con.execute(f"PRAGMA table_info({tabela})")}


def _adicionar_coluna(con: sqlite3.Connection, tabela: str, definicao: str) -> None:
    nome = definicao.split()[0]
    if nome not in _colunas(con, tabela):
        con.execute(f"ALTER TABLE {tabela} ADD COLUMN {definicao}")


def _migrar(con: sqlite3.Connection) -> None:
    """Atualiza bancos criados por versões anteriores. Seguro de executar sempre."""
    _adicionar_coluna(con, "nfe", "tipo TEXT NOT NULL DEFAULT 'resumo'")
    _adicionar_coluna(con, "nfe", "empresa_cnpj TEXT")
    _adicionar_coluna(con, "controle_nsu", "max_nsu TEXT")
    _adicionar_coluna(con, "controle_nsu", "bloqueado_ate TEXT")
    _adicionar_coluna(con, "controle_nsu", "atualizado_em TEXT")

    # Datas gravadas antes da normalização ainda têm 'T' e fuso.
    antigas = con.execute(
        "SELECT chave, data_emissao FROM nfe WHERE data_emissao LIKE '%T%'"
    ).fetchall()
    for chave, data in antigas:
        con.execute(
            "UPDATE nfe SET data_emissao = ? WHERE chave = ?",
            (normalizar_data(data), chave),
        )

    # Todo CNPJ com NSU vira empresa (cadastro incompleto até a Etapa 2).
    con.execute(
        "INSERT OR IGNORE INTO empresas (cnpj) SELECT cnpj FROM controle_nsu"
    )

    # Banco de versão anterior com uma única empresa: as notas antigas são dela.
    cnpjs = [linha[0] for linha in con.execute("SELECT cnpj FROM empresas")]
    if len(cnpjs) == 1:
        con.execute(
            "UPDATE nfe SET empresa_cnpj = ? WHERE empresa_cnpj IS NULL", (cnpjs[0],)
        )
    con.commit()
