"""
Remanejamento de Estoque: Painel Executivo v3.
Interface Streamlit para planejamento, recomposição de grade e auditoria de transferências.
"""

from datetime import datetime
from functools import partial
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from auth import (
    autenticar,
    cadastrar,
    cancelar_recuperacao,
    criar_sessao,
    emitir_senha_temporaria,
    marcar_guia_visto,
    recuperacoes_pendentes,
    revogar_sessao,
    solicitar_recuperacao,
    trocar_senha,
    validar_sessao,
)
from calculos import (
    calcular_concentracao_pontas,
    calcular_distribuicao_cadenciada,
    gerar_transferencia_concentracao,
)
from guia import VERSAO_GUIA, etapas_para
from real_data import (
    READ_ONLY,
    auditar_sugestoes,
    buscar_grade_unificada,
    carregar_dados_do_banco,
    carregar_dados_para_editor,
    carregar_solicitacoes_relatorio,
    gerar_relatorio_excel,
    gravar_novas_solicitacoes,
)
from session_bridge import COOKIE, acompanhar_navegador, ensure_bridge

st.set_page_config(
    page_title="Remanejamento · Operações",
    page_icon=":material/sync_alt:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

css = Path(__file__).parent / "antigravity.css"
if css.exists():
    st.markdown(f"<style>{css.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

ensure_bridge()
for chave, padrao in {
    "usuario_id": None,
    "versao_senha": None,
    "usuario_nome": None,
    "tipo_acesso": None,
    "auth_token": None,
    "cookie_pending": False,
    "chave_editor": 0,
    "df_catalogo": pd.DataFrame(),
    "sugestoes_temp": None,
    "sugestoes_pontas_temp": None,
    "confirmacao_solicitacao": None,
    "mostrar_dialogo_confirmacao": False,
}.items():
    if chave not in st.session_state:
        st.session_state[chave] = padrao

if not st.session_state["auth_token"]:
    token_cookie = st.context.cookies.get(COOKIE)
    if token_cookie:
        try:
            conta = validar_sessao(token_cookie)
        except Exception:
            st.error("Não foi possível validar sua sessão no banco local.")
            st.stop()
        if conta:
            st.session_state["auth_token"] = token_cookie
            st.session_state["usuario_id"] = conta["id"]
            st.session_state["versao_senha"] = conta["versao_senha"]

conta = None
if st.session_state["auth_token"]:
    try:
        conta = validar_sessao(st.session_state["auth_token"])
    except Exception:
        st.error("Não foi possível validar sua sessão no banco local.")
        st.stop()
    if not conta:
        st.session_state.clear()
        st.rerun()
    st.session_state["usuario_id"] = conta["id"]
    st.session_state["versao_senha"] = conta["versao_senha"]
    st.session_state["usuario_nome"] = conta["username"]
    st.session_state["tipo_acesso"] = conta["perfil"]
else:
    st.session_state["usuario_id"] = None
    st.session_state["usuario_nome"] = None
    st.session_state["tipo_acesso"] = None

resultado_cookie = acompanhar_navegador(
    action="set"
    if st.session_state["cookie_pending"]
    else ("watch" if st.session_state["auth_token"] else "clear"),
    token=st.session_state["auth_token"] if st.session_state["cookie_pending"] else None,
    logged_in=bool(st.session_state["auth_token"]),
)
if resultado_cookie.cookie_ready in (True, False):
    st.session_state["cookie_pending"] = False
if resultado_cookie.expired:
    st.session_state.clear()
    st.rerun()


@st.fragment(run_every="10s")
def verificar_ociosidade():
    token = st.session_state.get("auth_token")
    if token and not validar_sessao(token):
        st.session_state.clear()
        st.rerun(scope="app")


if st.session_state["auth_token"]:
    verificar_ociosidade()


def _iniciar_sessao_conta(dados_conta: dict) -> None:
    st.session_state["auth_token"] = criar_sessao(dados_conta["id"], dados_conta["versao_senha"])
    st.session_state["cookie_pending"] = True
    st.session_state["usuario_id"] = dados_conta["id"]
    st.session_state["versao_senha"] = dados_conta["versao_senha"]
    st.session_state["usuario_nome"] = dados_conta["username"]
    st.session_state["tipo_acesso"] = dados_conta["perfil"]
    st.rerun()


if not st.session_state["usuario_id"]:
    st.html(
        """
        <div class="app-header"><div class="brand">
          <div class="brand-logo-frame">
            <span style="font-size:32px;color:#ea5e39" aria-label="Remanejamento">⇄</span>
          </div><div><span class="eyebrow">Portfólio</span>
          <h1>Remanejamento de estoque</h1>
          <span class="subtitle">Acesse sua conta para explorar os fluxos com dados sintéticos.</span></div>
        </div></div>
        """
    )
    _, coluna_login, _ = st.columns([1, 1.4, 1])
    with coluna_login:
        st.caption("Contas locais de demonstração: ADMINDEMO ou COMPRASDEMO (senha inicial: Portfolio2026!).")
        aba_entrar, aba_cadastro, aba_recuperar = st.tabs(["Entrar", "Criar conta", "Esqueci a senha"])
        with aba_entrar:
            with st.form("form_entrar", enter_to_submit=False):
                usuario = st.text_input("Nome de usuário", autocomplete="username")
                senha = st.text_input("Senha", type="password", autocomplete="current-password")
                entrar = st.form_submit_button("Acessar painel", type="primary", width="stretch")
            if entrar:
                try:
                    conta = autenticar(usuario, senha)
                except Exception:
                    st.error("Não foi possível acessar o banco local. Tente novamente.")
                else:
                    if not conta:
                        st.error("Usuário ou senha inválidos. Se necessário, solicite a recuperação.")
                    else:
                        _iniciar_sessao_conta(conta)

            st.caption("Acesso rápido para demonstração:")
            col_demo_admin, col_demo_compras = st.columns(2)
            with col_demo_admin:
                if st.button("Entrar como Admin", key="btn_demo_admin", width="stretch"):
                    conta_demo = autenticar("ADMINDEMO", "Portfolio2026!")
                    if conta_demo:
                        _iniciar_sessao_conta(conta_demo)
                    else:
                        st.info("A senha padrão de ADMINDEMO foi alterada. Use o formulário acima.")
            with col_demo_compras:
                if st.button("Entrar como Compras", key="btn_demo_compras", width="stretch"):
                    conta_demo = autenticar("COMPRASDEMO", "Portfolio2026!")
                    if conta_demo:
                        _iniciar_sessao_conta(conta_demo)
                    else:
                        st.info("A senha padrão de COMPRASDEMO foi alterada. Use o formulário acima.")

        with aba_cadastro:
            st.caption("Use de 3 a 32 letras sem acento ou números. A senha pode conter espaços e símbolos.")
            with st.form("form_cadastro", enter_to_submit=False):
                novo_usuario = st.text_input("Escolha seu nome de usuário", autocomplete="username")
                nova_senha = st.text_input(
                    "Crie uma senha (mínimo 12 caracteres)",
                    type="password",
                    autocomplete="new-password",
                )
                confirmar = st.text_input(
                    "Confirme a senha",
                    type="password",
                    autocomplete="new-password",
                )
                criar = st.form_submit_button("Criar conta", type="primary", width="stretch")
            if criar:
                if nova_senha != confirmar:
                    st.error("As senhas não conferem.")
                else:
                    try:
                        cadastrar(novo_usuario, nova_senha)
                    except ValueError as erro:
                        st.error(str(erro))
                    except Exception:
                        st.error("Não foi possível criar a conta no banco local.")
                    else:
                        st.success("Conta criada. Entre com seu nome de usuário e senha.")
        with aba_recuperar:
            st.caption(
                "Informe seu nome de usuário. Um administrador precisará confirmar sua identidade e liberar uma senha temporária."
            )
            with st.form("form_recuperar"):
                recuperar_usuario = st.text_input("Nome de usuário para recuperar")
                solicitar = st.form_submit_button("Solicitar recuperação", width="stretch")
            if solicitar:
                try:
                    solicitar_recuperacao(recuperar_usuario)
                except Exception:
                    st.error("Não foi possível registrar o pedido agora.")
                else:
                    st.info("Se a conta existir, o pedido ficará disponível para um administrador.")
    st.stop()

if conta["trocar_senha"]:
    st.subheader("Defina uma nova senha")
    st.write("Sua conta está usando uma senha temporária. Troque-a antes de acessar o painel.")
    with st.form("form_troca_obrigatoria", enter_to_submit=False):
        senha_atual = st.text_input("Senha atual ou temporária", type="password")
        nova_senha = st.text_input("Nova senha (mínimo 12 caracteres)", type="password")
        confirmar = st.text_input("Confirme a nova senha", type="password")
        salvar = st.form_submit_button("Salvar nova senha", type="primary")
    if salvar:
        if nova_senha != confirmar:
            st.error("As senhas não conferem.")
        else:
            try:
                alterada = trocar_senha(st.session_state["usuario_id"], senha_atual, nova_senha)
            except ValueError as erro:
                st.error(str(erro))
            except Exception:
                st.error("Não foi possível atualizar a senha.")
            else:
                if alterada:
                    revogar_sessao(st.session_state["auth_token"])
                    st.session_state["versao_senha"] += 1
                    st.session_state["auth_token"] = criar_sessao(
                        st.session_state["usuario_id"], st.session_state["versao_senha"]
                    )
                    st.session_state["cookie_pending"] = True
                    st.rerun()
                else:
                    st.error("Senha atual incorreta.")
    if st.button("Desconectar", key="sair_troca_senha"):
        revogar_sessao(st.session_state["auth_token"])
        st.session_state.clear()
        st.rerun()
    st.stop()

df_sugestoes, df_reais, df_produtos, df_filiais, df_kpis_base = carregar_dados_do_banco()
if df_filiais.empty:
    st.error("Não foi possível carregar as filiais do banco. Verifique a conexão e atualize a página.")
    st.stop()
MAPA_NOMES_FILIAIS = dict(zip(df_filiais["FilialID"].astype(int), df_filiais["Nome_filial"]))
opcoes_lojas = df_filiais["Nome_filial"].tolist()
id_por_nome = {nome: filial_id for filial_id, nome in MAPA_NOMES_FILIAIS.items()}


def filial_id(nome: str) -> int:
    return id_por_nome[nome]


def bytes_relatorio_periodo(data_inicial, data_final, token, kpis, filiais):
    conta_atual = validar_sessao(token)
    if not conta_atual or conta_atual["perfil"] != "admin":
        raise PermissionError("Somente administradores podem baixar este relatório.")
    solicitacoes = carregar_solicitacoes_relatorio(data_inicial, data_final)
    return gerar_relatorio_excel(solicitacoes, kpis, filiais).getvalue()


def definir_selecao_catalogo(selecionar: bool) -> None:
    """Atualiza a coluna de seleção e reinicia o editor com o novo valor."""
    catalogo = st.session_state["df_catalogo"].copy()
    if catalogo.empty:
        return
    if "Selecionar" in catalogo.columns:
        catalogo["Selecionar"] = selecionar
        catalogo = catalogo[["Selecionar", *[col for col in catalogo.columns if col != "Selecionar"]]]
    else:
        catalogo.insert(0, "Selecionar", selecionar)
    st.session_state["df_catalogo"] = catalogo
    st.session_state["chave_editor"] += 1


def registrar_solicitacoes(sugestoes):
    """Registra o plano de transferências no banco local."""
    with st.spinner("Registrando solicitações..."):
        try:
            n, ignorados = gravar_novas_solicitacoes(
                sugestoes, st.session_state["usuario_nome"], df_produtos
            )
        except Exception as erro:
            st.error(f"Não foi possível registrar: {erro}")
            st.stop()
        st.session_state["sugestoes_temp"] = None
        if n:
            definir_selecao_catalogo(False)
        st.session_state["confirmacao_solicitacao"] = {"registradas": n, "ignoradas": ignorados}
        st.session_state["mostrar_dialogo_confirmacao"] = True
    st.rerun()


def texto_confirmacao_solicitacao(resultado: dict) -> str:
    registradas = resultado["registradas"]
    ignoradas = resultado["ignoradas"]
    if registradas == 1:
        mensagem = "1 solicitação registrada com sucesso."
    elif registradas > 1:
        mensagem = f"{registradas} solicitações registradas com sucesso."
    elif ignoradas == 1:
        mensagem = "A transferência já está pendente. Nenhuma nova solicitação foi registrada."
    elif ignoradas > 1:
        mensagem = f"As {ignoradas} transferências já estão pendentes. Nenhuma nova solicitação foi registrada."
    else:
        mensagem = "Nenhuma solicitação foi registrada. Revise as quantidades e as filiais."
    if registradas and ignoradas == 1:
        mensagem += " Uma transferência já estava pendente e não foi registrada novamente."
    elif registradas and ignoradas > 1:
        mensagem += f" {ignoradas} transferências já estavam pendentes e não foram registradas novamente."
    return mensagem


@st.dialog("Resultado da solicitação")
def dialog_resultado_solicitacao(resultado):
    mensagem = texto_confirmacao_solicitacao(resultado)
    if resultado["registradas"]:
        st.success(mensagem, icon=":material/check_circle:")
    else:
        st.warning(mensagem, icon=":material/info:")
    if st.button("Entendi", type="primary", width="stretch"):
        st.rerun()


@st.dialog("Revisar transferências")
def dialog_confirmar(sugestoes):
    df_rev = pd.DataFrame(sugestoes)
    df_rev = df_rev.merge(df_produtos[["SKU", "Desc_prod"]], on="SKU", how="left")
    df_rev["Origem"] = df_rev["Filial_Origem_ID"].map(MAPA_NOMES_FILIAIS)
    df_rev["Destino"] = df_rev["Filial_Destino_ID"].map(MAPA_NOMES_FILIAIS)

    total = int(df_rev["Quantidade"].sum())
    st.write(f"Confira as {len(sugestoes)} transferências ({total} peças) antes de registrar.")
    if READ_ONLY:
        st.info("O registro está desativado neste ambiente.")

    st.dataframe(
        df_rev[["Desc_prod", "Origem", "Destino", "Quantidade", "Motivo"]].rename(
            columns={"Desc_prod": "Produto"}
        ),
        hide_index=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Registrar solicitações", type="primary", icon=":material/check:", disabled=READ_ONLY):
            registrar_solicitacoes(sugestoes)
    with c2:
        if st.button("Voltar", icon=":material/arrow_back:"):
            st.rerun()


@st.dialog("Confirmar transferência de pontas")
def dialog_pontas(sugestoes):
    total = sum(i["Quantidade"] for i in sugestoes)
    st.write(f"Serão registradas {len(sugestoes)} transferências de pontas, com {total} peças entre as filiais.")
    if READ_ONLY:
        st.info("O registro está desativado neste ambiente.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Registrar transferências", type="primary", icon=":material/done_all:", disabled=READ_ONLY):
            with st.spinner("Registrando transferências..."):
                try:
                    n, ignorados = gravar_novas_solicitacoes(
                        sugestoes, st.session_state["usuario_nome"], df_produtos, pontas=True
                    )
                except Exception as erro:
                    st.error(f"Não foi possível registrar: {erro}")
                    st.stop()
                st.session_state["sugestoes_pontas_temp"] = None
            st.toast(f"{n} solicitações registradas; {ignorados} já pendentes", icon=":material/check_circle:")
            st.rerun()
    with c2:
        if st.button("Descartar sugestões"):
            st.session_state["sugestoes_pontas_temp"] = None
            st.rerun()


perfil = "Admin" if st.session_state["tipo_acesso"] == "admin" else "Compras"
nome = escape(st.session_state["usuario_nome"].title())

st.html(
    f"""
    <div class="app-header">
        <div class="brand">
            <div class="brand-logo-frame">
                <span style="font-size:32px;color:#ea5e39" aria-label="Remanejamento">⇄</span>
            </div>
            <div>
                <span class="eyebrow">{len(df_filiais)} Filiais</span>
                <h1>Remanejamento de estoque</h1>
                <span class="subtitle">Planeje transferências, acompanhe solicitações e recomponha pontas de grade.</span>
            </div>
        </div>
        <div class="meta">
            <span class="demo-chip">Portfólio</span>
            <div class="status-chip"><span class="dot"></span> {'Dados sintéticos · leitura' if READ_ONLY else 'Dados sintéticos'}</div>
            <div class="user-chip">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                    <circle cx="12" cy="8" r="3.5"/><path d="M5 20c.7-3.5 3.1-5.2 7-5.2s6.3 1.7 7 5.2"/>
                </svg>
                {nome} · {perfil}
            </div>
        </div>
    </div>
    """
)

opcoes_navegacao = ("Transferências", "Transferência de Pontas", "Auditoria")
if st.session_state.get("nav_principal") not in (None, *opcoes_navegacao):
    st.session_state.pop("nav_principal")

aba = st.segmented_control(
    "nav",
    options=list(opcoes_navegacao),
    default="Transferências",
    label_visibility="collapsed",
    key="nav_principal",
)

df_aud_quick = auditar_sugestoes(df_sugestoes, df_reais, df_produtos)
pend_count = (
    len(df_aud_quick[df_aud_quick["Status_Auditoria"] == "PENDENTE"])
    if not df_aud_quick.empty
    else 0
)

if aba == "Transferências":
    st.html(
        """
        <div class="page-intro">
            <div class="eyebrow">01 / Planejamento</div>
            <h2>Planejar transferências</h2>
            <p>Selecione produtos na tabela para montar um plano de transferência entre filiais.</p>
        </div>
        """
    )

    confirmacao = st.session_state.get("confirmacao_solicitacao")
    if confirmacao:
        mensagem = texto_confirmacao_solicitacao(confirmacao)
        if confirmacao["registradas"]:
            st.success(mensagem, icon=":material/check_circle:")
        else:
            st.warning(mensagem, icon=":material/info:")
        if st.session_state.pop("mostrar_dialogo_confirmacao", False):
            dialog_resultado_solicitacao(confirmacao)

    st.html(
        f"""
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="label">Total de SKUs</div>
                <div class="value">{len(df_produtos)}</div>
                <div class="delta">{df_produtos["Secao"].nunique()} departamentos</div>
            </div>
            <div class="kpi-card">
                <div class="label">Filiais</div>
                <div class="value">{len(df_filiais)}</div>
                <div class="delta">Filiais ativas</div>
            </div>
            <div class="kpi-card">
                <div class="label">Solicitações registradas</div>
                <div class="value">{len(df_sugestoes)}</div>
                <div class="delta">Últimos 30 dias</div>
            </div>
            <div class="kpi-card">
                <div class="label">Solicitações pendentes</div>
                <div class="value">{pend_count}</div>
            </div>
        </div>
        """
    )

    st.html('<div class="section-title">Filtros</div>')

    with st.expander("Filtros avançados"):
        setores = sorted(df_produtos["Secao"].dropna().astype(str).unique().tolist())
        setor = st.selectbox("Setor", ["Todos"] + setores, key="filtro_setor_catalogo")
        base_setor = df_produtos if setor == "Todos" else df_produtos[df_produtos["Secao"] == setor]
        cf1, cf2, cf3 = st.columns(3)
        with cf1:
            categoria = st.selectbox(
                "Categoria",
                ["Todas"] + sorted(base_setor["Categoria"].dropna().astype(str).unique()),
                key="filtro_categoria_catalogo",
            )
        with cf2:
            subgrupo = st.selectbox(
                "Subgrupo",
                ["Todos"] + sorted(base_setor["Subgrupo"].dropna().astype(str).unique()),
                key="filtro_subgrupo_catalogo",
            )
        with cf3:
            marca = st.selectbox(
                "Marca",
                ["Todas"] + sorted(base_setor["Marca"].dropna().astype(str).unique()),
                key="filtro_marca_catalogo",
            )

    col_busca, col_pesquisar, col_limpar = st.columns([3, 1, 1], vertical_alignment="bottom")
    with col_busca:
        termo = st.text_input(
            "Busca",
            placeholder="Busque por código pai, SKU ou nome do produto",
            label_visibility="collapsed",
            key="busca_catalogo",
        )
    with col_pesquisar:
        pesquisar = st.button("Pesquisar", type="primary", icon=":material/search:", width="stretch")
    with col_limpar:
        limpar = st.button("Limpar resultado", icon=":material/filter_alt_off:", width="stretch")

    filtros_atuais = (setor, categoria, marca, subgrupo, termo)
    if st.session_state.get("filtros_pesquisados") != filtros_atuais:
        st.session_state["df_catalogo"] = pd.DataFrame()
        st.session_state["filtros_pesquisados"] = None
        st.session_state["chave_editor"] += 1
    if limpar:
        st.session_state["df_catalogo"] = pd.DataFrame()
        st.session_state["chave_editor"] += 1
    if pesquisar:
        with st.spinner("Consultando estoque atual..."):
            st.session_state["df_catalogo"] = buscar_grade_unificada(
                setor, categoria, marca, subgrupo, termo.strip()
            )
        st.session_state["filtros_pesquisados"] = filtros_atuais
        st.session_state["chave_editor"] += 1

    df_cat = st.session_state["df_catalogo"].copy()
    if not df_cat.empty:
        if "Selecionar" not in df_cat.columns:
            df_cat.insert(0, "Selecionar", False)
        else:
            df_cat = df_cat[["Selecionar", *[col for col in df_cat.columns if col != "Selecionar"]]]

    st.html('<div class="section-title">Estoque por filial</div>')

    if df_cat.empty:
        mensagem = (
            "Nenhum produto encontrado com esses filtros."
            if st.session_state.get("filtros_pesquisados")
            else "Use Pesquisar para consultar o estoque atual."
        )
        st.info(mensagem, icon=":material/search:")
        skus_sel = []
    else:
        total_col, selecionar_col, desmarcar_col = st.columns(
            [3, 1.35, 1.35], vertical_alignment="center"
        )
        with total_col:
            st.caption(f"{len(df_cat)} SKUs no resultado")
        with selecionar_col:
            st.button(
                "Selecionar todos",
                icon=":material/check_box:",
                width="stretch",
                on_click=definir_selecao_catalogo,
                args=(True,),
            )
        with desmarcar_col:
            st.button(
                "Desmarcar todos",
                icon=":material/check_box_outline_blank:",
                width="stretch",
                on_click=definir_selecao_catalogo,
                args=(False,),
            )

        col_cfg = {
            "Selecionar": st.column_config.CheckboxColumn("", help="Marque para transferir"),
            "SKU": st.column_config.TextColumn("SKU", disabled=True),
            "Modelo": st.column_config.TextColumn("Modelo", disabled=True),
            "Produto": st.column_config.TextColumn("Produto", disabled=True, width="large"),
            "Cor": st.column_config.TextColumn("Cor", disabled=True),
            "Tamanho": st.column_config.TextColumn("Tam", disabled=True),
        }
        df_cat_visivel = df_cat.drop(columns=["Estoque Total"], errors="ignore")
        for lj in [c for c in df_cat_visivel.columns if c not in col_cfg and c != "Selecionar"]:
            col_cfg[lj] = st.column_config.NumberColumn(lj, format="%d", disabled=True)

        edited = st.data_editor(
            df_cat_visivel,
            column_config=col_cfg,
            disabled=[c for c in df_cat_visivel.columns if c != "Selecionar"],
            hide_index=True,
            height=340,
            key=f"grid_{st.session_state['chave_editor']}",
        )
        skus_sel = edited[edited["Selecionar"] == True]["SKU"].tolist()
        st.caption(f"{len(skus_sel)} de {len(df_cat)} SKUs selecionados")

    if not skus_sel:
        st.caption("Selecione produtos na tabela para planejar a transferência.")
    else:
        st.divider()
        st.html(f'<div class="section-title">Plano de transferência · {len(skus_sel)} SKUs selecionados</div>')

        estrategia = st.segmented_control(
            "Estratégia",
            ["Manual", "Concentrar", "Distribuir"],
            default="Concentrar",
            label_visibility="collapsed",
            key="estrategia_seg",
        )

        sugestoes = []
        erro = False

        if estrategia == "Concentrar":
            st.caption("Concentra o saldo na filial escolhida como polo de maior giro.")
            c1, c2 = st.columns(2)
            with c1:
                sel_or = st.selectbox("Origem", ["Toda a rede"] + opcoes_lojas, key="conc_origem")
                id_or = None if "Toda" in sel_or else filial_id(sel_or)
            with c2:
                sel_dest = st.selectbox("Destino", opcoes_lojas, key="conc_destino")
                id_dest = filial_id(sel_dest)

            if id_or and id_or == id_dest:
                st.error("Escolha filiais diferentes para origem e destino.", icon=":material/error:")
                erro = True
            else:
                sugestoes = gerar_transferencia_concentracao(skus_sel, id_dest, id_or)

        elif estrategia == "Distribuir":
            st.caption("Usa o giro dos últimos 60 dias e a cobertura em dias para equilibrar o estoque.")
            with st.expander("Parâmetros", expanded=True, icon=":material/tune:"):
                p1, p2 = st.columns(2)
                with p1:
                    est_min = st.number_input("Estoque Mínimo", min_value=0, value=4, key="dist_min")
                    dias_alerta = st.number_input(
                        "Alerta de falta (dias)", min_value=1, value=10, key="dist_alerta"
                    )
                with p2:
                    lote = st.number_input("Envio mínimo (peças)", min_value=1, value=2, key="dist_lote")
                    dias_alvo = st.number_input(
                        "Meta de abastecimento (dias)", min_value=1, value=25, key="dist_alvo"
                    )
                lojas = st.multiselect(
                    "Filiais participantes", opcoes_lojas, default=opcoes_lojas, key="dist_lojas"
                )

            ids_part = [filial_id(t) for t in lojas]
            if setor != "08-PERFUMARIA":
                st.warning(
                    "A distribuição cadenciada está habilitada para o setor 08-PERFUMARIA. Selecione-o no filtro Setor.",
                    icon=":material/warning:",
                )
                erro = True
            elif len(ids_part) < 2:
                st.warning("Selecione pelo menos duas filiais.", icon=":material/warning:")
                erro = True
            else:
                sugestoes = calcular_distribuicao_cadenciada(
                    skus_sel,
                    ids_part,
                    estoque_min_visual=est_min,
                    dias_alerta=dias_alerta,
                    dias_alvo=dias_alvo,
                    lote_minimo=lote,
                    setor_alvo=setor,
                )

        elif estrategia == "Manual":
            st.caption("Defina quantidades manualmente entre origem e destinos.")
            c1, c2 = st.columns(2)
            with c1:
                idx_padrao = opcoes_lojas.index("01-MATRIZ") if "01-MATRIZ" in opcoes_lojas else 0
                s_or = st.selectbox("Origem", opcoes_lojas, index=idx_padrao, key="man_or")
                i_or = filial_id(s_or)
            with c2:
                opts_d = [l for l in opcoes_lojas if filial_id(l) != i_or]
                s_dests = st.multiselect("Destinos", opts_d, default=[], key="man_dests")
                i_dests = [filial_id(t) for t in s_dests]

            if not i_dests:
                st.warning("Escolha uma filial de destino.", icon=":material/warning:")
                erro = True
            else:
                df_m = carregar_dados_para_editor(skus_sel, i_or, i_dests)
                if df_m.empty:
                    st.warning("Não há estoque disponível na origem para estes produtos.")
                    erro = True
                cfg_m = {
                    "SKU": st.column_config.TextColumn("SKU", disabled=True),
                    "Produto": st.column_config.TextColumn("Produto", disabled=True),
                    "Estoque Origem": st.column_config.NumberColumn("Saldo", disabled=True, format="%d"),
                }
                for fid in i_dests:
                    nm = MAPA_NOMES_FILIAIS.get(fid, f"Loja {fid}")
                    cfg_m[f"Estoque_{fid}"] = st.column_config.NumberColumn(
                        f"Est. {nm}", disabled=True, format="%d"
                    )
                    cfg_m[f"Qtd_Destino_{fid}"] = st.column_config.NumberColumn(
                        f"→ {nm}", min_value=0, max_value=1000, step=1
                    )

                df_ed = (
                    st.data_editor(
                        df_m,
                        column_config=cfg_m,
                        hide_index=True,
                        height=220,
                        key="manual_grid",
                    )
                    if not df_m.empty
                    else df_m
                )

                for _, row in df_ed.iterrows():
                    saldo = int(row["Estoque Origem"])
                    total_req = sum(int(row[f"Qtd_Destino_{f}"]) for f in i_dests)
                    if total_req > saldo:
                        st.error(
                            f"{row['Produto']}: quantidade solicitada ({total_req}) maior que o saldo ({saldo}).",
                            icon=":material/error:",
                        )
                        erro = True
                        break
                    if total_req > 0:
                        for fid in i_dests:
                            q = int(row[f"Qtd_Destino_{fid}"])
                            if q > 0:
                                sugestoes.append(
                                    {
                                        "SKU": str(row["SKU"]),
                                        "Filial_Origem_ID": i_or,
                                        "Filial_Destino_ID": fid,
                                        "Quantidade": q,
                                        "Motivo": "Manual",
                                    }
                                )

        if not erro:
            if not sugestoes:
                st.info(
                    "Nenhuma transferência sugerida para os produtos e parâmetros escolhidos.",
                    icon=":material/info:",
                )
            else:
                st.divider()

                df_tmp = pd.DataFrame(sugestoes)
                fluxos = (
                    df_tmp.groupby(["Filial_Origem_ID", "Filial_Destino_ID"])["Quantidade"]
                    .sum()
                    .reset_index()
                )

                cards_html = ""
                for _, r in fluxos.iterrows():
                    o = MAPA_NOMES_FILIAIS.get(r["Filial_Origem_ID"], f"Loja {r['Filial_Origem_ID']}")
                    d = MAPA_NOMES_FILIAIS.get(r["Filial_Destino_ID"], f"Loja {r['Filial_Destino_ID']}")
                    cards_html += f"""
                    <div class="flow-card">
                        <span class="node">{o}</span>
                        <span class="arrow">→</span>
                        <span class="badge">{int(r['Quantidade'])} pç</span>
                        <span class="arrow">→</span>
                        <span class="node">{d}</span>
                    </div>"""

                st.html(cards_html)

                acao_revisar, acao_direta = st.columns(2)
                with acao_revisar:
                    if st.button(
                        "Revisar transferências", type="primary", icon=":material/send:", width="stretch"
                    ):
                        dialog_confirmar(sugestoes)
                with acao_direta:
                    if st.button(
                        "Solicitar diretamente",
                        icon=":material/bolt:",
                        width="stretch",
                        disabled=READ_ONLY,
                    ):
                        registrar_solicitacoes(sugestoes)

elif aba == "Transferência de Pontas":
    st.html(
        """
        <div class="page-intro">
            <div class="eyebrow">02 / Recomposição</div>
            <h2>Transferência de Pontas</h2>
            <p>Encontre grades incompletas e revise a filial de destino sugerida pelo giro dos últimos 60 dias.</p>
        </div>
        """
    )
    st.html('<div class="section-title">Escolha os produtos</div>')
    st.caption("A busca considera grades com até dois tamanhos e três peças por filial.")

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            sec_p = st.selectbox(
                "Setor",
                ["Todos"] + sorted(df_produtos["Secao"].dropna().unique().tolist()),
                key="san_sec",
            )
        with c2:
            cat_p = st.selectbox(
                "Categoria",
                ["Todas"] + sorted(df_produtos["Categoria"].dropna().unique().tolist()),
                key="san_cat",
            )
        with c3:
            mar_p = st.selectbox(
                "Marca",
                ["Todas"] + sorted(df_produtos["Marca"].dropna().unique().tolist()),
                key="san_mar",
            )

        if st.button("Buscar pontas de grade", type="primary", icon=":material/radar:", width="stretch"):
            with st.spinner("Buscando pontas no estoque..."):
                df_alvo = df_produtos.copy()
                if sec_p != "Todos":
                    df_alvo = df_alvo[df_alvo["Secao"] == sec_p]
                if cat_p != "Todas":
                    df_alvo = df_alvo[df_alvo["Categoria"] == cat_p]
                if mar_p != "Todas":
                    df_alvo = df_alvo[df_alvo["Marca"] == mar_p]
                st.session_state["sugestoes_pontas_temp"] = calcular_concentracao_pontas(
                    df_alvo["SKU"].tolist()
                )

    if st.session_state.get("sugestoes_pontas_temp"):
        pontas = st.session_state["sugestoes_pontas_temp"]

        st.divider()
        st.markdown(f"{len(pontas)} transferências sugeridas entre as filiais.")

        df_pv = pd.DataFrame(pontas)
        df_pv = df_pv.merge(
            df_produtos[["SKU", "Desc_prod", "Cor", "Tamanho"]], on="SKU", how="left"
        )
        df_pv["Origem"] = df_pv["Filial_Origem_ID"].map(MAPA_NOMES_FILIAIS)
        df_pv["Destino"] = df_pv["Filial_Destino_ID"].map(MAPA_NOMES_FILIAIS)

        st.dataframe(
            df_pv[["Desc_prod", "Cor", "Tamanho", "Origem", "Destino", "Quantidade"]].rename(
                columns={"Desc_prod": "Produto"}
            ),
            hide_index=True,
            height=280,
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "Revisar transferências", type="primary", icon=":material/done_all:", width="stretch"
            ):
                dialog_pontas(pontas)
        with c2:
            if st.button("Descartar", icon=":material/close:", width="stretch"):
                st.session_state["sugestoes_pontas_temp"] = None
                st.rerun()

elif aba == "Auditoria":
    st.html(
        """
        <div class="page-intro">
            <div class="eyebrow">03 / Acompanhamento</div>
            <h2>Auditoria de transferências</h2>
            <p>Compare as quantidades solicitadas com as transferências realizadas nos últimos 30 dias.</p>
        </div>
        """
    )

    df_auditado = df_aud_quick.copy()
    if df_auditado.empty:
        st.info("Nenhuma solicitação registrada nos últimos 30 dias.", icon=":material/info:")
    else:
        c_f1, c_f2, c_f3 = st.columns([1.2, 1.2, 2])
        with c_f1:
            setores_aud = ["Todos"] + sorted(
                [str(x) for x in df_auditado["Secao"].dropna().unique() if x]
            )
            filtro_setor_aud = st.selectbox("Setor", setores_aud, key="aud_setor")
        with c_f2:
            status_opcoes = ["Todos", "PENDENTE", "CONCLUÍDA", "DIVERGENTE", "IGNORADO"]
            filtro_status_aud = st.selectbox("Status", status_opcoes, key="aud_status")
        with c_f3:
            busca_aud = st.text_input(
                "Buscar produto ou SKU",
                placeholder="Digite o SKU, código pai ou descrição",
                key="aud_busca",
            )

        if filtro_setor_aud != "Todos":
            df_auditado = df_auditado[df_auditado["Secao"] == filtro_setor_aud]
        if filtro_status_aud != "Todos":
            df_auditado = df_auditado[df_auditado["Status_Auditoria"] == filtro_status_aud]
        if busca_aud.strip():
            termo_aud = busca_aud.strip()
            df_auditado = df_auditado[
                df_auditado["SKU"].astype(str).str.contains(termo_aud, case=False, regex=False)
                | df_auditado["Desc_prod"].astype(str).str.contains(termo_aud, case=False, regex=False)
            ]

        total_solicitado = int(df_auditado["Quantidade_sugerida"].sum())
        total_realizado = int(df_auditado["Qtd_realizada_Final"].sum())
        df_pend_aud = df_auditado[df_auditado["Status_Auditoria"] == "PENDENTE"]
        pecas_pendentes = int(df_pend_aud["Quantidade_sugerida"].sum())
        df_div_aud = df_auditado[df_auditado["Status_Auditoria"] == "DIVERGENTE"]
        pecas_divergentes = int(df_div_aud["Quantidade_sugerida"].sum())

        if not df_pend_aud.empty:
            gargalo_id = int(
                df_pend_aud.groupby("Filial_origem_ID")["Quantidade_sugerida"].sum().idxmax()
            )
            nome_gargalo = MAPA_NOMES_FILIAIS.get(gargalo_id, f"Filial {gargalo_id}")
        else:
            nome_gargalo = "Nenhuma"

        st.html(
            f"""
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="label">Realizado / Solicitado</div>
                    <div class="value">{total_realizado} / {total_solicitado}</div>
                    <div class="delta">Peças no período filtrado</div>
                </div>
                <div class="kpi-card">
                    <div class="label">Peças pendentes</div>
                    <div class="value">{pecas_pendentes}</div>
                    <div class="delta">Aguardando emissão</div>
                </div>
                <div class="kpi-card">
                    <div class="label">Peças divergentes</div>
                    <div class="value">{pecas_divergentes}</div>
                    <div class="delta">Quantidade diferente da sugerida</div>
                </div>
                <div class="kpi-card">
                    <div class="label">Maior pendência</div>
                    <div class="value" style="font-size:1.25rem">{escape(str(nome_gargalo))}</div>
                    <div class="delta">Filial de origem</div>
                </div>
            </div>
            """
        )

        st.html('<div class="section-title">Solicitações auditadas</div>')
        if df_auditado.empty:
            st.info("Nenhum registro corresponde aos filtros selecionados.")
        else:
            df_exibir = df_auditado.copy()
            df_exibir["Origem"] = df_exibir["Filial_origem_ID"].map(MAPA_NOMES_FILIAIS)
            df_exibir["Destino"] = df_exibir["Filial_destino_ID"].map(MAPA_NOMES_FILIAIS)
            colunas_aud = [
                "Status_Auditoria",
                "Data_sugestao",
                "Origem",
                "Destino",
                "SKU",
                "Desc_prod",
                "Quantidade_sugerida",
                "Qtd_realizada_Final",
            ]
            st.dataframe(
                df_exibir[colunas_aud],
                hide_index=True,
                height=360,
                column_config={
                    "Status_Auditoria": st.column_config.TextColumn("Status", width="small"),
                    "Data_sugestao": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY"),
                    "Origem": st.column_config.TextColumn("Origem", width="medium"),
                    "Destino": st.column_config.TextColumn("Destino", width="medium"),
                    "SKU": st.column_config.TextColumn("SKU", width="medium"),
                    "Desc_prod": st.column_config.TextColumn("Produto", width="large"),
                    "Quantidade_sugerida": st.column_config.NumberColumn("Sugerido", format="%d"),
                    "Qtd_realizada_Final": st.column_config.NumberColumn("Realizado", format="%d"),
                },
            )

with st.sidebar:
    st.caption("Sessão")
    st.write(
        f"**{st.session_state['usuario_nome'].title()}** · "
        f"{'Admin' if st.session_state['tipo_acesso'] == 'admin' else 'Compras'}"
    )
    st.caption("Portfólio")
    if READ_ONLY:
        st.info("Somente leitura. Solicitações bloqueadas.")
    st.divider()
    st.caption("Filiais")
    for _, filial in df_filiais.iterrows():
        st.write(f"· {filial['Nome_filial']}")
    st.divider()
    with st.expander("Alterar minha senha"):
        with st.form("form_troca_voluntaria", enter_to_submit=False):
            senha_atual = st.text_input("Senha atual", type="password")
            nova_senha = st.text_input("Nova senha (mínimo 12 caracteres)", type="password")
            confirmar = st.text_input("Confirme a nova senha", type="password")
            salvar_senha = st.form_submit_button("Atualizar senha")
        if salvar_senha:
            if nova_senha != confirmar:
                st.error("As senhas não conferem.")
            else:
                try:
                    alterada = trocar_senha(st.session_state["usuario_id"], senha_atual, nova_senha)
                except ValueError as erro:
                    st.error(str(erro))
                except Exception:
                    st.error("Não foi possível atualizar a senha.")
                else:
                    if alterada:
                        revogar_sessao(st.session_state["auth_token"])
                        st.session_state["versao_senha"] += 1
                        st.session_state["auth_token"] = criar_sessao(
                            st.session_state["usuario_id"], st.session_state["versao_senha"]
                        )
                        st.session_state["cookie_pending"] = True
                        st.success("Senha atualizada.")
                        st.rerun()
                    else:
                        st.error("Senha atual incorreta.")
    if st.session_state["tipo_acesso"] == "admin":

        @st.fragment(run_every="10s")
        def mostrar_recuperacoes():
            with st.expander("Pedidos de recuperação"):
                cancelada = st.session_state.pop("recuperacao_cancelada", None)
                if cancelada:
                    st.success(f"Solicitação de {cancelada} cancelada.")
                try:
                    pedidos = recuperacoes_pendentes()
                except Exception:
                    st.error("Não foi possível consultar os pedidos.")
                    pedidos = []
                if not pedidos:
                    st.caption("Nenhum pedido pendente.")
                for pedido_id, usuario_pedido, data_pedido in pedidos:
                    st.write(f"**{usuario_pedido}** · {data_pedido:%d/%m/%Y %H:%M}")
                    st.caption("Confirme a identidade da pessoa antes de liberar a senha.")
                    with st.container(key=f"recuperacao_acoes_{pedido_id}"):
                        gerar, excluir = st.columns(2, gap="small")
                        with gerar:
                            if st.button(
                                "Gerar senha temporária", key=f"reset_{pedido_id}", width="stretch"
                            ):
                                try:
                                    temporaria = emitir_senha_temporaria(
                                        pedido_id, st.session_state["usuario_id"]
                                    )
                                except Exception:
                                    st.error("Não foi possível atender o pedido.")
                                else:
                                    if temporaria:
                                        st.session_state["senha_temporaria_exibida"] = (
                                            usuario_pedido,
                                            temporaria,
                                        )
                                        st.rerun(scope="fragment")
                                    else:
                                        st.info("Esse pedido já foi atendido.")
                        with excluir:
                            if st.button(
                                "Excluir solicitação", key=f"cancelar_{pedido_id}", width="stretch"
                            ):
                                try:
                                    cancelado = cancelar_recuperacao(
                                        pedido_id, st.session_state["usuario_id"]
                                    )
                                except Exception:
                                    st.error("Não foi possível cancelar a solicitação.")
                                else:
                                    if cancelado:
                                        st.session_state["recuperacao_cancelada"] = usuario_pedido
                                        st.rerun(scope="fragment")
                                    else:
                                        st.info("Essa solicitação não está mais pendente.")
                pendente = st.session_state.get("senha_temporaria_exibida")
                if pendente:
                    st.warning(
                        f"Copie a senha de {pendente[0]} e entregue diretamente à pessoa. "
                        "Ela não ficará registrada em texto legível."
                    )
                    st.code(pendente[1])
                    if st.button("Ocultar senha temporária", key="ocultar_senha_temporaria"):
                        del st.session_state["senha_temporaria_exibida"]
                        st.rerun(scope="fragment")

        mostrar_recuperacoes()
        with st.expander("Baixar relatorio"):
            hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
            data_inicial = st.date_input(
                "Data inicial",
                value=hoje,
                max_value=hoje,
                format="DD/MM/YYYY",
                key="relatorio_data_inicial",
            )
            data_final = st.date_input(
                "Data final",
                value=hoje,
                max_value=hoje,
                format="DD/MM/YYYY",
                key="relatorio_data_final",
            )
            periodo_valido = data_inicial <= data_final
            if not periodo_valido:
                st.warning("A data inicial deve ser anterior ou igual à data final.")
            st.download_button(
                "Baixar",
                data=partial(
                    bytes_relatorio_periodo,
                    data_inicial,
                    data_final,
                    st.session_state["auth_token"],
                    df_kpis_base,
                    df_filiais,
                ),
                file_name=f"Remanejamento_{data_inicial:%d-%m-%Y}_a_{data_final:%d-%m-%Y}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                icon=":material/download:",
                width="stretch",
                disabled=not periodo_valido,
                on_click="ignore",
            )
    st.divider()
    if st.button("Desconectar", icon=":material/logout:", width="stretch"):
        revogar_sessao(st.session_state["auth_token"])
        st.session_state.clear()
        st.rerun()


@st.dialog("Guia do aplicativo", width="large", dismissible=False)
def mostrar_guia():
    etapas = etapas_para(st.session_state["tipo_acesso"])
    indice = max(0, min(st.session_state.get("guia_etapa", 0), len(etapas) - 1))
    titulo, descricao = etapas[indice]
    st.caption(f"ETAPA {indice + 1} DE {len(etapas)}")
    st.progress((indice + 1) / len(etapas))
    st.subheader(titulo)
    st.write(descricao)

    voltar, proximo, fechar = st.columns([1, 1, 1.3], vertical_alignment="bottom")
    with voltar:
        if st.button(
            "Voltar",
            icon=":material/arrow_back:",
            disabled=indice == 0,
            width="stretch",
            key="guia_voltar",
        ):
            st.session_state["guia_etapa"] = indice - 1
            st.rerun(scope="fragment")
    with proximo:
        if indice < len(etapas) - 1 and st.button(
            "Próximo",
            icon=":material/arrow_forward:",
            type="primary",
            width="stretch",
            key="guia_proximo",
        ):
            st.session_state["guia_etapa"] = indice + 1
            st.rerun(scope="fragment")
    with fechar:
        rotulo = "Concluir" if indice == len(etapas) - 1 else "Fechar guia"
        if st.button(rotulo, width="stretch", key="guia_fechar"):
            try:
                marcar_guia_visto(st.session_state["usuario_id"], VERSAO_GUIA)
            except Exception:
                st.error("Não foi possível salvar que você viu o guia. Tente novamente.")
            else:
                st.session_state["guia_etapa"] = 0
                st.rerun()


with st.container(key="ajuda_flutuante"):
    abrir_guia = st.button(
        "Ajuda",
        icon=":material/help_outline:",
        help="Abrir o guia do aplicativo",
        key="abrir_guia",
    )

if abrir_guia:
    st.session_state["guia_etapa"] = 0
if abrir_guia or conta["versao_guia"] < VERSAO_GUIA:
    mostrar_guia()
