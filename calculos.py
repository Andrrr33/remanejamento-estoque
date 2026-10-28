"""Algoritmos de cálculo de transferências, recomposição de pontas e auditoria."""
from __future__ import annotations

import os
from typing import Any, Sequence

import numpy as np
import pandas as pd

from dados_demo import dados_calculo


def gerar_transferencia_concentracao(
    sku_lista: Sequence[str],
    id_loja_destino: int,
    id_loja_origem: int | None = None,
) -> list[dict[str, Any]]:
    sugestoes: list[dict[str, Any]] = []
    df_estoque_total = dados_calculo(sku_lista).rename(columns={"Estoque": "Quantidade_Estoque"})
    if id_loja_origem is not None:
        df_estoque_total = df_estoque_total[df_estoque_total.FilialID == id_loja_origem]
    if df_estoque_total.empty:
        return []

    for _, row in df_estoque_total.iterrows():
        origem_id = int(row["FilialID"])
        qtd_estoque = int(row["Quantidade_Estoque"])
        if origem_id == int(id_loja_destino) or qtd_estoque <= 0:
            continue

        sugestoes.append(
            {
                "SKU": str(row["SKU"]),
                "Filial_Origem_ID": origem_id,
                "Filial_Destino_ID": int(id_loja_destino),
                "Quantidade": qtd_estoque,
                "Motivo": "Concentração de Estoque",
            }
        )

    return sugestoes


def calcular_concentracao_pontas(sku_lista: Sequence[str]) -> list[dict[str, Any]]:
    sugestoes: list[dict[str, Any]] = []
    df_dados = dados_calculo(sku_lista, grade_completa=True)
    if df_dados.empty:
        return []

    df_dados["SKU"] = df_dados["SKU"].astype(str)
    df_dados["FilialID"] = df_dados["FilialID"].astype(int)
    df_dados["Estoque"] = pd.to_numeric(df_dados["Estoque"]).fillna(0).clip(lower=0)
    df_dados["Vendas_60d"] = pd.to_numeric(df_dados["Vendas_60d"]).fillna(0).clip(lower=0)

    loja_padrao = int(os.getenv("FILIAL_PADRAO_ID", "2"))
    peso_hierarquia = {2: 4, 3: 3, 1: 2, 4: 1}

    grupos = df_dados.groupby(["Prod_pai", "Cor"])

    for (_, _), df_grupo in grupos:
        if df_grupo["Tamanho"].nunique() <= 1:
            continue

        resumo_lojas = (
            df_grupo[df_grupo["Estoque"] > 0]
            .groupby("FilialID")
            .agg(
                Total_Estoque=("Estoque", "sum"),
                Tamanhos_Distintos=("Tamanho", "nunique"),
                Tamanhos_Lista=("Tamanho", lambda x: set(x)),
            )
            .reset_index()
        )

        vendas_lojas = df_grupo.groupby("FilialID")["Vendas_60d"].max().reset_index()

        doadoras = resumo_lojas[
            (resumo_lojas["Tamanhos_Distintos"] <= 2) & (resumo_lojas["Total_Estoque"] <= 3)
        ]

        if doadoras.empty:
            continue

        df_itens_doacao = df_grupo[
            (df_grupo["FilialID"].isin(doadoras["FilialID"])) & (df_grupo["Estoque"] > 0)
        ]

        tamanhos_doados = set(df_itens_doacao["Tamanho"].unique())
        vendas_totais_grade = vendas_lojas["Vendas_60d"].sum()

        id_destino: int | None = None

        if vendas_totais_grade == 0:
            id_destino = loja_padrao
        else:
            vendas_lojas["Peso_Desempate"] = vendas_lojas["FilialID"].map(peso_hierarquia).fillna(0)
            potenciais_destinos = vendas_lojas.sort_values(
                by=["Vendas_60d", "Peso_Desempate"],
                ascending=[False, False],
            )

            for _, row_destino in potenciais_destinos.iterrows():
                cand_id = int(row_destino["FilialID"])

                tamanhos_destino: set[str] = set()
                if cand_id in resumo_lojas["FilialID"].values:
                    tamanhos_destino = resumo_lojas[resumo_lojas["FilialID"] == cand_id][
                        "Tamanhos_Lista"
                    ].iloc[0]

                tamanhos_finais = tamanhos_destino.union(tamanhos_doados)

                if len(tamanhos_finais) >= 2:
                    id_destino = cand_id
                    break

            if id_destino is None:
                id_destino = loja_padrao

        for _, item in df_itens_doacao.iterrows():
            f_origem = int(item["FilialID"])

            if f_origem != id_destino:
                sugestoes.append(
                    {
                        "SKU": str(item["SKU"]),
                        "Filial_Origem_ID": f_origem,
                        "Filial_Destino_ID": id_destino,
                        "Quantidade": int(item["Estoque"]),
                        "Motivo": "Concentração de Pontas de Grade",
                    }
                )

    return sugestoes


def calcular_distribuicao_cadenciada(
    sku_lista: Sequence[str],
    ids_lojas_participantes: Sequence[int],
    estoque_min_visual: int,
    dias_alerta: int,
    dias_alvo: int,
    lote_minimo: int,
    setor_alvo: str,
) -> list[dict[str, Any]]:
    sugestoes: list[dict[str, Any]] = []
    df_dados = dados_calculo(sku_lista)
    df_dados = df_dados[
        df_dados.FilialID.isin(ids_lojas_participantes) & df_dados.Secao.eq(setor_alvo)
    ]
    if df_dados.empty:
        return []

    df_dados["SKU"] = df_dados["SKU"].astype(str)
    df_dados["FilialID"] = df_dados["FilialID"].astype(int)
    df_dados["Estoque"] = pd.to_numeric(df_dados["Estoque"]).fillna(0).clip(lower=0)
    df_dados["Vendas_60d"] = pd.to_numeric(df_dados["Vendas_60d"]).fillna(0).clip(lower=0)

    df_dados_por_sku = {sku: grupo for sku, grupo in df_dados.groupby("SKU")}

    for sku in sku_lista:
        df_sku = df_dados_por_sku.get(str(sku), pd.DataFrame()).copy()
        if df_sku.empty:
            continue

        df_sku["Venda_Diaria"] = df_sku["Vendas_60d"] / 60
        df_sku["Dias_Cobertura"] = df_sku.apply(
            lambda row: row["Estoque"] / row["Venda_Diaria"] if row["Venda_Diaria"] > 0 else 999,
            axis=1,
        )

        recebedoras = df_sku[df_sku["Dias_Cobertura"] < dias_alerta].copy()
        recebedoras["Necessidade"] = np.ceil(
            (recebedoras["Venda_Diaria"] * dias_alvo) - recebedoras["Estoque"]
        )
        recebedoras = recebedoras[recebedoras["Necessidade"] > 0].sort_values(
            "Necessidade", ascending=False
        )

        doadoras = df_sku[df_sku["Estoque"] > estoque_min_visual].copy()
        doadoras["Estoque_Disponivel"] = doadoras["Estoque"] - estoque_min_visual
        doadoras = doadoras[doadoras["Estoque_Disponivel"] >= lote_minimo].sort_values(
            "Estoque_Disponivel", ascending=False
        )

        for _, rec in recebedoras.iterrows():
            id_destino = int(rec["FilialID"])
            necessidade = float(rec["Necessidade"])

            for idx, doa in doadoras.iterrows():
                if necessidade <= 0:
                    break

                id_origem = int(doa["FilialID"])
                disponivel = float(doa["Estoque_Disponivel"])

                if disponivel >= lote_minimo and id_origem != id_destino:
                    qtd_transferir = min(necessidade, disponivel)

                    sugestoes.append(
                        {
                            "SKU": str(sku),
                            "Filial_Origem_ID": id_origem,
                            "Filial_Destino_ID": id_destino,
                            "Quantidade": int(qtd_transferir),
                            "Motivo": "Distribuição (EM TESTE)",
                        }
                    )

                    necessidade -= qtd_transferir
                    doadoras.at[idx, "Estoque_Disponivel"] -= qtd_transferir

    return sugestoes


def auditar_sugestoes(df_sugestoes: pd.DataFrame, df_reais: pd.DataFrame) -> pd.DataFrame:
    if df_sugestoes.empty:
        df_auditado = df_sugestoes.copy()
        df_auditado["Status_Auditoria"] = None
        df_auditado["Qtd_realizada_Final"] = 0
        df_auditado["Data_emissao"] = None
        df_auditado["Quantidade_realizada"] = 0
        return df_auditado

    df_sug = df_sugestoes.copy()
    df_sug["Data_sugestao"] = pd.to_datetime(df_sug["Data_sugestao"])

    if df_reais.empty:
        df_auditado = df_sug.copy()
        df_auditado["Data_emissao"] = pd.NaT
        df_auditado["Quantidade_realizada"] = 0
        dias_passados = (
            pd.Timestamp.now().normalize() - df_auditado["Data_sugestao"].dt.normalize()
        ).dt.days
        df_auditado["Status_Auditoria"] = np.where(dias_passados > 10, "IGNORADO", "PENDENTE")
        df_auditado["Qtd_realizada_Final"] = 0
        return df_auditado

    df_rea = df_reais.copy()
    df_rea["Data_emissao"] = pd.to_datetime(df_rea["Data_emissao"])

    df_merge = pd.merge(
        df_sug,
        df_rea,
        on=["SKU", "Filial_origem_ID", "Filial_destino_ID"],
        how="left",
        suffixes=("_sugerido", "_realizado"),
    )

    emissao_valida = df_merge["Data_emissao"].notna() & (
        df_merge["Data_emissao"] >= (df_merge["Data_sugestao"] - pd.Timedelta(hours=2))
    )

    df_merge.loc[~emissao_valida, "Data_emissao"] = pd.NaT
    df_merge.loc[~emissao_valida, "Quantidade_realizada"] = np.nan

    cols_sug = [c for c in df_sug.columns if c in df_merge.columns]
    df_auditado = (
        df_merge.sort_values("Data_emissao")
        .groupby(cols_sug, as_index=False, dropna=False)
        .agg({"Data_emissao": "last", "Quantidade_realizada": "sum"})
    )

    tem_emissao = df_auditado["Data_emissao"].notna()
    qtd_igual = df_auditado["Quantidade_sugerida"] == df_auditado["Quantidade_realizada"]

    dias_passados = (
        pd.Timestamp.now().normalize() - df_auditado["Data_sugestao"].dt.normalize()
    ).dt.days

    status = np.where(
        tem_emissao & qtd_igual,
        "CONCLUÍDA",
        np.where(
            tem_emissao,
            "DIVERGENTE",
            np.where(dias_passados > 10, "IGNORADO", "PENDENTE"),
        ),
    )
    df_auditado["Status_Auditoria"] = status
    df_auditado["Qtd_realizada_Final"] = pd.to_numeric(
        df_auditado["Quantidade_realizada"], errors="coerce"
    ).fillna(0)

    return df_auditado
