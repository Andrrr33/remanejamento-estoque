# Política de segurança

## Comunicação responsável

Não publique vulnerabilidades, credenciais, endereços internos, dados de usuários ou evidências sensíveis em issues públicas. Utilize um canal privado definido pelo responsável pelo repositório e inclua uma descrição objetiva do problema, impacto e forma de reprodução.

O recebimento deve ser confirmado, o risco avaliado e a correção planejada antes de qualquer divulgação pública.

## Escopo esperado

- Autenticação, autorização e gestão de sessão.
- Proteção de dados e consultas ao banco.
- Importação e exportação de planilhas.
- Exposição acidental de segredos, arquivos internos ou dados de operação.
- Dependências vulneráveis e cadeia de fornecimento.

## Controles adotados na versão pública

- Nenhum segredo é versionado; somente `.env.example` é mantido no Git.
- Dados de demonstração são sintéticos.
- O repositório exclui certificados, bancos locais, exports, logs e arquivos temporários.
- A integração contínua executa testes e verificações de dependências.
- Alterações de estrutura de banco são versionadas como migrações revisáveis.

