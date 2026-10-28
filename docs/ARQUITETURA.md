# Arquitetura da aplicação

## Fluxo de execução e camadas

A aplicação separa a interface Streamlit das regras de cálculo, persistência e autenticação:

```mermaid
flowchart LR
    U["Navegador do usuário"] -->|"HTTP local (8504)"| APP["app.py (Interface Streamlit)"]
    U -->|"Cookie HttpOnly (8774)"| BRIDGE["session_bridge.py"]
    APP --> AUTH["auth.py (Identidade e sessão)"]
    APP --> DATA["real_data.py (Consultas e gravação)"]
    APP --> CALC["calculos.py (Algoritmos de estoque)"]
    CALC --> DEMO["dados_demo.py (Catálogo, saldos e vendas 60d)"]
    DATA --> DEMO
    DATA --> DB[("banco_local.py (SQLite)")]
    AUTH --> DB
    BRIDGE --> AUTH
```

## Ciclo de uma solicitação de transferência

```mermaid
sequenceDiagram
    participant Usuario as Usuário
    participant Tela as app.py (Streamlit)
    participant Calculo as calculos.py
    participant Dados as real_data.py
    participant Auth as auth.py
    participant SQLite as portfolio.sqlite3

    Usuario->>Tela: Filtra catálogo, seleciona SKUs e escolhe estratégia
    Tela->>Calculo: Calcula sugestões (Concentrar, Distribuir ou Pontas)
    Calculo-->>Tela: Lista de transferências sugeridas por origem e destino
    Usuario->>Tela: Confirma o registro do plano
    Tela->>Dados: gravar_novas_solicitacoes(sugestoes)
    Dados->>Auth: exigir_usuario() valida token ativo e senha
    Auth-->>Dados: Conta autenticada
    Dados->>SQLite: BEGIN IMMEDIATE, confere duplicatas pendentes e grava
    Dados-->>Tela: Quantidade registrada e quantidade ignorada
    Tela-->>Usuario: Exibe confirmação e atualiza indicadores
```

## Decisões técnicas

### Persistência híbrida na demonstração

O catálogo de produtos, os saldos de estoque e as vendas dos últimos 60 dias vêm de funções determinísticas em `dados_demo.py`. Assim, os cenários de excesso, ruptura e grade furada estão sempre prontos para teste. Já as contas de usuário, as sessões, os pedidos de recuperação de senha e as novas solicitações de transferência são gravados em `dados/portfolio.sqlite3` por `banco_local.py`.

### Validação de sessão no servidor em cada operação

O Streamlit pode reexecutar apenas um diálogo (`@st.dialog`) ou um fragmento (`@st.fragment`) sem rodar o topo do script principal. Por isso, `real_data.py` e `auth.py` chamam `exigir_usuario()` dentro de cada função que lê dados restritos, grava solicitações, emite senhas temporárias ou exporta o relatório Excel.

### Continuidade da sessão após recarregar a página

O módulo `session_bridge.py` inicia um servidor HTTP local na porta `8774` para gravar um cookie `HttpOnly` com `SameSite=Strict`. Quando o usuário recarrega a página com `F5`, `app.py` lê o cookie via `st.context.cookies` e restaura a sessão caso não tenha passado mais de 5 minutos sem interação. Se o aplicativo rodar em um ambiente de nuvem onde a porta secundária não esteja acessível ao navegador, a sessão continua funcionando normalmente em memória pelo `st.session_state`.
