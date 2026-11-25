from dataclasses import dataclass
from datetime import datetime

AVISO_DIAS = 30  # a partir de quantos dias para vencer o app começa a avisar

__all__ = ["AVISO_DIAS", "Certificado"]


@dataclass(frozen=True)
class Certificado:
    thumbprint: str
    titular: str
    validade: datetime

    @property
    def dias_restantes(self) -> int:
        agora = datetime.now(self.validade.tzinfo)
        return (self.validade.date() - agora.date()).days

    @property
    def vencido(self) -> bool:
        return self.dias_restantes < 0

    @property
    def vencendo(self) -> bool:
        return 0 <= self.dias_restantes <= AVISO_DIAS

    @property
    def situacao(self) -> str:
        # usado em: "<titular> · <situacao> até dd/mm/aaaa"
        if self.vencido:
            return "vencido"
        if self.vencendo:
            return "vence"
        return "válido"

    @property
    def rotulo(self) -> str:
        return f"{self.titular} — {self.situacao} até {self.validade:%d/%m/%Y}"
