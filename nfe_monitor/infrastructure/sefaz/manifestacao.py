import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from nfe_monitor.domain.resumo import FUSO
from nfe_monitor.infrastructure.paths import recurso
from nfe_monitor.infrastructure.sefaz import cliente
from nfe_monitor.infrastructure.sefaz.parametros import Config

__all__ = [
    "TP_EVENTO_CIENCIA", "COD_ORGAO_AN", "URL_EVENTO", "SOAP_ACTION_EVENTO",
    "CSTATS_CIENCIA_OK", "CSTAT_DUPLICIDADE", "ErroEvento", "enviar_ciencia",
]

TP_EVENTO_CIENCIA = "210210"
COD_ORGAO_AN = "91"  # Ambiente Nacional, usado nos eventos de manifestação
URL_EVENTO = {
    # Confirme as URLs no portal da NF-e antes de usar.
    1: "https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
    2: "https://hom.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
}
SOAP_ACTION_EVENTO = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4/nfeRecepcaoEventoNF"

CSTATS_CIENCIA_OK = {"135", "136"}  # 135 vinculado; 136 registrado sem vinculação
CSTAT_DUPLICIDADE = "573"           # evento já registrado: tratado como sucesso

_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ErroEvento(RuntimeError):
    """Falha de negócio na manifestação ou na obtenção do XML (mostrada ao usuário)."""


def _montar_evento(cnpj: str, chave: str, cfg: Config) -> str:
    agora = datetime.now(FUSO)
    id_evento = f"ID{TP_EVENTO_CIENCIA}{chave}01"  # ID + tpEvento + chave + nSeqEvento
    id_lote = agora.strftime("%y%m%d%H%M%S")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                 xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">
      <envEvento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
        <idLote>{id_lote}</idLote>
        <evento versao="1.00">
          <infEvento Id="{id_evento}">
            <cOrgao>{COD_ORGAO_AN}</cOrgao>
            <tpAmb>{cfg.tp_amb}</tpAmb>
            <CNPJ>{cnpj}</CNPJ>
            <chNFe>{chave}</chNFe>
            <dhEvento>{agora.isoformat(timespec="seconds")}</dhEvento>
            <tpEvento>{TP_EVENTO_CIENCIA}</tpEvento>
            <nSeqEvento>1</nSeqEvento>
            <verEvento>1.00</verEvento>
            <detEvento versao="1.00">
              <descEvento>Ciencia da Operacao</descEvento>
            </detEvento>
          </infEvento>
        </evento>
      </envEvento>
    </nfeDadosMsg>
  </soap12:Body>
</soap12:Envelope>"""


def _assinar(xml: str, thumbprint: str) -> str:
    with tempfile.TemporaryDirectory() as pasta:
        entrada = Path(pasta) / "evento.xml"
        saida = Path(pasta) / "evento_assinado.xml"
        entrada.write_text(xml, encoding="utf-8")

        r = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(recurso("scripts/assinar_evento.ps1")),
                "-Thumbprint", thumbprint,
                "-ArquivoEntrada", str(entrada),
                "-ArquivoSaida", str(saida),
            ],
            capture_output=True,
            timeout=60,
            creationflags=_SEM_JANELA,
        )
        if r.returncode != 0:
            erro = (r.stderr + r.stdout).decode("utf-8", errors="replace")
            raise ErroEvento(f"Falha ao assinar o evento:\n{erro.strip()}")

        # utf-8-sig remove o BOM que o .NET costuma gravar
        return saida.read_text(encoding="utf-8-sig")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _resultado_evento(corpo: str) -> tuple[str, str]:
    """Lê cStat e xMotivo do infEvento da resposta do serviço de eventos."""
    raiz = ET.fromstring(corpo)
    for el in raiz.iter():
        if _local(el.tag) != "infEvento":
            continue
        valores = {_local(f.tag): (f.text or "") for f in el}
        return valores.get("cStat", ""), valores.get("xMotivo", "")
    raise ErroEvento("Resposta do serviço de eventos sem infEvento")


def enviar_ciencia(chave: str, cnpj: str, cfg: Config) -> tuple[str, str]:
    """Monta, assina e envia a Ciência da Operação. Devolve (cStat, xMotivo)."""
    evento_cfg = replace(cfg, url=URL_EVENTO[cfg.tp_amb], soap_action=SOAP_ACTION_EVENTO)
    assinado = _assinar(_montar_evento(cnpj, chave, cfg), cfg.thumbprint)
    corpo = cliente.enviar_soap(assinado, evento_cfg)
    return _resultado_evento(corpo)
