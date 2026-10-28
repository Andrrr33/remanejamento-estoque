"""Camada de acesso a dados locais, gravação de solicitações e exportação Excel."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import io
import re
from typing import Any, Sequence
from uuid import uuid4

import pandas as pd

from auth import exigir_usuario
from banco_local import conectar
from calculos import auditar_sugestoes as _auditar
from dados_demo import FILIAIS, estoque_vendas, produtos, realizadas

READ_ONLY = False


def _solicitacoes() -> pd.DataFrame:
    with conectar() as db:
        return pd.read_sql_query(
            """
            SELECT Data_sugestao, Execucao_ID, SKU, Prod_pai, Cor,
                   Filial_origem_ID, Filial_destino_ID, Quantidade_sugerida,
                   Status, Observacoes
            FROM solicitacoes
            """,
            db,
            parse_dates=["Data_sugestao"],
        )


def carregar_dados_do_banco() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    exigir_usuario()
    sugestoes = _solicitacoes()
    sugestoes = sugestoes[sugestoes.Data_sugestao >= datetime.now() - timedelta(days=30)]
    kpis = estoque_vendas()[["SKU", "FilialID", "Secao", "Categoria", "Estoque"]].rename(
        columns={"Estoque": "Estoque_Atual"}
    )
    filiais = pd.DataFrame([{"FilialID": i, "Nome_filial": nome} for i, nome in FILIAIS.items()])
    return sugestoes, realizadas(), produtos(), filiais, kpis


def buscar_grade_unificada(
    setor: str = "Todos",
    categoria: str = "Todas",
    marca: str = "Todas",
    subgrupo: str = "Todos",
    termo_busca: str = "",
) -> pd.DataFrame:
    exigir_usuario()
    base = estoque_vendas()
    filtros = [
        ("Secao", setor, "Todos"),
        ("Categoria", categoria, "Todas"),
        ("Marca", marca, "Todas"),
        ("Subgrupo", subgrupo, "Todos"),
    ]
    for col, valor, padrao in filtros:
        if valor != padrao:
            base = base[base[col].eq(valor)]

    termo = termo_busca.strip()
    if termo:
        codigo = re.match(r"^(\d{14}|\d{8})(?!\d)", termo)
        if codigo:
            coluna = "SKU" if len(codigo[1]) == 14 else "Prod_pai"
            base = base[base[coluna].eq(codigo[1])]
        else:
            base = base[base.Desc_prod.str.contains(termo, case=False, regex=False)]

    if base.empty:
        return pd.DataFrame()

    grade = base.pivot(
        index=["SKU", "Prod_pai", "Desc_prod", "Cor", "Tamanho"],
        columns="FilialID",
        values="Estoque",
    ).reset_index()
    grade.columns.name = None
    grade = grade.rename(columns={**FILIAIS, "Prod_pai": "Modelo", "Desc_prod": "Produto"})
    grade["Estoque Total"] = grade[list(FILIAIS.values())].sum(axis=1)
    return grade.sort_values("Estoque Total", ascending=False).reset_index(drop=True)


def carregar_dados_para_editor(
    sku_lista: Sequence[str],
    id_origem: int,
    ids_destinos: Sequence[int],
) -> pd.DataFrame:
    exigir_usuario()
    base = estoque_vendas()
    base = base[base.SKU.isin(sku_lista)]
    if base.empty:
        return pd.DataFrame()

    grade = base.pivot(
        index=["SKU", "Desc_prod"],
        columns="FilialID",
        values="Estoque",
    ).reset_index()
    grade["Estoque Origem"] = grade[id_origem]
    cols = ["SKU", "Desc_prod", "Estoque Origem"]
    for fid in ids_destinos:
        grade[f"Estoque_{fid}"] = grade[fid]
        grade[f"Qtd_Destino_{fid}"] = 0
        cols.extend([f"Estoque_{fid}", f"Qtd_Destino_{fid}"])
    grade.columns.name = None
    return grade[cols].rename(columns={"Desc_prod": "Produto"})


def auditar_sugestoes(
    sugestoes: pd.DataFrame,
    reais: pd.DataFrame,
    df_produtos: pd.DataFrame,
) -> pd.DataFrame:
    cols = ["Desc_prod", "Secao", "Categoria", "Marca", "Subgrupo", "Ref_fornecedor"]
    faltantes = [col for col in cols if col not in sugestoes.columns]
    base = (
        sugestoes.merge(df_produtos[["SKU", *faltantes]], on="SKU", how="left")
        if faltantes and not df_produtos.empty
        else sugestoes.copy()
    )
    return _auditar(base, reais)


def gravar_novas_solicitacoes(
    sugestoes: Sequence[dict[str, Any]],
    usuario_nome: str,
    df_produtos: pd.DataFrame,
    pontas: bool = False,
) -> tuple[int, int]:
    conta = exigir_usuario()
    if conta["trocar_senha"]:
        raise PermissionError("Defina sua nova senha antes de registrar solicitações.")

    saldo = estoque_vendas().set_index(["SKU", "FilialID"]).Estoque.to_dict()
    metadados = df_produtos.set_index("SKU").to_dict("index")
    agora = datetime.now()
    lote = str(uuid4())
    registros = 0
    ignorados = 0

    with conectar() as db:
        db.execute("BEGIN IMMEDIATE")
        limite = "" if pontas else " AND Data_sugestao >= ?"
        params = () if pontas else ((agora - timedelta(days=10)).isoformat(),)
        pendentes = {
            (r[0], r[1], r[2])
            for r in db.execute(
                "SELECT SKU, Filial_origem_ID, Filial_destino_ID "
                f"FROM solicitacoes WHERE Status = 'PENDENTE'{limite}",
                params,
            )
        }
        for item in sugestoes:
            sku = str(item["SKU"])
            origem = int(item["Filial_Origem_ID"])
            destino = int(item["Filial_Destino_ID"])
            quantidade = item["Quantidade"]
            qtd = int(quantidade)
            if quantidade != qtd or qtd < 0:
                raise ValueError("Informe quantidades inteiras e positivas.")
            if origem not in FILIAIS or destino not in FILIAIS or origem == destino or sku not in metadados:
                raise ValueError("Produto ou filiais inválidos.")
            if qtd == 0:
                continue
            chave = (sku, origem, destino)
            if chave in pendentes:
                ignorados += 1
                continue
            if qtd > saldo[(sku, origem)]:
                raise ValueError("A quantidade solicitada ultrapassa o estoque da origem.")
            saldo[(sku, origem)] -= qtd
            info = metadados[sku]
            db.execute(
                """
                INSERT INTO solicitacoes (
                    Data_sugestao, Execucao_ID, SKU, Prod_pai, Cor,
                    Filial_origem_ID, Filial_destino_ID, Quantidade_sugerida,
                    Status, Observacoes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agora.isoformat(),
                    lote,
                    sku,
                    info["Prod_pai"],
                    info["Cor"],
                    origem,
                    destino,
                    qtd,
                    "PENDENTE",
                    f"{conta['username']} | {item.get('Motivo', 'Manual')}",
                ),
            )
            pendentes.add(chave)
            registros += 1
    return registros, ignorados


def carregar_solicitacoes_relatorio(data_inicial: date, data_final: date) -> pd.DataFrame:
    exigir_usuario(admin=True)
    if data_inicial > data_final:
        raise ValueError("A data inicial deve ser anterior ou igual à data final.")
    base = _solicitacoes()
    base = base[base.Data_sugestao.dt.date.between(data_inicial, data_final)]
    return base.merge(
        produtos()[["SKU", "Desc_prod", "Secao", "Ref_fornecedor"]],
        on="SKU",
        how="left",
    )


def gerar_relatorio_excel(
    auditado: pd.DataFrame,
    kpis: pd.DataFrame,
    filiais: pd.DataFrame,
) -> io.BytesIO:
    """Gera o relatório em Excel separado por filial de origem."""
    buffer = io.BytesIO()
    opcoes_xlsx = {"options": {"strings_to_formulas": False, "strings_to_urls": False}}
    with pd.ExcelWriter(buffer, engine="xlsxwriter", engine_kwargs=opcoes_xlsx) as writer:
        workbook = writer.book
        header = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#231f1d",
                "font_color": "#ffffff",
                "align": "center",
                "border": 1,
            }
        )
        destino_fmt = workbook.add_format({"bg_color": "#fce8dc", "num_format": "#,##0"})
        for _, filial in filiais.sort_values("FilialID").iterrows():
            origem_id = int(filial["FilialID"])
            origem_nome = str(filial["Nome_filial"])
            destinos = [
                str(r["Nome_filial"])
                for _, r in filiais.iterrows()
                if int(r["FilialID"]) != origem_id
            ]
            colunas = ["Filial", "REF", "Produto", "Secao", "Estoque"] + destinos
            linhas = auditado[auditado["Filial_origem_ID"] == origem_id].copy()
            if not linhas.empty:
                estoque = kpis[kpis["FilialID"] == origem_id][["SKU", "Estoque_Atual"]]
                linhas = linhas.merge(estoque, on="SKU", how="left")
                linhas["Estoque_Atual"] = (
                    pd.to_numeric(linhas["Estoque_Atual"], errors="coerce")
                    .fillna(0)
                    .clip(lower=0)
                    .astype(int)
                )
                linhas["Ref_fornecedor"] = linhas["Ref_fornecedor"].fillna(linhas["SKU"])
                mapa = dict(zip(filiais["FilialID"].astype(int), filiais["Nome_filial"]))
                linhas["Nome_Destino"] = linhas["Filial_destino_ID"].map(mapa)
                tabela = linhas.pivot_table(
                    index=["Ref_fornecedor", "Desc_prod", "Secao", "Estoque_Atual"],
                    columns="Nome_Destino",
                    values="Quantidade_sugerida",
                    aggfunc="sum",
                    fill_value=0,
                ).reset_index()
                tabela.columns.name = None
                for nome in destinos:
                    if nome not in tabela.columns:
                        tabela[nome] = 0
                tabela = tabela[tabela[destinos].sum(axis=1) > 0]
                tabela.insert(0, "Filial", origem_nome)
                tabela = tabela.rename(
                    columns={
                        "Ref_fornecedor": "REF",
                        "Desc_prod": "Produto",
                        "Estoque_Atual": "Estoque",
                    }
                ).reindex(columns=colunas)
            else:
                tabela = pd.DataFrame(columns=colunas)

            aba_nome = origem_nome[:31]
            tabela.to_excel(writer, sheet_name=aba_nome, index=False, startrow=1)
            sheet = writer.sheets[aba_nome]
            sheet.merge_range(0, 5, 0, 7, f"{origem_nome} para destinos", header)
            for col, name in enumerate(colunas):
                sheet.write(1, col, name, header)
                sheet.set_column(col, col, 48 if name == "Produto" else 18)
                if col >= 5:
                    sheet.set_column(col, col, 20, destino_fmt)
            sheet.freeze_panes(2, 0)
    buffer.seek(0)
    return buffer
