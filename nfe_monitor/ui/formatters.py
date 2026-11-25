from datetime import datetime
from decimal import Decimal


def formatar_brl(valor) -> str:
    if valor in (None, ""):
        return ""
    texto = f"{Decimal(str(valor)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def formatar_data(texto: str | None) -> str:
    if not texto:
        return ""
    try:
        return datetime.strptime(texto, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return texto
