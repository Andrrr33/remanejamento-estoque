# Como contribuir

Este repositório apresenta uma versão funcional e autocontida do sistema de remanejamento de estoque com dados sintéticos. Contribuições devem manter o projeto executável sem dependências externas.

## Passo a passo para alterações

1. Crie uma branch a partir da branch principal.
2. Mantenha o escopo da alteração focado em um único ajuste ou funcionalidade.
3. Atualize ou adicione testes em `tests/test_fluxos.py` sempre que alterar cálculos de estoque, regras de autenticação ou validações de gravação.
4. Execute a suíte de testes antes de abrir um pull request:
   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   ```

## Critérios de revisão

- Nenhum banco `.sqlite3`, planilha `.xlsx`, certificado ou arquivo `.log` incluído no commit.
- Compatibilidade preservada com os testes automatizados existentes.
- Consultas SQL parametrizadas e validação de sessão via `exigir_usuario()` nas operações do servidor.
