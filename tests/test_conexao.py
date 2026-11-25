import sqlite3

from nfe_monitor.infrastructure.database.conexao import _colunas, conectar

SCHEMA_ANTIGO = """
CREATE TABLE nfe (
    chave TEXT PRIMARY KEY, emitente_cnpj TEXT NOT NULL, emitente_nome TEXT,
    data_emissao TEXT, valor TEXT, situacao TEXT, protocolo TEXT,
    manifestacao TEXT NOT NULL DEFAULT 'pendente', caminho_xml TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE controle_nsu (cnpj TEXT PRIMARY KEY, ult_nsu TEXT NOT NULL);
INSERT INTO controle_nsu VALUES ('12345678000199', '000000000000150');
INSERT INTO nfe (chave, emitente_cnpj, data_emissao)
    VALUES ('CHAVE1', '11111111000111', '2026-01-10T08:00:00-03:00');
"""


def _banco_antigo(tmp_path):
    caminho = tmp_path / "antigo.db"
    con = sqlite3.connect(caminho)
    con.executescript(SCHEMA_ANTIGO)
    con.close()
    return caminho


def test_migracao_adiciona_colunas(tmp_path):
    con = conectar(_banco_antigo(tmp_path))
    assert {"tipo", "empresa_cnpj"} <= _colunas(con, "nfe")
    assert {"max_nsu", "bloqueado_ate", "atualizado_em"} <= _colunas(con, "controle_nsu")


def test_migracao_preserva_nsu_e_cria_empresa(tmp_path):
    con = conectar(_banco_antigo(tmp_path))
    assert con.execute("SELECT ult_nsu FROM controle_nsu").fetchone()[0] == "000000000000150"
    assert con.execute("SELECT cnpj FROM empresas").fetchall() == [("12345678000199",)]


def test_migracao_atribui_notas_a_empresa_unica(tmp_path):
    con = conectar(_banco_antigo(tmp_path))
    assert con.execute("SELECT empresa_cnpj FROM nfe").fetchone()[0] == "12345678000199"


def test_migracao_idempotente(tmp_path):
    caminho = _banco_antigo(tmp_path)
    conectar(caminho).close()
    con = conectar(caminho)  # segunda execução não pode falhar nem duplicar
    assert con.execute("SELECT COUNT(*) FROM empresas").fetchone()[0] == 1
