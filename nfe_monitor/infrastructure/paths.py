import os
import sys
from pathlib import Path


def pasta_dados() -> Path:
    """Banco e XMLs ficam no perfil do usuário, que é gravável."""
    base = Path(os.environ.get("APPDATA", Path.home())) / "NFeMonitor"
    base.mkdir(parents=True, exist_ok=True)
    return base


def recurso(relativo: str) -> Path:
    """Funciona tanto no código-fonte quanto no executável do PyInstaller.

    paths.py -> infrastructure -> nfe_monitor -> raiz do projeto (parents[2]).
    """
    raiz = getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])
    return Path(raiz) / relativo


PASTA_DADOS = pasta_dados()
DB = PASTA_DADOS / "nfe.db"
# A subpasta de cada empresa (<CNPJ>) é criada por quem salva o XML.
PASTA_XML = PASTA_DADOS / "xml"
