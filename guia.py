"""Estrutura e estado do guia inicial do aplicativo."""
from __future__ import annotations

VERSAO_GUIA = 1

ETAPAS_GERAIS: tuple[tuple[str, str], ...] = (
    ("Bem-vindo", "Este guia apresenta as telas principais. Use Próximo e Voltar para navegar."),
    ("Transferências", "Pesquise produtos, selecione os SKUs e escolha um plano de transferência."),
    ("Transferência de Pontas", "Consulte as sugestões para completar grades e confira antes de registrar."),
    ("Auditoria", "Acompanhe o status das solicitações, compare quantidades sugeridas e realizadas e filtre divergências."),
    ("Sua conta", "Use a barra lateral para alterar sua senha ou encerrar a sessão."),
)

ETAPA_ADMIN: tuple[str, str] = (
    "Ferramentas do administrador",
    "Na barra lateral, acompanhe pedidos de recuperação e baixe o relatório em Excel por período.",
)


def etapas_para(perfil: str | None) -> tuple[tuple[str, str], ...]:
    if perfil == "admin":
        return ETAPAS_GERAIS + (ETAPA_ADMIN,)
    return ETAPAS_GERAIS
