from dataclasses import dataclass
from datetime import timedelta, timezone
from decimal import Decimal

# Bahia não usa horário de verão desde 2019. Offset fixo evita depender de tzdata no Windows.
FUSO = timezone(timedelta(hours=-3))


@dataclass(frozen=True)
class Resumo:
    chave: str
    emitente_cnpj: str
    emitente_nome: str
    data_emissao: str
    valor: Decimal
    situacao: str
    protocolo: str | None
