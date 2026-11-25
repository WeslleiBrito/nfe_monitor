import json
from urllib.error import URLError
from urllib.request import Request, urlopen

__all__ = ["URL", "consultar_cnpj"]

URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"


def consultar_cnpj(cnpj: str, timeout: int = 10) -> dict | None:
    """Devolve {'razao_social', 'uf'} ou None se a API falhar (o cadastro segue sem ela)."""
    req = Request(URL.format(cnpj=cnpj), headers={"User-Agent": "nfe-monitor"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    return {
        "razao_social": (dados.get("razao_social") or "").strip() or None,
        "uf": (dados.get("uf") or "").strip().upper() or None,
    }
