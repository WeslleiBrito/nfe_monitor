from datetime import datetime, timedelta

from nfe_monitor.domain.resumo import FUSO
from nfe_monitor.infrastructure import preferencias

INTERVALO = timedelta(hours=1)


def ultima_sincronizacao() -> datetime | None:
    texto = preferencias.carregar().ultima_sincronizacao
    return datetime.fromisoformat(texto) if texto else None


def segundos_restantes() -> int:
    ultima = ultima_sincronizacao()
    if ultima is None:
        return 0
    restante = (ultima + INTERVALO) - datetime.now(FUSO)
    return max(0, int(restante.total_seconds()))


def registrar_disparo() -> None:
    """Grava o momento do clique. Vale também para sincronizações que falharam,
    porque a SEFAZ conta cada consulta, mesmo as que dão erro."""
    p = preferencias.carregar()
    p.ultima_sincronizacao = datetime.now(FUSO).isoformat(timespec="seconds")
    preferencias.salvar(p)
