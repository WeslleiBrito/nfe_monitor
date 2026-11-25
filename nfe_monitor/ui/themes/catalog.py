from nfe_monitor.ui.themes.theme import Fontes, Status, Theme

SYSTEM_ID = "system"

_FONTES = Fontes(texto="Segoe UI", titulo="Segoe UI Variable Display", mono="Cascadia Mono")

NEBLINA = Theme(
    id="neblina", nome="Neblina (claro)", escuro=False,
    background="#EEF0F4", rail="#111827", surface="#FFFFFF", surfaceAlt="#F6F7FA",
    border="#E3E6EC", accent="#5B5BD6", accentSoft="#ECECFB", onAccent="#FFFFFF",
    text="#151821", muted="#6B7280", radius=14, fontes=_FONTES,
    status=Status(sucesso="#12A150", sucessoSoft="#E3F6EA", info="#2F6FEB", infoSoft="#E6EEFD",
                  alerta="#C77700", alertaSoft="#FDF1DC", perigo="#D93838", perigoSoft="#FCE6E6"),
)

GRAFITE = Theme(
    id="grafite", nome="Grafite (escuro)", escuro=True,
    background="#0D0F14", rail="#080A0E", surface="#151820", surfaceAlt="#1B1F29",
    border="#242936", accent="#8B8BFF", accentSoft="#23234A", onAccent="#0D0F14",
    text="#ECEEF3", muted="#8A93A6", radius=14, fontes=_FONTES,
    status=Status(sucesso="#3DDC84", sucessoSoft="#12301F", info="#6EA8FF", infoSoft="#16264A",
                  alerta="#FFB547", alertaSoft="#3A2A10", perigo="#FF6B6B", perigoSoft="#3A1616"),
)

ESMERALDA = Theme(
    id="esmeralda", nome="Esmeralda", escuro=True,
    background="#07130F", rail="#040C09", surface="#0D1F19", surfaceAlt="#122920",
    border="#1A3A2E", accent="#34E0A1", accentSoft="#0F3A2B", onAccent="#04140E",
    text="#E3F7EF", muted="#7FA899", radius=18, fontes=_FONTES,
    status=Status(sucesso="#34E0A1", sucessoSoft="#0F3A2B", info="#5CC8FF", infoSoft="#0E2E40",
                  alerta="#F5C451", alertaSoft="#3A2F10", perigo="#FF7A7A", perigoSoft="#3D1717"),
)

AMBAR = Theme(
    id="ambar", nome="Âmbar", escuro=False,
    background="#FBF6EE", rail="#2A1A0A", surface="#FFFFFF", surfaceAlt="#FCF3E6",
    border="#EFE2CF", accent="#E8730C", accentSoft="#FDEBD9", onAccent="#FFFFFF",
    text="#2A1A0A", muted="#8C755C", radius=10, fontes=_FONTES,
    status=Status(sucesso="#2E9E5B", sucessoSoft="#E4F4EA", info="#3B6FD9", infoSoft="#E7EEFB",
                  alerta="#C76A00", alertaSoft="#FCEBD3", perigo="#CF3A3A", perigoSoft="#FAE3E3"),
)

THEMES: dict[str, Theme] = {t.id: t for t in (NEBLINA, GRAFITE, ESMERALDA, AMBAR)}


def resolve_theme(theme_id: str, sistema_escuro: bool) -> Theme:
    if theme_id == SYSTEM_ID or theme_id not in THEMES:
        return GRAFITE if sistema_escuro else NEBLINA
    return THEMES[theme_id]
