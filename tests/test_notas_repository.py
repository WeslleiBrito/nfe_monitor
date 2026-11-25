import pytest

from nfe_monitor.infrastructure.database import notas_repository as repo
from nfe_monitor.infrastructure.database.conexao import conectar

CNPJ = "12345678000199"


@pytest.fixture
def con(tmp_path):
    c = conectar(tmp_path / "teste.db")
    yield c
    c.close()


def _empresa(**kw):
    dados = dict(cnpj=CNPJ, razao_social="EMPRESA TESTE", uf="BA", thumbprint="ABC")
    dados.update(kw)
    return repo.Empresa(**dados)


def test_cadastro_cria_nsu_zerado(con):
    repo.salvar_empresa(con, _empresa())
    assert repo.obter_empresa(con, CNPJ).c_uf_autor == "29"
    assert repo.ler_ult_nsu(con, CNPJ) == repo.NSU_ZERO


def test_salvar_nsu_preserva_max(con):
    repo.salvar_empresa(con, _empresa())
    repo.salvar_ult_nsu(con, CNPJ, "10", "500")
    repo.salvar_ult_nsu(con, CNPJ, "20")
    row = con.execute("SELECT ult_nsu, max_nsu FROM controle_nsu").fetchone()
    assert row == ("000000000000020", "000000000000500")


def test_bloqueio_656(con):
    repo.salvar_empresa(con, _empresa())
    repo.bloquear_empresa(con, CNPJ)
    assert repo.bloqueada_ate(con, CNPJ) is not None
    assert repo.empresas_prontas(con) == []


def test_bloqueio_expirado_libera(con):
    repo.salvar_empresa(con, _empresa())
    repo.bloquear_empresa(con, CNPJ, minutos=-1)
    assert [e.cnpj for e in repo.empresas_prontas(con)] == [CNPJ]


def test_cadastro_incompleto_nao_fica_pronto(con):
    repo.salvar_empresa(con, _empresa(uf=None, thumbprint=None))
    assert repo.empresas_prontas(con) == []


def test_validacoes(con):
    with pytest.raises(ValueError):
        repo.salvar_empresa(con, _empresa(uf="ZZ"))
    with pytest.raises(ValueError):
        repo.salvar_empresa(con, _empresa(cnpj="123"))
