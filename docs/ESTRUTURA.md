# Estrutura e responsabilidades

| Área | Responsabilidade | Não deve conter |
| --- | --- | --- |
| `ui/` | Páginas, componentes, tema e acessibilidade | SQL direto, segredos e decisões de permissão |
| `domain/` | Entidades e regras de transferência | Código de Streamlit e acesso externo |
| `services/` | Casos de uso e autorização por operação | Componentes visuais |
| `repositories/` | Contratos de persistência | Regras duplicadas de negócio |
| `infrastructure/` | SQL Server, config, logs e integrações | Dados corporativos no código |
| `migrations/` | Evolução auditável do schema | Alterações manuais não documentadas |
| `tests/` | Evidência automatizada de comportamento | Dados reais ou credenciais |
| `demo_data/` | Massa sintética reprodutível | Exports reais |

## Exemplo de divisão de responsabilidade

Uma página pode solicitar que uma transferência seja criada, mas não deve montar SQL nem decidir sozinha se alguém é administrador. Ela envia dados validados ao serviço. O serviço valida a sessão e a permissão, aplica regras e usa um repositório para gravar. Assim, a mesma regra funciona para uma tela futura, uma API ou um processo automatizado.

