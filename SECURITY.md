# Política de segurança

## Relato de vulnerabilidades

Se você identificar uma falha de segurança neste repositório, não abra uma issue pública com detalhes de exploração. Envie um relato privado pelo recurso de *Security Advisories* do GitHub contendo os passos de reprodução e o impacto observado.

## Escopo coberto pelo projeto

- Autenticação de usuários, derivação de senhas (`PBKDF2-HMAC-SHA256`) e bloqueio contra força bruta (`auth.py`).
- Validação de sessão e autorização no servidor antes de leituras, gravações e ações administrativas (`auth.py` e `real_data.py`).
- Serviço local de cookie `HttpOnly` e validação de origem (`session_bridge.py`).
- Prevenção de injeção de fórmulas na exportação de relatórios Excel (`real_data.py`).
- Isolamento de dados sintéticos sem exposição de credenciais ou infraestrutura privada.
