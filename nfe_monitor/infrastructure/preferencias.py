import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from nfe_monitor.infrastructure.paths import PASTA_DADOS

ARQUIVO: Path = PASTA_DADOS / "config.json"


@dataclass
class Preferencias:
    thumbprint: str = ""             # certificado padrão (usado se a empresa não tiver o seu)
    pasta_download: str = ""         # vazio = perguntar a cada download
    ultima_sincronizacao: str = ""   # ISO com fuso de Brasília
    empresa_filtro: str = ""         # CNPJ escolhido na tela; vazio = todas as empresas


def carregar() -> Preferencias:
    if not ARQUIVO.exists():
        return Preferencias()
    try:
        dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Preferencias()
    if not isinstance(dados, dict):
        return Preferencias()
    campos = Preferencias.__dataclass_fields__
    return Preferencias(**{
        k: v for k, v in dados.items() if k in campos and isinstance(v, str)
    })


def salvar(p: Preferencias) -> None:
    """Grava em arquivo temporário e troca de uma vez: nunca deixa o JSON pela metade."""
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    temporario = ARQUIVO.with_suffix(".json.tmp")
    temporario.write_text(json.dumps(asdict(p), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, ARQUIVO)
