from dataclasses import dataclass, field
from pathlib import Path

from nfe_monitor.infrastructure import preferencias
from nfe_monitor.infrastructure.paths import DB, recurso


@dataclass(frozen=True)
class Config:
    # Confirme a URL de produção no portal da NF-e antes de usar.
    url: str = "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
    soap_action: str = (
        "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"
    )
    tp_amb: int = 1       # 1 = produção, 2 = homologação
    uf_autor: str = "29"  # código da UF do autor (Bahia)
    banco: Path = DB
    script_ps: Path = recurso("scripts/envia_soap.ps1")
    timeout_s: int = 120
    # Lido do config.json a cada Config(): sempre reflete a escolha atual
    thumbprint: str = field(default_factory=lambda: preferencias.carregar().thumbprint)
