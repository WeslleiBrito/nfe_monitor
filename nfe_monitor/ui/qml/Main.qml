import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: root
    width: 1440
    height: 860
    minimumWidth: 1180
    minimumHeight: 680
    visible: true
    visibility: Window.Maximized
    title: "NF-e Monitor"
    color: Theme.t.background

    readonly property var corSituacao: ({
        baixado: [Theme.t.status.sucesso, Theme.t.status.sucessoSoft],
        ciencia: [Theme.t.status.info, Theme.t.status.infoSoft],
        pendente: [Theme.t.status.alerta, Theme.t.status.alertaSoft]
    })
    readonly property var paletaAvatar: ["#6366F1", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#EC4899", "#8B5CF6", "#14B8A6"]

    function corAvatar(nome) {
        let h = 0
        for (let i = 0; i < nome.length; i++) h = (h * 31 + nome.charCodeAt(i)) >>> 0
        return paletaAvatar[h % paletaAvatar.length]
    }
    function paraIso(texto) {
        const d = texto.replace(/\D/g, "")
        return d.length === 8 ? d.slice(4) + "-" + d.slice(2, 4) + "-" + d.slice(0, 2) : ""
    }
    function mascaraData(campo) {
        const d = campo.text.replace(/\D/g, "").slice(0, 8)
        let f = d
        if (d.length > 4) f = d.slice(0, 2) + "/" + d.slice(2, 4) + "/" + d.slice(4)
        else if (d.length > 2) f = d.slice(0, 2) + "/" + d.slice(2)
        if (f !== campo.text) campo.text = f
    }
    function filtrar() {
        viewModel.aplicarFiltros(buscaInput.text, paraIso(deInput.text), paraIso(ateInput.text))
    }
    function toast(msg) { toastBox.texto = msg; toastBox.opacity = 1; toastTimer.restart() }

    onClosing: (close) => {
        if (!viewModel.podeFechar() || config.ocupado) {
            close.accepted = false
            toast("Há uma operação em andamento. Aguarde para fechar.")
        }
    }

    // =================== Componentes ===================
    component Txt: Text {
        property bool fraco: false
        color: fraco ? Theme.t.muted : Theme.t.text
        font.family: Theme.t.fontes.texto
        font.pixelSize: 14
        elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
    }

    component Btn: Button {
        id: b
        property string variante: "primario"   // primario | suave | fantasma
        property color corBase: variante === "primario" ? Theme.t.accent
                              : variante === "suave" ? Theme.t.accentSoft : "transparent"
        property color corTexto: variante === "primario" ? Theme.t.onAccent : Theme.t.accent
        hoverEnabled: true
        padding: 0
        implicitHeight: 40
        implicitWidth: Math.max(96, rot.implicitWidth + 32)
        contentItem: Text {
            id: rot
            text: b.text
            color: b.corTexto
            font.family: Theme.t.fontes.texto
            font.pixelSize: 14
            font.weight: 600
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: Theme.t.radius - 4
            color: b.down ? Qt.darker(b.corBase, 1.15)
                 : b.hovered ? (b.variante === "fantasma" ? Theme.t.accentSoft : Qt.lighter(b.corBase, 1.08))
                 : b.corBase
            border.color: b.variante === "fantasma" ? Theme.t.border : "transparent"
            Behavior on color { ColorAnimation { duration: 120 } }
        }
        opacity: enabled ? 1 : 0.4
        HoverHandler { cursorShape: Qt.PointingHandCursor }
    }

    component Campo: TextField {
        id: c
        property string icone: ""
        color: Theme.t.text
        placeholderTextColor: Theme.t.muted
        font.family: Theme.t.fontes.texto
        font.pixelSize: 14
        leftPadding: icone ? 38 : 14
        implicitHeight: 42
        selectByMouse: true
        background: Rectangle {
            radius: Theme.t.radius - 4
            color: Theme.t.surfaceAlt
            border.width: c.activeFocus ? 2 : 1
            border.color: c.activeFocus ? Theme.t.accent : Theme.t.border
            Text {
                visible: c.icone.length > 0
                text: c.icone
                anchors.left: parent.left
                anchors.leftMargin: 13
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.t.muted
                font.pixelSize: 15
            }
        }
    }

    component Combo: ComboBox {
        id: cb
        textRole: "nome"
        valueRole: "id"
        implicitHeight: 42
        contentItem: Txt { leftPadding: 14; text: cb.displayText }
        background: Rectangle {
            radius: Theme.t.radius - 4
            color: Theme.t.surfaceAlt
            border.color: cb.activeFocus ? Theme.t.accent : Theme.t.border
        }
        delegate: ItemDelegate {
            required property var modelData
            required property int index
            width: cb.width
            contentItem: Txt { text: modelData.nome }
            background: Rectangle { color: cb.highlightedIndex === index ? Theme.t.accentSoft : Theme.t.surface }
        }
        popup.background: Rectangle { color: Theme.t.surface; border.color: Theme.t.border; radius: 10 }
    }

    component Cartao: Rectangle {
        color: Theme.t.surface
        radius: Theme.t.radius
        border.color: Theme.t.border
    }

    component Pilula: Rectangle {
        id: pil
        property string chave: "pendente"
        property string texto: ""
        implicitWidth: lbl.implicitWidth + 30
        implicitHeight: 26
        radius: 13
        color: root.corSituacao[pil.chave][1]
        Row {
            anchors.centerIn: parent
            spacing: 6
            Rectangle { width: 7; height: 7; radius: 4; anchors.verticalCenter: parent.verticalCenter; color: root.corSituacao[pil.chave][0] }
            Text { id: lbl; text: pil.texto; color: root.corSituacao[pil.chave][0]; font.family: Theme.t.fontes.texto; font.pixelSize: 12; font.weight: 700 }
        }
    }

    component RailBtn: AbstractButton {
        id: rb
        property string icone: ""
        property bool ativo: false
        property string dica: ""
        implicitWidth: 48
        implicitHeight: 48
        hoverEnabled: true
        contentItem: Text {
            text: rb.icone
            color: rb.ativo ? "#FFFFFF" : "#9AA3B5"
            font.pixelSize: 20
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 14
            color: rb.ativo ? Theme.t.accent : rb.hovered ? Qt.rgba(1, 1, 1, 0.08) : "transparent"
        }
        ToolTip.visible: hovered && dica.length > 0
        ToolTip.text: dica
        HoverHandler { cursorShape: Qt.PointingHandCursor }
    }

    component Metrica: Cartao {
        id: met
        property string rotulo
        property string valor
        property string icone
        property color cor: Theme.t.accent
        property real progresso: -1
        Layout.fillWidth: true
        implicitHeight: 104
        Rectangle { width: 4; height: parent.height - 32; radius: 2; color: met.cor; anchors.left: parent.left; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter }
        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: 32
            anchors.rightMargin: 20
            anchors.topMargin: 16
            anchors.bottomMargin: 16
            spacing: 4
            RowLayout {
                Txt { text: met.rotulo.toUpperCase(); fraco: true; font.pixelSize: 11; font.weight: 700; font.letterSpacing: 1.2; Layout.fillWidth: true }
                Txt { text: met.icone; color: met.cor; font.pixelSize: 18 }
            }
            Txt { text: met.valor; font.family: Theme.t.fontes.titulo; font.pixelSize: 28; font.weight: 700 }
            Rectangle {
                visible: met.progresso >= 0
                Layout.fillWidth: true
                height: 4
                radius: 2
                color: Theme.t.surfaceAlt
                Rectangle {
                    width: parent.width * Math.max(0, Math.min(1, met.progresso)); height: parent.height; radius: 2; color: met.cor
                    Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                }
            }
        }
    }

    // =================== Diálogos ===================
    FolderDialog {
        id: pastaDialog
        property int linha: -1
        title: "Pasta para salvar o XML"
        onAccepted: viewModel.continuarComPasta(linha, selectedFolder.toString())
    }

    FolderDialog {
        id: pastaConfigDialog
        title: "Pasta padrão dos XMLs"
        onAccepted: pastaConfig.text = config.caminhoDe(selectedFolder.toString())
    }

    Dialog {
        id: cienciaDialog
        property int linha: -1
        property string pasta: ""
        modal: true
        anchors.centerIn: parent
        width: 460
        padding: 28
        background: Cartao { border.color: Theme.t.status.alerta }
        ColumnLayout {
            anchors.fill: parent
            spacing: 14
            Txt { text: "⚠  Registrar ciência da operação"; font.pixelSize: 18; font.weight: 700 }
            Txt {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                fraco: true
                text: "Para baixar este XML é preciso registrar a ciência na SEFAZ. Essa manifestação é <b>definitiva</b> e não pode ser desfeita."
                textFormat: Text.StyledText
            }
            RowLayout {
                Layout.topMargin: 8
                Item { Layout.fillWidth: true }
                Btn { text: "Cancelar"; variante: "fantasma"; onClicked: cienciaDialog.close() }
                Btn { text: "Registrar e baixar"; onClicked: { cienciaDialog.close(); viewModel.confirmarCiencia(cienciaDialog.linha, cienciaDialog.pasta) } }
            }
        }
    }

    Dialog {
        id: erroDialog
        property string titulo: ""
        property string mensagem: ""
        modal: true
        anchors.centerIn: parent
        width: 480
        padding: 28
        background: Cartao { border.color: Theme.t.status.perigo }
        ColumnLayout {
            anchors.fill: parent
            spacing: 14
            Txt { text: "✕  " + erroDialog.titulo; color: Theme.t.status.perigo; font.pixelSize: 18; font.weight: 700 }
            Txt { Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; text: erroDialog.mensagem }
            RowLayout { Item { Layout.fillWidth: true } Btn { text: "Entendi"; onClicked: erroDialog.close() } }
        }
    }

    Connections {
        target: viewModel
        function onSolicitarPasta(linha) { pastaDialog.linha = linha; pastaDialog.open() }
        function onSolicitarCiencia(linha, pasta) { cienciaDialog.linha = linha; cienciaDialog.pasta = pasta; cienciaDialog.open() }
        function onNotificacao(msg) { root.toast(msg) }
        function onErro(titulo, msg) { erroDialog.titulo = titulo; erroDialog.mensagem = msg; erroDialog.open() }
        function onEmpresasChanged() { empresaCombo.currentIndex = viewModel.empresaIndice }
    }

    // ---------- Configurações ----------
    Dialog {
        id: configDialog
        modal: true
        anchors.centerIn: parent
        width: 680
        padding: 28
        onAboutToShow: {
            config.carregar()
            certCombo.currentIndex = certCombo.indexOfValue(config.thumbprint)
            pastaConfig.text = config.pasta
            temaCombo.currentIndex = temaCombo.indexOfValue(Theme.selecionado)
            configErro.text = ""
            configAviso.text = ""
            ufCampo.clear()
        }
        background: Cartao {}

        Connections {
            target: config
            function onErro(msg) { configAviso.text = ""; configErro.text = msg }
            function onCadastrado(msg) {
                configErro.text = ""
                configAviso.text = msg
                root.toast("✓ Empresa cadastrada")
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 18

            Txt { text: "Configurações"; font.family: Theme.t.fontes.titulo; font.pixelSize: 22; font.weight: 700 }

            // Certificado
            ColumnLayout {
                spacing: 6
                Layout.fillWidth: true
                Txt { text: "CERTIFICADO DIGITAL"; fraco: true; font.pixelSize: 11; font.weight: 700; font.letterSpacing: 1.2 }
                RowLayout {
                    Layout.fillWidth: true
                    Combo { id: certCombo; Layout.fillWidth: true; model: config.certificados }
                    Btn { text: "↻"; variante: "fantasma"; implicitWidth: 42; enabled: !config.ocupado; onClicked: { config.carregar(); certCombo.currentIndex = certCombo.indexOfValue(config.thumbprint) } }
                }
                Txt {
                    readonly property var c: certCombo.currentIndex >= 0 ? config.certificados[certCombo.currentIndex] : null
                    text: c ? "CNPJ " + c.cnpj + " · Validade: " + c.validade + " · " + c.situacao
                            : (config.certificados.length === 0 ? "Nenhum certificado encontrado no Windows." : "Selecione um certificado.")
                    color: c && c.alerta ? Theme.t.status.alerta : Theme.t.muted
                    font.pixelSize: 12
                }
            }

            // Empresas
            ColumnLayout {
                spacing: 6
                Layout.fillWidth: true
                Txt { text: "EMPRESAS MONITORADAS"; fraco: true; font.pixelSize: 11; font.weight: 700; font.letterSpacing: 1.2 }

                Repeater {
                    model: config.empresas
                    Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 46
                        radius: Theme.t.radius - 4
                        color: Theme.t.surfaceAlt
                        border.color: Theme.t.border
                        opacity: modelData.ativo ? 1 : 0.5
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 14
                            anchors.rightMargin: 10
                            spacing: 12
                            Txt { text: modelData.nome; Layout.fillWidth: true; font.weight: 600 }
                            Txt { text: modelData.cnpj; fraco: true; font.family: Theme.t.fontes.mono; font.pixelSize: 12 }
                            Txt { text: modelData.uf; fraco: true; font.weight: 700; Layout.preferredWidth: 26 }
                            Pilula {
                                chave: modelData.completa ? "baixado" : "pendente"
                                texto: !modelData.ativo ? "Inativa" : modelData.completa ? "Pronta" : "Incompleta"
                            }
                        }
                    }
                }
                Txt { visible: config.empresas.length === 0; text: "Nenhuma empresa cadastrada."; fraco: true; font.pixelSize: 12 }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    Campo {
                        id: ufCampo
                        Layout.preferredWidth: 110
                        placeholderText: "UF (auto)"
                        maximumLength: 2
                        font.capitalization: Font.AllUppercase
                        ToolTip.visible: hovered
                        ToolTip.text: "Deixe vazio para buscar na BrasilAPI"
                    }
                    Btn {
                        Layout.fillWidth: true
                        variante: "suave"
                        text: config.ocupado ? "Cadastrando…" : "＋  Cadastrar empresa do certificado selecionado"
                        enabled: !config.ocupado && certCombo.currentIndex >= 0
                        onClicked: {
                            configErro.text = ""
                            configAviso.text = ""
                            config.cadastrar(certCombo.currentValue || "", ufCampo.text)
                        }
                    }
                }
                Txt {
                    id: configAviso
                    visible: text.length > 0
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    font.pixelSize: 13
                    color: text.indexOf("⚠") >= 0 ? Theme.t.status.alerta : Theme.t.status.sucesso
                }
            }

            // Pasta
            ColumnLayout {
                spacing: 6
                Layout.fillWidth: true
                Txt { text: "PASTA DOS XMLS"; fraco: true; font.pixelSize: 11; font.weight: 700; font.letterSpacing: 1.2 }
                RowLayout {
                    Layout.fillWidth: true
                    Campo { id: pastaConfig; Layout.fillWidth: true; readOnly: true; icone: "📁"; placeholderText: "Perguntar a cada download" }
                    Btn { text: "Escolher"; variante: "suave"; onClicked: pastaConfigDialog.open() }
                    Btn { text: "Limpar"; variante: "fantasma"; enabled: pastaConfig.text.length > 0; onClicked: pastaConfig.clear() }
                }
            }

            // Aparência
            ColumnLayout {
                spacing: 6
                Layout.fillWidth: true
                Txt { text: "APARÊNCIA"; fraco: true; font.pixelSize: 11; font.weight: 700; font.letterSpacing: 1.2 }
                Combo { id: temaCombo; Layout.fillWidth: true; model: Theme.opcoes; onActivated: Theme.selecionar(currentValue) }
            }

            Txt { id: configErro; visible: text.length > 0; color: Theme.t.status.perigo; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Btn { text: "Cancelar"; variante: "fantasma"; onClicked: configDialog.close() }
                Btn {
                    text: "Salvar"
                    enabled: !config.ocupado
                    onClicked: if (config.salvar(certCombo.currentValue || "", pastaConfig.text)) {
                        viewModel.atualizarCertificado()
                        configDialog.close()
                        root.toast("✓ Configurações salvas")
                    }
                }
            }
        }
    }

    // =================== Layout ===================
    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ---------- Barra lateral ----------
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 76
            color: Theme.t.rail

            ColumnLayout {
                anchors.fill: parent
                anchors.topMargin: 18
                anchors.bottomMargin: 18
                spacing: 10

                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    width: 44; height: 44; radius: 14
                    gradient: Gradient {
                        GradientStop { position: 0; color: Theme.t.accent }
                        GradientStop { position: 1; color: Qt.darker(Theme.t.accent, 1.4) }
                    }
                    Text { anchors.centerIn: parent; text: "NF"; color: "white"; font.pixelSize: 16; font.weight: 800; font.family: Theme.t.fontes.titulo }
                }
                Item { Layout.preferredHeight: 14 }
                RailBtn { Layout.alignment: Qt.AlignHCenter; icone: "▤"; ativo: true; dica: "Notas recebidas" }
                Item { Layout.fillHeight: true }
                RailBtn { Layout.alignment: Qt.AlignHCenter; icone: Theme.t.escuro ? "☀" : "☾"; dica: "Alternar tema"; onClicked: Theme.alternar() }
                RailBtn { Layout.alignment: Qt.AlignHCenter; icone: "⚙"; dica: "Configurações"; onClicked: configDialog.open() }
            }
        }

        // ---------- Conteúdo ----------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 28
            spacing: 20

            // Cabeçalho
            RowLayout {
                Layout.fillWidth: true
                spacing: 16
                ColumnLayout {
                    spacing: 6
                    Txt { text: "Notas recebidas"; font.family: Theme.t.fontes.titulo; font.pixelSize: 30; font.weight: 700 }

                    // Uma empresa: só o CNPJ · Várias: seletor de empresa
                    Txt {
                        visible: !viewModel.multiEmpresa
                        text: "CNPJ " + viewModel.cnpj + "  ·  " + viewModel.status
                        fraco: true
                    }
                    RowLayout {
                        visible: viewModel.multiEmpresa
                        spacing: 12
                        Combo {
                            id: empresaCombo
                            Layout.preferredWidth: 420
                            implicitHeight: 36
                            model: viewModel.empresasOpcoes
                            currentIndex: viewModel.empresaIndice
                            enabled: !viewModel.ocupado
                            onActivated: viewModel.selecionarEmpresa(currentValue || "")
                            ToolTip.visible: hovered
                            ToolTip.text: "Filtrar notas por empresa"
                        }
                        Txt { text: viewModel.status; fraco: true }
                    }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    implicitHeight: 36
                    implicitWidth: certTxt.implicitWidth + 46
                    radius: 18
                    color: viewModel.certAlerta ? Theme.t.status.alertaSoft : Theme.t.status.sucessoSoft
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: configDialog.open() }
                    Row {
                        anchors.centerIn: parent
                        spacing: 8
                        Text { text: viewModel.certAlerta ? "⚠" : "🛡"; font.pixelSize: 14; color: viewModel.certAlerta ? Theme.t.status.alerta : Theme.t.status.sucesso }
                        Text {
                            id: certTxt; text: viewModel.certTexto; font.family: Theme.t.fontes.texto; font.pixelSize: 13; font.weight: 600
                            color: viewModel.certAlerta ? Theme.t.status.alerta : Theme.t.status.sucesso
                        }
                    }
                }
            }

            // Painel de sincronização + métricas
            RowLayout {
                Layout.fillWidth: true
                spacing: 16

                Rectangle {
                    Layout.preferredWidth: 360
                    implicitHeight: 104
                    radius: Theme.t.radius
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Theme.t.accent }
                        GradientStop { position: 1; color: Qt.darker(Theme.t.accent, 1.35) }
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 14
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text { text: viewModel.proxima ? "PRÓXIMA SINCRONIZAÇÃO" : "SEFAZ"; color: Qt.rgba(1,1,1,0.75); font.pixelSize: 11; font.weight: 700; font.letterSpacing: 1.2; font.family: Theme.t.fontes.texto }
                            Text { text: viewModel.proxima || (viewModel.ocupado ? "Trabalhando…" : "Liberada"); color: "white"; font.pixelSize: 26; font.weight: 700; font.family: viewModel.proxima ? Theme.t.fontes.mono : Theme.t.fontes.titulo }
                            Text { text: "Última: " + viewModel.ultima; color: Qt.rgba(1,1,1,0.75); font.pixelSize: 12; font.family: Theme.t.fontes.texto }
                        }
                        AbstractButton {
                            id: syncBtn
                            implicitWidth: 56; implicitHeight: 56
                            enabled: viewModel.syncLiberado
                            hoverEnabled: true
                            onClicked: viewModel.sincronizar()
                            ToolTip.visible: hovered
                            ToolTip.text: enabled ? "Sincronizar agora (F5)" : "Aguarde o intervalo da SEFAZ"
                            background: Rectangle { radius: 28; color: syncBtn.hovered ? "white" : Qt.rgba(1,1,1,0.92); opacity: syncBtn.enabled ? 1 : 0.35 }
                            contentItem: Text {
                                text: "⟳"; color: Theme.t.accent; font.pixelSize: 26; font.weight: 700
                                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                RotationAnimation on rotation { running: viewModel.ocupado; loops: Animation.Infinite; from: 0; to: 360; duration: 1100 }
                            }
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                        }
                    }
                }

                Metrica { rotulo: "Notas encontradas"; valor: viewModel.totalNotas.toLocaleString(Qt.locale("pt_BR"), "f", 0); icone: "▤"; cor: Theme.t.accent }
                Metrica { rotulo: "Valor total"; valor: viewModel.valorTotal; icone: "$"; cor: Theme.t.status.sucesso }
                Metrica {
                    rotulo: "XML baixados"
                    valor: viewModel.baixados + " / " + viewModel.totalNotas
                    icone: "⬇"
                    cor: Theme.t.status.alerta
                    progresso: viewModel.totalNotas > 0 ? viewModel.baixados / viewModel.totalNotas : 0
                }
            }

            // Filtros
            Cartao {
                Layout.fillWidth: true
                implicitHeight: 66
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 10
                    Campo { id: buscaInput; Layout.fillWidth: true; icone: "🔍"; placeholderText: "Buscar fornecedor…  (Ctrl+F)"; onAccepted: root.filtrar() }
                    Txt { text: "De"; fraco: true }
                    Campo {
                        id: deInput; Layout.preferredWidth: 130; placeholderText: "dd/mm/aaaa"; font.family: Theme.t.fontes.mono; maximumLength: 10
                        onTextEdited: root.mascaraData(deInput); onAccepted: root.filtrar()
                    }
                    Txt { text: "até"; fraco: true }
                    Campo {
                        id: ateInput; Layout.preferredWidth: 130; placeholderText: "dd/mm/aaaa"; font.family: Theme.t.fontes.mono; maximumLength: 10
                        onTextEdited: root.mascaraData(ateInput); onAccepted: root.filtrar()
                    }
                    Btn { text: "Filtrar"; onClicked: root.filtrar() }
                    Btn {
                        text: "Limpar"; variante: "fantasma"; visible: viewModel.filtrado
                        onClicked: { buscaInput.clear(); deInput.clear(); ateInput.clear(); viewModel.limparFiltros() }
                    }
                }
            }

            // Lista
            Cartao {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 1
                    spacing: 0

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 44
                        Layout.leftMargin: 20
                        Layout.rightMargin: 20
                        spacing: 16
                        Repeater {
                            model: [
                                { t: "EMITENTE", w: -1 }, { t: "Nº NF-E", w: 90 }, { t: "EMISSÃO", w: 130 },
                                { t: "VALOR", w: 130 }, { t: "SITUAÇÃO", w: 170 }, { t: "", w: 140 }
                            ]
                            Txt {
                                required property var modelData
                                required property int index
                                text: modelData.t
                                fraco: true
                                font.pixelSize: 11
                                font.weight: 700
                                font.letterSpacing: 1.2
                                Layout.fillWidth: modelData.w < 0
                                Layout.preferredWidth: modelData.w
                                horizontalAlignment: index === 1 || index === 3 ? Text.AlignRight : Text.AlignLeft
                            }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.t.border }

                    ListView {
                        id: lista
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: viewModel.notas
                        ScrollBar.vertical: ScrollBar {}
                        spacing: 0

                        delegate: Rectangle {
                            id: linha
                            required property var model
                            required property int index
                            required property string emitente
                            required property string iniciais
                            required property string numero
                            required property string valor
                            required property string situacao
                            required property string situacaoTexto
                            required property string chave
                            required property bool baixado
                            // "data" é propriedade reservada do Item; lida via model
                            readonly property string emissao: model.data ?? ""

                            width: lista.width
                            height: 68
                            color: hov.hovered ? Theme.t.surfaceAlt : "transparent"
                            HoverHandler { id: hov }
                            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.t.border; opacity: 0.6 }
                            Rectangle { visible: hov.hovered; width: 3; height: parent.height; color: Theme.t.accent }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 20
                                anchors.rightMargin: 20
                                spacing: 16

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 12
                                    Rectangle {
                                        width: 38; height: 38; radius: 12
                                        color: Qt.alpha(root.corAvatar(linha.emitente), 0.18)
                                        Text { anchors.centerIn: parent; text: linha.iniciais; color: root.corAvatar(linha.emitente); font.weight: 800; font.pixelSize: 13; font.family: Theme.t.fontes.texto }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Txt { Layout.fillWidth: true; text: linha.emitente; font.weight: 600 }
                                        Txt {
                                            Layout.fillWidth: true; text: linha.chave; fraco: true
                                            font.family: Theme.t.fontes.mono; font.pixelSize: 11
                                            MouseArea {
                                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                                onClicked: { copiador.text = linha.chave; copiador.selectAll(); copiador.copy(); root.toast("Chave copiada") }
                                            }
                                        }
                                    }
                                }
                                Txt { text: linha.numero; Layout.preferredWidth: 90; horizontalAlignment: Text.AlignRight; font.family: Theme.t.fontes.mono }
                                Txt { text: linha.emissao; Layout.preferredWidth: 130; fraco: true; font.pixelSize: 13 }
                                Txt { text: linha.valor; Layout.preferredWidth: 130; horizontalAlignment: Text.AlignRight; font.family: Theme.t.fontes.mono; font.weight: 600 }
                                Item {
                                    Layout.preferredWidth: 170
                                    implicitHeight: 26
                                    Pilula { anchors.verticalCenter: parent.verticalCenter; chave: linha.situacao; texto: linha.situacaoTexto }
                                }
                                Btn {
                                    Layout.preferredWidth: 140
                                    implicitHeight: 34
                                    variante: linha.baixado ? "fantasma" : "suave"
                                    text: linha.baixado ? "💾  Salvar" : "⬇  Baixar"
                                    enabled: !viewModel.ocupado
                                    onClicked: viewModel.acaoXml(linha.index)
                                }
                            }
                        }

                        // Estado vazio
                        Column {
                            anchors.centerIn: parent
                            visible: lista.count === 0
                            spacing: 8
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "∅"; font.pixelSize: 44; color: Theme.t.muted }
                            Txt {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: viewModel.filtrado ? "Nenhuma nota com esses filtros"
                                    : viewModel.empresaIndice > 0 ? "Nenhuma nota para esta empresa"
                                    : "Nenhuma nota ainda — sincronize com a SEFAZ"
                                fraco: true
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.t.border }

                    // Paginação
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 56
                        Layout.leftMargin: 20
                        Layout.rightMargin: 20
                        Txt { text: viewModel.totalNotas + " notas"; fraco: true; font.pixelSize: 13 }
                        Item { Layout.fillWidth: true }
                        Btn { text: "‹"; variante: "fantasma"; implicitWidth: 40; implicitHeight: 34; enabled: viewModel.pagina > 1 && !viewModel.ocupado; onClicked: { viewModel.irPagina(-1); lista.positionViewAtBeginning() } }
                        Txt { text: "Página  <b>" + viewModel.pagina + "</b>  de  " + viewModel.totalPaginas; textFormat: Text.StyledText; font.pixelSize: 13; Layout.leftMargin: 8; Layout.rightMargin: 8 }
                        Btn { text: "›"; variante: "fantasma"; implicitWidth: 40; implicitHeight: 34; enabled: viewModel.pagina < viewModel.totalPaginas && !viewModel.ocupado; onClicked: { viewModel.irPagina(1); lista.positionViewAtBeginning() } }
                    }
                }
            }
        }
    }

    // Copiar para a área de transferência
    TextEdit { id: copiador; visible: false }

    // Toast
    Rectangle {
        id: toastBox
        property string texto: ""
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 28
        width: toastTxt.implicitWidth + 40
        height: 44
        radius: 22
        color: Theme.t.text
        opacity: 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 220 } }
        Text { id: toastTxt; anchors.centerIn: parent; text: toastBox.texto; color: Theme.t.background; font.family: Theme.t.fontes.texto; font.pixelSize: 14; font.weight: 600 }
        Timer { id: toastTimer; interval: 2600; onTriggered: toastBox.opacity = 0 }
    }

    Shortcut { sequence: "Ctrl+F"; onActivated: buscaInput.forceActiveFocus() }
    Shortcut { sequence: "F5"; onActivated: if (viewModel.syncLiberado) viewModel.sincronizar() }
}
