# Segurança: desenho esperado antes da publicação

## Identidade e sessão

- Senhas com hash adaptativo ou PBKDF2 forte, salt único e parâmetros revisáveis.
- Política mínima de senha, limite de tentativas e bloqueio temporário contra força bruta.
- Token de sessão aleatório, armazenado somente como hash no banco.
- Expiração por inatividade e invalidação global após troca de senha.
- Cookie `HttpOnly`, `Secure` em HTTPS e `SameSite` apropriado.
- Recuperação de senha com token de uso único, prazo curto e registro de auditoria.

## Autorização

Perfis não ficam restritos à interface. Cada serviço confirma no servidor se o usuário pode criar solicitação, consultar auditoria, exportar dados ou administrar acessos. A tela pode ocultar recursos sem permissão, mas o serviço toma a decisão.

## Banco de dados

- Conta específica para a aplicação, sem privilégio administrativo.
- Conta separada e temporária para executar migrações.
- Acesso protegido por rede, firewall e credenciais gerenciadas.
- SQL Server com conexão criptografada e certificado validado.
- Queries parametrizadas, transações para gravações relacionadas e auditoria de operações relevantes.

## Dados e arquivos

- O portfólio usa apenas dados criados para demonstração.
- Arquivos enviados são validados por tamanho, extensão, conteúdo e destino permitido.
- Exportações neutralizam valores interpretáveis como fórmulas por planilhas.
- Logs não registram senhas, tokens, strings de conexão ou dados pessoais desnecessários.

## Cadeia de fornecimento

- Dependências com versões controladas e atualização periódica.
- Verificação automatizada de vulnerabilidades conhecidas.
- Ações de CI com permissões mínimas e versões fixadas quando possível.
- Revisão de pull request antes de publicar em produção.

