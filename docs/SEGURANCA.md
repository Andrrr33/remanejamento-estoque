# Controles de segurança implementados

## Autenticação e senhas (`auth.py`)

- As senhas são derivadas com `PBKDF2-HMAC-SHA256`, 600.000 iterações e salt aleatório de 16 bytes por usuário.
- A verificação usa `hmac.compare_digest` e executa uma derivação contra um hash fixo quando o usuário informado não existe, reduzindo diferenças de tempo de resposta.
- Cinco falhas consecutivas de senha bloqueiam a conta por 15 minutos (`900` segundos).
- O cadastro exige nomes de usuário ASCII de 3 a 32 caracteres alfanuméricos e senhas entre 12 e 128 caracteres, criando sempre contas com perfil `usuario`.
- A recuperação de senha gera um pedido pendente para aprovação de um administrador. Ao emitir a senha temporária, o sistema invalida todas as sessões anteriores daquela conta e exige a troca da senha no próximo acesso.

## Sessão e autorização por operação (`auth.py`, `session_bridge.py` e `real_data.py`)

- O banco armazena apenas o hash `SHA-256` do token de sessão aleatório (`secrets.token_urlsafe(32)`).
- As sessões expiram após 5 minutos de inatividade (`300` segundos) ou imediatamente quando `versao_senha` é incrementada.
- O cookie de sessão local recebe os atributos `HttpOnly`, `SameSite=Strict` e `Max-Age=300` (adicionando `Secure` quando executado sob HTTPS).
- Operações de leitura, gravação de solicitações, administração de recuperações e download de relatório validam a sessão e o perfil no servidor por meio de `exigir_usuario()`.

## Integridade de dados e exportação (`banco_local.py` e `real_data.py`)

- A tabela `solicitacoes` possui restrições `CHECK(Quantidade_sugerida > 0)` e `CHECK(Filial_origem_ID != Filial_destino_ID)` no schema do SQLite.
- A gravação de novas solicitações roda dentro de uma transação `BEGIN IMMEDIATE`, conferindo se a quantidade é inteira e positiva, se não há solicitação pendente idêntica na janela operacional e se o volume não excede o estoque disponível na origem.
- O gerador de planilhas em `gerar_relatorio_excel` inicializa o `XlsxWriter` com `strings_to_formulas=False` e `strings_to_urls=False`, impedindo que descrições de produtos iniciadas por `=`, `+`, `-` ou `@` sejam interpretadas como fórmulas pelo Excel.
