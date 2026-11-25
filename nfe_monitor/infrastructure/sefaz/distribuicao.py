import base64
import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from nfe_monitor.domain.resumo import FUSO, Resumo

__all__ = [
    "NS", "CSTAT_ESPERA", "CSTAT_SEM_DOCS", "CSTAT_COM_DOCS", "FUSO",
    "Documento", "Lote", "Resumo",
    "normalizar_data", "ler_lote", "ler_resumo", "ler_completo",
]

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

CSTAT_ESPERA = "656"      # consumo indevido: aguardar antes de nova consulta
CSTAT_SEM_DOCS = "137"    # nenhum documento localizado
CSTAT_COM_DOCS = "138"    # documentos localizados


def normalizar_data(texto: str | None) -> str:
    """Converte a data para 'AAAA-MM-DD HH:MM:SS' no horário de Brasília (ordenável como texto)."""
    if not texto:
        return ""
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        return texto
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=FUSO)
    return dt.astimezone(FUSO).strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class Documento:
    nsu: str
    schema: str
    xml: str

    @property
    def tipo(self) -> str:
        if self.schema.startswith("resNFe"):
            return "resumo"
        if self.schema.startswith("procNFe"):
            return "completo"
        return "outro"


@dataclass(frozen=True)
class Lote:
    cstat: str
    motivo: str
    ult_nsu: str | None
    max_nsu: str | None
    docs: list[Documento] = field(default_factory=list)


def _encontrar_ret(raiz: ET.Element) -> ET.Element | None:
    """Localiza retDistDFeInt na raiz ou em qualquer nível abaixo dela."""
    alvo = f"{{{NS['nfe']}}}retDistDFeInt"
    return next((e for e in raiz.iter() if e.tag == alvo), None)


def ler_lote(corpo: str, exigir_nsu: bool = True) -> Lote:
    ret = _encontrar_ret(ET.fromstring(corpo))
    if ret is None:
        raise ValueError("Resposta sem retDistDFeInt")

    cstat = ret.findtext("nfe:cStat", namespaces=NS)
    motivo = ret.findtext("nfe:xMotivo", namespaces=NS)
    ult_nsu = ret.findtext("nfe:ultNSU", namespaces=NS)
    max_nsu = ret.findtext("nfe:maxNSU", namespaces=NS)

    if not cstat:
        raise ValueError("Resposta da SEFAZ sem cStat")
    if exigir_nsu and cstat in (CSTAT_SEM_DOCS, CSTAT_COM_DOCS) and not (ult_nsu and max_nsu):
        raise ValueError(f"Resposta cStat {cstat} sem ultNSU ou maxNSU")

    docs = []
    for d in ret.findall("nfe:loteDistDFeInt/nfe:docZip", NS):
        conteudo = gzip.decompress(base64.b64decode(d.text or "")).decode("utf-8")
        docs.append(Documento(nsu=d.get("NSU", ""), schema=d.get("schema", ""), xml=conteudo))

    return Lote(cstat=cstat, motivo=motivo or "", ult_nsu=ult_nsu, max_nsu=max_nsu, docs=docs)


def ler_resumo(xml: str) -> Resumo:
    """resNFe: dados mínimos. Situação é cSitNFe (1 autorizada, 2 cancelada, 3 denegada)."""
    r = ET.fromstring(xml)
    return Resumo(
        chave=r.findtext("nfe:chNFe", namespaces=NS),
        emitente_cnpj=r.findtext("nfe:CNPJ", namespaces=NS) or "",
        emitente_nome=r.findtext("nfe:xNome", namespaces=NS) or "",
        data_emissao=normalizar_data(r.findtext("nfe:dhEmi", namespaces=NS)),
        valor=Decimal(r.findtext("nfe:vNF", namespaces=NS)),
        situacao=r.findtext("nfe:cSitNFe", namespaces=NS) or "",
        protocolo=r.findtext("nfe:nProt", namespaces=NS),
    )


def ler_completo(xml: str) -> Resumo:
    """procNFe: XML completo. Situação é o cStat do protocolo (100 autorizada, 101 cancelada)."""
    raiz = ET.fromstring(xml)
    inf = raiz.find(".//nfe:infNFe", NS)
    if inf is None:
        raise ValueError("procNFe sem infNFe")

    emit = inf.find("nfe:emit", NS)
    prot = raiz.find(".//nfe:protNFe/nfe:infProt", NS)

    return Resumo(
        chave=inf.get("Id", "")[3:],  # remove o prefixo "NFe"
        emitente_cnpj=(emit.findtext("nfe:CNPJ", namespaces=NS)
                       or emit.findtext("nfe:CPF", namespaces=NS) or ""),
        emitente_nome=emit.findtext("nfe:xNome", namespaces=NS) or "",
        data_emissao=normalizar_data(
            inf.findtext("nfe:ide/nfe:dhEmi", namespaces=NS)
            or inf.findtext("nfe:ide/nfe:dEmi", namespaces=NS)
        ),
        valor=Decimal(inf.findtext("nfe:total/nfe:ICMSTot/nfe:vNF", namespaces=NS)),
        situacao=(prot.findtext("nfe:cStat", namespaces=NS) or "") if prot is not None else "",
        protocolo=prot.findtext("nfe:nProt", namespaces=NS) if prot is not None else None,
    )
