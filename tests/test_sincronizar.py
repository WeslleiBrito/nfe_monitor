import pytest

from nfe_monitor.application import sincronizar as sinc
from nfe_monitor.infrastructure.database import notas_repository as repo
from nfe_monitor.infrastructure.database.conexao import conectar
from nfe_monitor.infrastructure.sefaz.distribuicao import Lote
from nfe_monitor.infrastructure.sefaz.parametros import Config

A, B, C = "11444777000161", "11222333000181", "33000167000101"
FIM = Lote("137", "Nenhum", "0" * 15, "0" * 15)


@pytest.fixture
def cfg(tmp_path):
    cfg = Config(banco=tmp_path / "t.db", thumbprint="PADRAO")
    con = conectar(cfg.banco)
    with con:
        repo.salvar_empresa(con, repo.Empresa(A, "A", "BA", "TA"))
        repo.salvar_empresa(con, repo.Empresa(B, "B", "SP", "TB"))
    con.close()
    return cfg


def _sefaz(monkeypatch, respostas: dict):
    """respostas: cnpj -> Lote. Guarda o Config usado em cada chamada."""
    usados = {}

    def consultar(cnpj, ult, cfg):
        usados[cnpj] = cfg
        return cnpj
    monkeypatch.setattr(sinc.cliente, "consultar", consultar)
    monkeypatch.setattr(sinc.distribuicao, "ler_lote", lambda corpo: respostas[corpo])
    return usados


def _bloqueada(cfg, cnpj):
    con = conectar(cfg.banco)
    try:
        return repo.bloqueada_ate(con, cnpj) is not None
    finally:
        con.close()


def test_cnpj_valido():
    assert sinc.cnpj_valido(A) and sinc.cnpj_valido(B) and sinc.cnpj_valido(C)
    assert not sinc.cnpj_valido("12345678000199")
    assert not sinc.cnpj_valido("00000000000000")


def test_cnpj_invalido_nao_chama_sefaz(cfg, monkeypatch):
    usados = _sefaz(monkeypatch, {})
    with pytest.raises(sinc.CnpjInvalido):
        sinc.sincronizar("12345678000199", cfg, forcar=True)
    with pytest.raises(sinc.CnpjInvalido):
        sinc.sincronizar(C, cfg, forcar=True)  # válido, mas não cadastrado
    assert usados == {}


def test_usa_certificado_e_uf_de_cada_empresa(cfg, monkeypatch):
    usados = _sefaz(monkeypatch, {A: FIM, B: FIM})
    sinc.sincronizar_todas(cfg)
    assert (usados[A].thumbprint, usados[A].uf_autor) == ("TA", "29")
    assert (usados[B].thumbprint, usados[B].uf_autor) == ("TB", "35")


def test_656_bloqueia_so_a_empresa(cfg, monkeypatch):
    _sefaz(monkeypatch, {A: Lote("656", "Consumo indevido", None, None), B: FIM})
    res = {r.cnpj: r.status for r in sinc.sincronizar_todas(cfg)}
    assert res == {A: "espera", B: "ok"}
    assert _bloqueada(cfg, A)


def test_fim_da_fila_pausa_1h(cfg, monkeypatch):
    _sefaz(monkeypatch, {A: Lote("138", "Ok", "5".zfill(15), "5".zfill(15))})
    sinc.sincronizar(A, cfg)
    assert _bloqueada(cfg, A)
    with pytest.raises(sinc.EsperaSefaz):
        sinc.sincronizar(A, cfg)


def test_cadastro_incompleto_usa_config_padrao(cfg, monkeypatch):
    con = conectar(cfg.banco)
    with con:
        repo.salvar_empresa(con, repo.Empresa(C))
    con.close()
    usados = _sefaz(monkeypatch, {C: FIM})
    sinc.sincronizar(C, cfg)
    assert (usados[C].thumbprint, usados[C].uf_autor) == ("PADRAO", "29")
