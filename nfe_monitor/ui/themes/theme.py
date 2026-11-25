from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Fontes:
    texto: str
    titulo: str
    mono: str


@dataclass(frozen=True, slots=True)
class Status:
    sucesso: str
    sucessoSoft: str
    info: str
    infoSoft: str
    alerta: str
    alertaSoft: str
    perigo: str
    perigoSoft: str


@dataclass(frozen=True, slots=True)
class Theme:
    id: str
    nome: str
    escuro: bool
    background: str   # fundo da janela
    rail: str         # barra lateral
    surface: str      # cartões
    surfaceAlt: str   # hover / linhas alternadas
    border: str
    accent: str
    accentSoft: str
    onAccent: str     # texto sobre o accent
    text: str
    muted: str
    radius: int
    fontes: Fontes
    status: Status

    def to_qml(self) -> dict[str, Any]:
        return asdict(self)
