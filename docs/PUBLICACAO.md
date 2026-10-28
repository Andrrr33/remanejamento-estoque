# Guia de publicação e demonstração

## Verificações antes de publicar atualizações

1. Confirme que o arquivo `dados/portfolio.sqlite3`, logs locais (`*.log`) e ambientes virtuais (`.venv/`) não estão listados no `git status`.
2. Execute a suíte de testes completa:
   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   ```
3. Inicie o aplicativo localmente e teste o acesso rápido com as contas `ADMINDEMO` e `COMPRASDEMO`.

## Execução local vs. hospedagem em nuvem

| Aspecto | Execução local (`127.0.0.1`) | Hospedagem em nuvem (ex.: Streamlit Community Cloud) |
| --- | --- | --- |
| Banco de dados | `dados/portfolio.sqlite3` persistido no disco local | SQLite criado automaticamente no container da aplicação |
| Sessão após `F5` | Conservada pelo cookie `HttpOnly` na porta `8774` | Mantida em `st.session_state` durante a conexão da aba |
| Contas iniciais | `ADMINDEMO` e `COMPRASDEMO` criadas na inicialização | `ADMINDEMO` e `COMPRASDEMO` criadas na inicialização |

## Separação entre portfólio e ambiente corporativo

Este repositório mantém a mesma arquitetura de interface, regras de cálculo de estoque, validações de sessão e formato de exportação Excel do sistema de produção, substituindo a camada de banco SQL Server corporativo pelo adaptador SQLite (`banco_local.py`) e pela massa sintética (`dados_demo.py`). Nenhum dado de clientes, filiais reais, servidores internos ou credenciais de trabalho faz parte deste código.
