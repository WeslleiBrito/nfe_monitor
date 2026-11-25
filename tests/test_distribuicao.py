import base64
import gzip
from decimal import Decimal

from nfe_monitor.infrastructure.database.conexao import conectar
from nfe_monitor.infrastructure.database.notas_repository import inserir_resumo
from nfe_monitor.infrastructure.sefaz.distribuicao import ler_lote, ler_resumo

RESUMO_XML = """<resNFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <chNFe>29261117471387000167550010013121891208125550</chNFe>
  <CNPJ>17471387000167</CNPJ>
  <xNome>FORNECEDOR EXEMPLO LTDA</xNome>
  <dhEmi>2026-11-12T03:29:00-03:00</dhEmi>
  <vNF>4124.82</vNF>
  <cSitNFe>1</cSitNFe>
  <nProt>129261609811504</nProt>
</resNFe>"""


def _doc_zip(xml: str) -> str:
    return base64.b64encode(gzip.compress(xml.encode("utf-8"))).decode("ascii")


def _resposta(cstat: str, ult: str, maximo: str, docs: list[tuple[str, str, str]]) -> str:
    lote = "".join(
        f'<docZip NSU="{nsu}" schema="{schema}">{_doc_zip(xml)}</docZip>'
        for nsu, schema, xml in docs
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <nfeDistDFeInteresseResponse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
      <nfeDistDFeInteresseResult>
        <retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>1</tpAmb><cStat>{cstat}</cStat><xMotivo>Teste</xMotivo>
          <ultNSU>{ult}</ultNSU><maxNSU>{maximo}</maxNSU>
          <loteDistDFeInt>{lote}</loteDistDFeInt>
        </retDistDFeInt>
      </nfeDistDFeInteresseResult>
    </nfeDistDFeInteresseResponse>
  </soap:Body>
</soap:Envelope>"""


def test_ler_lote_descompacta_resumo():
    corpo = _resposta("138", "000000000000001", "000000000000001",
                      [("000000000000001", "resNFe_v1.01.xsd", RESUMO_XML)])
    lote = ler_lote(corpo)

    assert lote.cstat == "138"
    assert lote.docs[0].tipo == "resumo"


def test_ler_lote_sem_documentos():
    corpo = _resposta("137", "000000000000000", "000000000000000", [])
    lote = ler_lote(corpo)

    assert lote.cstat == "137"
    assert lote.docs == []


def test_ler_resumo_campos():
    r = ler_resumo(RESUMO_XML)

    assert r.chave == "29261117471387000167550010013121891208125550"
    assert r.valor == Decimal("4124.82")
    assert r.situacao == "1"


def test_inserir_resumo_nao_duplica(tmp_path):
    con = conectar(tmp_path / "teste.db")
    try:
        r = ler_resumo(RESUMO_XML)
        assert inserir_resumo(con, r) is True
        assert inserir_resumo(con, r) is False
        assert con.execute("SELECT COUNT(*) FROM nfe").fetchone()[0] == 1
    finally:
        con.close()
