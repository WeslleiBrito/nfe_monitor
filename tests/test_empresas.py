from datetime import datetime, timedelta

import pytest

from nfe_monitor.application import empresas
from nfe_monitor.infrastructure import preferencias
from nfe_monitor.infrastructure.certificados import Certificado, extrair_cnpj
from nfe_monitor.infrastructure.database import notas_repository as repo
from nfe_monitor.infrastructure.database.conexao import conectar
from nfe_monitor.infrastructure.sefaz.parametros import Config

CNPJ = "11444777000161"


def _cert(dias=365, cnpj=CNPJ, thumb="ABC123"):
    return Certificado(thumb, f"CN=EMPRESA TESTE LTDA:{cnpj}, O=ICP-Brasil",
                       datetime.now() + timedelta(days=dias), cnpj, "EMPRESA TESTE LTDA")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(preferencias, "ARQUIVO", tmp_path / "config.json")
    return Config(banco=tmp_path / "t.db", thumbprint="PADRAO")


def _ambiente(monkeypatch, cert, api):
    monkeypatch.setattr(empresas.certificados, "listar", lambda: [cert])
    monkeypatch.setattr(empresas.brasilapi, "consultar_cnpj", lambda c: api)


def _empresa(cfg):
    con = conectar(cfg.banco)
    try:
        return repo.obter_empresa(con, CNPJ)
    finally:
        con.close()


def test_extrair_cnpj_ecnpj():
    assert extrair_cnpj("CN=EMPRESA X LTDA:11444777000161, OU=AC, O=ICP-Brasil") == \
        ("11444777000161", "EMPRESA X LTDA")
    assert extrair_cnpj("CN=Fulano, O=Teste") == (None, None)


def test_cadastro_completo_com_brasilapi(cfg, monkeypatch):
    _ambiente(monkeypatch, _cert(), {"razao_social": "RAZAO API", "uf": "BA"})
    res = empresas.cadastrar_por_certificado("abc123", cfg)
    assert res.nova and res.avisos == []
    e = _empresa(cfg)
    assert (e.razao_social, e.uf, e.thumbprint, e.completa) == ("RAZAO API", "BA", "ABC123", True)
    assert preferencias.carregar().thumbprint == "ABC123"


def test_sem_brasilapi_usa_certificado_e_avisa_uf(cfg, monkeypatch):
    _ambiente(monkeypatch, _cert(), None)
    res = empresas.cadastrar_por_certificado("ABC123", cfg)
    e = _empresa(cfg)
    assert e.razao_social == "EMPRESA TESTE LTDA" and e.uf is None
    assert len(res.avisos) == 2


def test_uf_informada_dispensa_api(cfg, monkeypatch):
    _ambiente(monkeypatch, _cert(), None)
    res = empresas.cadastrar_por_certificado("ABC123", cfg, uf="ba")
    assert _empresa(cfg).uf == "BA" and res.avisos == []


def test_recadastro_atualiza(cfg, monkeypatch):
    _ambiente(monkeypatch, _cert(), {"razao_social": "X", "uf": "BA"})
    empresas.cadastrar_por_certificado("ABC123", cfg)
    _ambiente(monkeypatch, _cert(thumb="NOVO"), {"razao_social": "X", "uf": "BA"})
    res = empresas.cadastrar_por_certificado("NOVO", cfg)
    assert not res.nova and _empresa(cfg).thumbprint == "NOVO"


def test_aviso_de_vencimento(cfg, monkeypatch):
    _ambiente(monkeypatch, _cert(dias=10), {"razao_social": "X", "uf": "BA"})
    res = empresas.cadastrar_por_certificado("ABC123", cfg)
    assert any("vence" in a for a in res.avisos)


@pytest.mark.parametrize("cert, uf", [
    (_cert(dias=-1), None),                 # vencido
    (_cert(cnpj="12345678000199"), None),   # CNPJ com DV errado
    (_cert(), "ZZ"),                        # UF inválida
])
def test_recusas(cfg, monkeypatch, cert, uf):
    _ambiente(monkeypatch, cert, None)
    with pytest.raises(empresas.ErroCadastro):
        empresas.cadastrar_por_certificado("ABC123", cfg, uf=uf)
    assert _empresa(cfg) is None


def test_certificado_inexistente(cfg, monkeypatch):
    _ambiente(monkeypatch, _cert(), None)
    with pytest.raises(empresas.ErroCadastro):
        empresas.cadastrar_por_certificado("OUTRO", cfg)
