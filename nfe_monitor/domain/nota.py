def numero_da_nota(chave: str | None) -> str:
    """Extrai o número da NF-e (posições 26 a 34 da chave de 44 dígitos)."""
    chave = str(chave or "")
    if len(chave) == 44 and chave.isdigit():
        return chave[25:34].lstrip("0") or "0"
    return "—"


def situacao_da(nota: dict) -> str:
    if nota["xml_baixado"]:
        return "baixado"
    if nota["manifestacao"] == "ciencia":
        return "ciencia"
    return "pendente"
