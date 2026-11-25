from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt

from nfe_monitor.ui.formatters import formatar_brl, formatar_data
from nfe_monitor.domain.nota import numero_da_nota, situacao_da

_TEXTO_SITUACAO = {"baixado": "XML baixado", "ciencia": "Ciência registrada", "pendente": "Pendente"}


def _iniciais(nome: str) -> str:
    partes = [p for p in nome.split() if p[:1].isalnum()]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


class NotasModel(QAbstractListModel):
    _NOMES = ["emitente", "iniciais", "numero", "data", "valor",
              "situacao", "situacaoTexto", "chave", "baixado"]
    ROLES = {Qt.UserRole + i + 1: n for i, n in enumerate(_NOMES)}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._notas: list[dict] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._notas)

    def roleNames(self) -> dict[int, QByteArray]:
        return {r: QByteArray(n.encode()) for r, n in self.ROLES.items()}

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        n = self._notas[index.row()]
        match self.ROLES.get(role):
            case "emitente": return n["emitente"] or "Emitente não informado"
            case "iniciais": return _iniciais(n["emitente"] or "")
            case "numero": return numero_da_nota(n["chave"])
            case "data": return formatar_data(n["data_emissao"])
            case "valor": return formatar_brl(n["valor"])
            case "situacao": return situacao_da(n)
            case "situacaoTexto": return _TEXTO_SITUACAO[situacao_da(n)]
            case "chave": return n["chave"]
            case "baixado": return bool(n["xml_baixado"])
        return None

    def carregar(self, notas: list[dict]) -> None:
        self.beginResetModel()
        self._notas = notas
        self.endResetModel()

    def nota(self, linha: int) -> dict | None:
        return self._notas[linha] if 0 <= linha < len(self._notas) else None
