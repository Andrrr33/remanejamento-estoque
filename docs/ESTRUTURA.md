# Estrutura e responsabilidades dos módulos

| Arquivo ou pasta | Responsabilidade | O que não deve conter |
| --- | --- | --- |
| `app.py` | Telas, filtros, tabelas editáveis, diálogos e navegação | Consultas SQL ou lógica de cálculo de estoque |
| `calculos.py` | Regras de distribuição cadenciada, concentração, pontas de grade e conciliação de auditoria | Dependência de sessão do Streamlit ou escrita no banco |
| `real_data.py` | Leitura de dados para a tela, validação transacional de solicitações e geração da planilha Excel | Componentes visuais |
| `dados_demo.py` | Geração da massa sintética de produtos, saldos por filial, giro de 60 dias e histórico inicial | Credenciais ou dados de operação real |
| `banco_local.py` | Gerenciador de contexto do SQLite e criação das tabelas (`usuarios`, `sessoes`, `recuperacoes`, `solicitacoes`) | Regras de interface |
| `auth.py` | Hash de senhas (`PBKDF2-HMAC-SHA256`), bloqueio por tentativas, tokens de sessão e recuperação de conta | Renderização de telas |
| `session_bridge.py` | Endpoint local para cookie `HttpOnly` e monitoramento de ociosidade no navegador | Acesso direto a tabelas de negócio |
| `guia.py` | Textos e passos do guia de introdução conforme o perfil do usuário | Estado de sessão ou banco |
| `tests/test_fluxos.py` | Testes unitários e de integração da interface com `unittest` e `Streamlit AppTest` | Dependência de banco externo |

## Fluxo entre os módulos

Quando o usuário seleciona produtos na tabela de `app.py` e escolhe um plano de transferência, a interface passa a lista de SKUs e parâmetros para `calculos.py`. O módulo de cálculo consulta a base em `dados_demo.py`, aplica as travas de cobertura, estoque mínimo de vitrine ou recomposição de grade e devolve uma lista de dicionários padronizados (`SKU`, `Filial_Origem_ID`, `Filial_Destino_ID`, `Quantidade`, `Motivo`).

Ao confirmar o envio, `app.py` aciona `gravar_novas_solicitacoes` em `real_data.py`. Essa função verifica a sessão ativa com `exigir_usuario()` de `auth.py`, abre uma transação `BEGIN IMMEDIATE` no SQLite via `banco_local.py`, impede duplicidades pendentes nos últimos 10 dias, valida o saldo disponível na filial de origem e registra a solicitação.
