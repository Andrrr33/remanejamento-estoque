# Publicação responsável no GitHub

## Sequência recomendada

1. Concluir as correções de segurança no ambiente de desenvolvimento.
2. Revisar o histórico Git e rotacionar qualquer credencial que tenha existido em commits antigos.
3. Extrair uma versão demonstrável com dados sintéticos e nomes neutros.
4. Confirmar que `.gitignore` exclui bancos, planilhas, logs, certificados e arquivos `.env`.
5. Criar testes para autenticação, autorização, fluxo de solicitações e exportação.
6. Ativar verificações automáticas de testes, dependências e segredos.
7. Publicar a demonstração em repositório público separado do repositório operacional privado.

## Automação esperada no GitHub

| Evento | Verificação |
| --- | --- |
| Pull request | Formatação, testes e análise estática |
| Pull request | Varredura de segredos e dependências vulneráveis |
| Dependência atualizada | Pull request automático para revisão |
| Release | Criação de versão identificável e notas de mudança |

## Por que dois repositórios

O repositório operacional tem contexto de negócio, configuração privada e histórico que não devem ser públicos. O repositório de portfólio mostra o código e as decisões técnicas sem expor a operação. Os dois podem seguir a mesma arquitetura, sem compartilhar dados, segredos ou histórico.

