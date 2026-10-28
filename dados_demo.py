"""Massa sintética de produtos, estoques, vendas e transferências."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd

from banco_local import conectar

FILIAIS: dict[int, str] = {
    1: "01-MATRIZ",
    2: "02-LOJA CENTRO",
    3: "03-LOJA SUL",
    4: "04-LOJA NORTE",
}


def produtos() -> pd.DataFrame:
    modelos = [
        ("91000001", "CAMISETA ALGODÃO", "01-MASCULINO", "Vestuário", "Camisetas", "Aurora"),
        ("91000002", "BLUSA LINHO", "02-FEMININO", "Vestuário", "Blusas", "Horizonte"),
        ("91000003", "TÊNIS CASUAL", "03-CALÇADOS", "Calçados", "Tênis", "Passo"),
        ("91000004", "CALDEIRÃO INOX", "04-CASA", "Utilidades", "Panelas", "Lar"),
        ("91000005", "COLÔNIA BRISA", "08-PERFUMARIA", "Perfumaria", "Colônias", "Brisa"),
        ("91000006", "HIDRATANTE FLORAL", "08-PERFUMARIA", "Perfumaria", "Hidratantes", "Brisa"),
        ("91000007", "CALÇA SARJA", "01-MASCULINO", "Vestuário", "Calças", "Aurora"),
        ("91000008", "SANDÁLIA CONFORTO", "03-CALÇADOS", "Calçados", "Sandálias", "Passo"),
    ]
    rows: list[dict[str, str]] = []
    for pai, nome, secao, categoria, subgrupo, marca in modelos:
        if secao in ("01-MASCULINO", "02-FEMININO"):
            tamanhos = ["P", "M", "G", "GG"]
        elif secao == "03-CALÇADOS":
            tamanhos = ["36", "38", "40", "42"]
        else:
            tamanhos = ["ÚN"]

        for cor_id, cor in enumerate(["AREIA", "AZUL"], start=1):
            for tam_id, tamanho in enumerate(tamanhos, start=1):
                sku = f"{pai}{cor_id:02d}{tam_id:04d}"
                rows.append(
                    {
                        "SKU": sku,
                        "Prod_pai": pai,
                        "Desc_prod": f"{sku} - {nome} {cor} {tamanho}",
                        "Secao": secao,
                        "Categoria": categoria,
                        "Subgrupo": subgrupo,
                        "Marca": marca,
                        "Ref_fornecedor": f"DEM-{pai[-3:]}",
                        "Cor": cor,
                        "Tamanho": tamanho,
                    }
                )
    return pd.DataFrame(rows)


def estoque_vendas() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for i, prod in produtos().iterrows():
        tamanho = int(prod.SKU[-4:])
        for filial in FILIAIS:
            if prod.Secao == "08-PERFUMARIA":
                saldo, vendas = {
                    1: (40, 5),
                    2: (2, 60),
                    3: (1, 42),
                    4: (12, 8),
                }[filial]
            else:
                saldo = {
                    1: 8 + (i % 6),
                    2: 4 + (i % 5),
                    3: 1 if tamanho in (1, 2) else 0,
                    4: 0 if tamanho > 1 else 2,
                }[filial]
                vendas = {1: 8, 2: 24, 3: 4, 4: 2}[filial] + (i % 3)

            rows.append(
                {
                    **prod.to_dict(),
                    "FilialID": filial,
                    "Estoque": saldo,
                    "Vendas_60d": vendas,
                }
            )
    return pd.DataFrame(rows)


def dados_calculo(skus: Iterable[str], grade_completa: bool = False) -> pd.DataFrame:
    base = estoque_vendas()
    selecionados = base[base.SKU.isin([str(s) for s in skus])]
    if not grade_completa:
        return selecionados.copy()

    grupos = selecionados[["Prod_pai", "Cor"]].drop_duplicates()
    grade = base.merge(grupos, on=["Prod_pai", "Cor"])
    grade["Vendas_60d"] = grade.groupby(["Prod_pai", "Cor", "FilialID"])["Vendas_60d"].transform("sum")
    return grade


def data_base() -> datetime:
    with conectar() as db:
        db.execute(
            "INSERT OR IGNORE INTO metadados VALUES (?, ?)",
            ("data_base", datetime.now().isoformat()),
        )
        valor = db.execute("SELECT valor FROM metadados WHERE chave = 'data_base'").fetchone()[0]
        return datetime.fromisoformat(valor)


def preparar_solicitacoes() -> None:
    inicio = data_base()
    with conectar() as db:
        if db.execute("SELECT 1 FROM metadados WHERE chave = 'seed_solicitacoes'").fetchone():
            return
        for i, prod in produtos().head(12).iterrows():
            status = "PENDENTE" if i % 3 == 0 else "CONCLUIDO"
            db.execute(
                """
                INSERT INTO solicitacoes (
                    Data_sugestao, Execucao_ID, SKU, Prod_pai, Cor,
                    Filial_origem_ID, Filial_destino_ID, Quantidade_sugerida,
                    Status, Observacoes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (inicio - timedelta(days=i % 15 + 1)).isoformat(),
                    f"DEMO-{i:03}",
                    prod.SKU,
                    prod.Prod_pai,
                    prod.Cor,
                    1,
                    2,
                    2 + i % 3,
                    status,
                    "Exemplo demonstrativo",
                ),
            )
        db.execute("INSERT INTO metadados VALUES ('seed_solicitacoes', '1')")


def realizadas() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    inicio = data_base()
    for i, prod in produtos().head(12).iterrows():
        if i % 3:
            rows.append(
                {
                    "Data_emissao": inicio - timedelta(days=i % 15),
                    "SKU": prod.SKU,
                    "Filial_origem_ID": 1,
                    "Filial_destino_ID": 2,
                    "Quantidade_realizada": 2 + i % 3 - (1 if i % 3 == 2 else 0),
                }
            )
    return pd.DataFrame(rows)


preparar_solicitacoes()
