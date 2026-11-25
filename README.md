# 📄 NF-e Monitor

Aplicativo desktop para **monitorar, consultar e baixar as NF-e emitidas contra os CNPJs da sua empresa**. Ele usa o serviço de **Distribuição DF-e da SEFAZ** e acessa a SEFAZ com o certificado digital A1 instalado no Windows.

Ele foi feito para escritórios e empresas que precisam acompanhar as notas de entrada de **um ou mais CNPJs** num só lugar.

---

## ✨ Funcionalidades

- 🔄 **Sincronização com a SEFAZ** a partir do último NSU, respeitando o intervalo obrigatório de 1 hora
- 🏢 **Várias empresas**: sincroniza todos os CNPJs ativos, e a tela filtra as notas por empresa
- 🔐 **Certificado digital do Windows**: cada empresa pode usar o seu certificado ou o certificado padrão
- 📥 **Download do XML completo** com manifestação de **Ciência da Operação**
- 🔍 **Filtros** por fornecedor, período de emissão e empresa
- 📊 **Painel** com quantidade de notas, valor total e progresso dos XMLs baixados
- 🎨 **Temas** claro e escuro
- 🧾 **Registro de operações**: cada sincronização fica gravada no banco, com início, fim, status e detalhe

---

## 🧱 Arquitetura

O projeto é organizado em camadas, no estilo *Clean Architecture* com *MVVM* na interface:

```
nfe-monitor/
├── main.py                      # Ponto de entrada (QML + view models)
├── requirements.txt
└── nfe_monitor/
    ├── domain/                  # Regras e entidades (Resumo, FUSO)
    ├── application/             # Casos de uso
    │   ├── sincronizar.py       # Distribuição DF-e (uma ou todas as empresas)
    │   ├── listar_notas.py      # Consulta paginada + métricas
    │   ├── baixar_xml.py        # Manifestação + download do XML
    │   └── limite.py            # Controle do intervalo entre sincronizações
    ├── infrastructure/
    │   ├── database/
    │   │   ├── conexao.py       # Conexão SQLite + códigos de UF
    │   │   └── notas_repository.py
    │   ├── sefaz/
    │   │   ├── cliente.py       # Chamadas SOAP
    │   │   ├── distribuicao.py  # Leitura dos lotes (cStat, NSU, docs)
    │   │   └── parametros.py    # Config (banco, thumbprint, UF)
    │   ├── certificados.py      # Certificados do repositório do Windows
    │   ├── preferencias.py      # config.json do usuário
    │   └── paths.py             # Pastas de dados e recursos (compatível com PyInstaller)
    └── ui/
        ├── viewmodels/
        │   ├── main_viewmodel.py    # Notas, filtros, sincronização
        │   └── config_viewmodel.py  # Certificados, empresas, preferências
        ├── themes/
        │   └── theme_manager.py     # Tema claro/escuro (exposto como "Theme")
        ├── models/notas_model.py
        ├── formatters.py
        └── qml/
            └── Main.qml             # Interface (Qt Quick, estilo Basic)
```

### Como a interface é montada

O `main.py` cria os três objetos e os expõe ao QML como propriedades de contexto:

| Nome no QML | Classe Python | Função |
|---|---|---|
| `Theme` | `ThemeManager` | Cores e tema ativo |
| `viewModel` | `MainViewModel` | Lista de notas, filtros, sincronização e download |
| `config` | `ConfigViewModel` | Tela de configurações |

Quando você salva as configurações, o sinal `config.salvo` chama `viewModel.atualizarCertificado`, então o certificado novo passa a valer na hora, sem reiniciar o programa.

### Tecnologias

| Camada | Bibliotecas |
|---|---|
| Interface | **PySide6 6.12** (Qt Quick / QML, estilo *Basic*) |
| Comunicação com a SEFAZ | **httpx** (HTTP), **lxml** (XML), **xsdata** (classes geradas a partir dos XSD) |
| Certificado digital | **cryptography** |
| Banco de dados | **SQLite** (já vem com o Python) |
| Qualidade | **pytest**, **ruff**, **mypy** |

---

## ✅ Requisitos

| Item | Versão / observação |
|---|---|
| Sistema operacional | **Windows 10/11**, porque os certificados vêm do repositório do Windows |
| Python | **3.10 ou superior** (64 bits) |
| Certificado digital | **e-CNPJ A1** instalado em *Usuário Atual → Pessoal* |
| Internet | Acesso aos webservices da SEFAZ e à BrasilAPI (usada para descobrir a UF da empresa) |

---

## 🚀 Instalação e ativação

### 1. Clonar o projeto

```bash
git clone <url-do-repositorio> nfe-monitor
cd nfe-monitor
```

### 2. Criar e ativar o ambiente virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> Se o PowerShell bloquear o script, rode uma vez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 3. Instalar as dependências

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Abrir o aplicativo

Rode a partir da **raiz do projeto**:

```powershell
python main.py
```

Na primeira execução, a pasta `%APPDATA%\NFeMonitor` é criada sozinha. Não é preciso preparar nada antes.

> Se a janela não abrir e o programa terminar com código `1`, o `Main.qml` não carregou. O erro de QML aparece no terminal.

---

## ⚙️ Configuração inicial

Na primeira execução, clique em **⚙ Configurações** na barra lateral.

### 1. Certificado digital
- Escolha o certificado na lista. Use **↻** para recarregar a lista se você acabou de instalar um certificado.
- Abaixo da lista aparecem o **CNPJ**, a **validade** e a **situação** do certificado. Ele fica em alerta quando está perto de vencer.

### 2. Cadastrar empresas
1. Selecione o certificado da empresa.
2. Preencha a **UF** ou deixe em branco para buscar na **BrasilAPI**.
3. Clique em **＋ Cadastrar empresa do certificado selecionado**.

Cada empresa aparece com um status:

| Status | Significado |
|---|---|
| 🟢 **Pronta** | Tem UF e certificado, já pode sincronizar |
| 🟡 **Incompleta** | Falta a UF ou o certificado |
| ⚪ **Inativa** | Não é mais monitorada, mas as notas dela continuam no banco |

### 3. Pasta dos XMLs
- **Escolher**: define uma pasta padrão para onde os XMLs são copiados.
- **Limpar**: faz o programa perguntar a pasta a cada download.

> Independentemente dessa escolha, o programa sempre guarda uma cópia do XML em `%APPDATA%\NFeMonitor\xml\<CNPJ>\`.

### 4. Aparência
Escolha o tema. Também dá para alternar pelo botão ☀/☾ da barra lateral.

Clique em **Salvar** para aplicar. A mudança vale na hora, sem reiniciar.

---

## 🖥️ Uso no dia a dia

### Sincronizar
- Clique em **⟳** ou pressione **F5**.
- Todas as empresas ativas são consultadas. No fim aparece um resumo, por exemplo `✓ 12 nova(s) · 1 em espera`.
- O painel mostra uma **contagem regressiva** até a próxima sincronização permitida.

### Filtrar
| Filtro | Como usar |
|---|---|
| Empresa | Seletor no cabeçalho, que só aparece com 2 ou mais empresas. A escolha fica salva para a próxima vez |
| Fornecedor | Campo de busca (**Ctrl+F**) |
| Período | Campos **De / até** no formato `dd/mm/aaaa` |

### Baixar ou salvar o XML
- **⬇ Baixar**: na primeira vez, o programa pede confirmação da **Ciência da Operação** na SEFAZ.
  > ⚠️ A manifestação é **definitiva** e não pode ser desfeita.
- **💾 Salvar**: copia para a pasta escolhida um XML que já foi baixado.
- Clique na **chave de acesso** para copiá-la.

### Atalhos
| Tecla | Ação |
|---|---|
| `F5` | Sincronizar |
| `Ctrl+F` | Ir para a busca por fornecedor |

---

## 🧰 Linha de comando

Também dá para sincronizar sem abrir a interface, o que serve para agendar tarefas:

```powershell
# Todas as empresas ativas
python -m nfe_monitor.application.sincronizar

# Uma empresa específica
python -m nfe_monitor.application.sincronizar 12345678000190

# Ignorar o bloqueio local (use com cuidado)
python -m nfe_monitor.application.sincronizar 12345678000190 --forcar
```

**Códigos de saída**

| Código | Significado |
|---|---|
| `0` | Sucesso |
| `1` | CNPJ inválido, CNPJ não cadastrado ou nenhuma empresa cadastrada |
| `2` | A SEFAZ pediu espera (cStat 656 ou intervalo ainda ativo) |
| `3` | Falha na sincronização |

### Agendar no Windows (Agendador de Tarefas)

```powershell
schtasks /create /tn "NFe Monitor" /sc hourly /mo 1 ^
  /tr "cmd /c cd /d C:\caminho\nfe-monitor && .venv\Scripts\python.exe -m nfe_monitor.application.sincronizar"
```

> A tarefa precisa rodar com o **mesmo usuário do Windows** que usa o aplicativo, porque o banco e o certificado ficam no perfil desse usuário. O `cd /d` garante que o pacote `nfe_monitor` seja encontrado.

---

## 📏 Regras da SEFAZ que o sistema respeita

| Situação | O que o sistema faz |
|---|---|
| Fila zerada (`cStat 137` ou `ultNSU == maxNSU`) | Bloqueia novas consultas daquela empresa por **60 min** |
| Consumo indevido (`cStat 656`) | Bloqueia por **60 min** e registra a ocorrência |
| Lote processado | Grava as notas e o NSU **na mesma transação**, então nada se perde se der falha no meio |
| NSU não avançou | Interrompe a consulta para evitar um laço infinito |

---

## 💾 Dados e arquivos

Todos os dados ficam no perfil do usuário, numa pasta onde o programa sempre tem permissão de escrita:

```
%APPDATA%\NFeMonitor\          (ex.: C:\Users\<usuario>\AppData\Roaming\NFeMonitor)
├── nfe.db                     # Banco SQLite
├── config.json                # Preferências do usuário
└── xml\
    └── <CNPJ>\<chave>.xml     # XMLs completos, separados por empresa
```

> Para abrir a pasta, pressione `Win + R` e digite `%APPDATA%\NFeMonitor`.
> Se a variável `APPDATA` não existir, o programa usa a pasta pessoal do usuário (`~/NFeMonitor`).

| Arquivo | Conteúdo |
|---|---|
| `nfe.db` | Tabelas `empresas`, `controle_nsu`, `nfe` e `operacoes` |
| `config.json` | Certificado padrão, pasta de download, última sincronização e empresa filtrada |
| `xml\` | XMLs completos baixados da SEFAZ |

### Exemplo de `config.json`

```json
{
  "thumbprint": "A1B2C3...",
  "pasta_download": "C:\\XMLs",
  "ultima_sincronizacao": "2026-11-25T16:00:00-03:00",
  "empresa_filtro": ""
}
```

### Backup

Basta copiar a pasta `%APPDATA%\NFeMonitor` inteira com o aplicativo **fechado**. Para restaurar, coloque a pasta de volta no mesmo lugar.

### Recomeçar do zero

Feche o aplicativo e apague a pasta `%APPDATA%\NFeMonitor`.

> ⚠️ Isso apaga o histórico de NSU. Na próxima sincronização, a SEFAZ devolve só os documentos dos **últimos 90 dias**.

---

## 📦 Gerar executável (PyInstaller)

O `paths.py` já encontra os arquivos de recurso (QML) tanto no código-fonte quanto dentro do executável, usando `sys._MEIPASS`.

```powershell
pip install pyinstaller
pyinstaller main.py --name "NFe Monitor" --windowed --noconfirm ^
  --add-data "nfe_monitor/ui/qml;nfe_monitor/ui/qml"
```

| Opção | Para quê |
|---|---|
| `--windowed` | Abre sem a janela preta do console |
| `--add-data` | Inclui os arquivos `.qml` no pacote. O caminho de destino precisa ser igual ao que o `main.py` usa em `recurso(...)` |

O executável fica em `dist\NFe Monitor\NFe Monitor.exe`. Os dados continuam em `%APPDATA%\NFeMonitor`, então atualizar o programa não apaga nada.

> Se a janela não abrir no `.exe`, gere uma vez **sem** `--windowed` para ver o erro de QML no console.

---

## 🧪 Desenvolvimento

| Ferramenta | Comando | Para quê |
|---|---|---|
| pytest | `pytest` | Rodar os testes |
| ruff | `ruff check .` | Apontar problemas de estilo e erros comuns |
| ruff | `ruff format .` | Formatar o código |
| mypy | `mypy nfe_monitor main.py` | Checar os tipos |

Antes de cada commit, rode os quatro comandos:

```powershell
ruff check . ; ruff format --check . ; mypy nfe_monitor main.py ; pytest
```

---

## 🛠️ Solução de problemas

| Problema | Solução |
|---|---|
| A janela não abre (código de saída `1`) | Erro no `Main.qml`. Veja a mensagem no terminal |
| `ModuleNotFoundError: nfe_monitor` | Rode o comando a partir da raiz do projeto, com o `.venv` ativado |
| "Certificado não configurado" | Selecione e salve um certificado em ⚙ Configurações |
| Certificado não aparece na lista | Instale o `.pfx` em *Usuário Atual → Pessoal* e clique em ↻ |
| Empresa **Incompleta** | Cadastre de novo informando a UF manualmente |
| `0 nova(s) · 1 em espera` | Comportamento normal: a SEFAZ exige esperar 1 h |
| Notas antigas somem ao filtrar por empresa | São notas sem `empresa_cnpj`. Corrija com o SQL abaixo |
| "Há uma operação em andamento" ao fechar | Aguarde a sincronização ou o download terminar |
| Erro ao instalar o `PySide6` | Confira se o Python é **64 bits** e se a versão é 3.10 ou superior |
| A tarefa agendada não encontra as notas | Configure a tarefa para rodar com o mesmo usuário do Windows que usa o aplicativo |

```sql
UPDATE nfe SET empresa_cnpj = '00000000000000' WHERE empresa_cnpj IS NULL;
```

---

## 🔒 Segurança

- O certificado **nunca é copiado**: o programa guarda só o *thumbprint* e usa o repositório do Windows.
- Os dados ficam **fora da pasta do projeto** (em `%APPDATA%`), então não vão para o Git por acidente.

```gitignore
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
build/
dist/
*.spec
```

---

## 📜 Licença

Defina a licença do projeto (por exemplo, MIT ou proprietária).
