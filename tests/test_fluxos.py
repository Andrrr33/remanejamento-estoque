from datetime import date, timedelta
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import auth
import banco_local
from calculos import (
    calcular_concentracao_pontas,
    calcular_distribuicao_cadenciada,
    gerar_transferencia_concentracao,
)
import dados_demo
import real_data


class Fluxos(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.antigo = banco_local.DB_PATH
        banco_local.DB_PATH = Path(self.tmp.name) / "dados" / "teste.sqlite3"
        banco_local.preparar_schema()
        auth.preparar_contas()
        dados_demo.preparar_solicitacoes()
        self.admin = auth.autenticar("ADMINDEMO", "Portfolio2026!")
        assert self.admin is not None
        self.token = auth.criar_sessao(self.admin["id"], self.admin["versao_senha"])
        self.state = patch("streamlit.session_state", {"auth_token": self.token})
        self.state.start()

    def tearDown(self) -> None:
        self.state.stop()
        banco_local.DB_PATH = self.antigo
        self.tmp.cleanup()

    def test_cadastro_senha_bloqueio_e_recuperacao(self) -> None:
        with self.assertRaises(ValueError):
            auth.cadastrar("João", "UmaSenhaNova2026!")
        auth.cadastrar("Teste123", "UmaSenhaNova2026!")
        self.assertIsNone(auth.autenticar("Teste123", "errada"))
        conta = auth.autenticar("Teste123", "UmaSenhaNova2026!")
        assert conta is not None
        token = auth.criar_sessao(conta["id"], conta["versao_senha"])
        auth.solicitar_recuperacao("Teste123")
        pedido = auth.recuperacoes_pendentes()[0][0]
        senha = auth.emitir_senha_temporaria(pedido, self.admin["id"])
        assert senha is not None
        self.assertIsNone(auth.validar_sessao(token))
        nova = auth.autenticar("Teste123", senha)
        assert nova is not None
        self.assertTrue(nova["trocar_senha"])
        with patch(
            "streamlit.session_state",
            {"auth_token": auth.criar_sessao(nova["id"], nova["versao_senha"])},
        ):
            self.assertTrue(auth.trocar_senha(nova["id"], senha, "SenhaFinal2026!"))
            with self.assertRaises(PermissionError):
                auth.recuperacoes_pendentes()
        self.assertIsNotNone(auth.autenticar("Teste123", "SenhaFinal2026!"))
        for _ in range(5):
            self.assertIsNone(auth.autenticar("Teste123", "errada"))
        self.assertIsNone(auth.autenticar("Teste123", "SenhaFinal2026!"))

    def test_sessao_expira_e_guia_persiste(self) -> None:
        auth.marcar_guia_visto(self.admin["id"], 1)
        sessao = auth.validar_sessao(self.token)
        assert sessao is not None
        self.assertEqual(sessao["versao_guia"], 1)
        with banco_local.conectar() as db:
            db.execute("UPDATE sessoes SET atividade = ?", (time.time() - 301,))
        self.assertIsNone(auth.validar_sessao(self.token))
        self.assertFalse(auth.tocar_sessao(self.token))

    def test_busca_planos_e_pontas(self) -> None:
        grade = real_data.buscar_grade_unificada(termo_busca="91000001 - CAMISETA ALGODÃO")
        self.assertEqual(len(grade), 8)
        sku = grade.SKU.iloc[0]
        self.assertEqual(len(real_data.buscar_grade_unificada(termo_busca=sku)), 1)
        concentrar = gerar_transferencia_concentracao([sku], 2, 1)
        self.assertGreater(concentrar[0]["Quantidade"], 0)
        pontas = calcular_concentracao_pontas(dados_demo.produtos().SKU.tolist())
        self.assertGreater(len(pontas), 0)
        perf = dados_demo.produtos().query("Secao == '08-PERFUMARIA'").SKU.tolist()
        distribuir = calcular_distribuicao_cadenciada(
            perf, [1, 2, 3, 4], 4, 10, 25, 2, "08-PERFUMARIA"
        )
        self.assertGreater(len(distribuir), 0)
        self.assertTrue(
            all(
                x["Filial_Origem_ID"] != x["Filial_Destino_ID"] and x["Quantidade"] > 0
                for x in distribuir
            )
        )

    def test_gravacao_duplicatas_saldo_exportacao(self) -> None:
        produtos = dados_demo.produtos()
        sku = produtos.SKU.iloc[-1]
        item = {
            "SKU": sku,
            "Filial_Origem_ID": 1,
            "Filial_Destino_ID": 4,
            "Quantidade": 2,
            "Motivo": "Manual",
        }
        self.assertEqual(real_data.gravar_novas_solicitacoes([item], "falso", produtos), (1, 0))
        self.assertEqual(real_data.gravar_novas_solicitacoes([item], "falso", produtos), (0, 1))
        with self.assertRaises(ValueError):
            real_data.gravar_novas_solicitacoes(
                [{**item, "Filial_Destino_ID": 3, "Quantidade": 10000}], "falso", produtos
            )
        hoje = real_data.carregar_solicitacoes_relatorio(date.today(), date.today())
        self.assertEqual(len(hoje), 1)
        self.assertIn("ADMINDEMO", hoje.iloc[0].Observacoes)
        vazio = real_data.carregar_solicitacoes_relatorio(
            date.today() - timedelta(days=400),
            date.today() - timedelta(days=390),
        )
        self.assertTrue(vazio.empty)
        _, _, _, filiais, kpis = real_data.carregar_dados_do_banco()
        hoje.loc[:, "Desc_prod"] = "=1+1"
        arquivo = real_data.gerar_relatorio_excel(hoje, kpis, filiais)
        with zipfile.ZipFile(arquivo) as z:
            self.assertEqual(
                len([x for x in z.namelist() if x.startswith("xl/worksheets/sheet")]),
                4,
            )
            self.assertFalse(
                any(b"<f>" in z.read(x) for x in z.namelist() if x.endswith(".xml"))
            )

    def test_interface_original_login_busca_registro(self) -> None:
        self.state.stop()
        import session_bridge
        from streamlit.testing.v1 import AppTest

        with (
            patch.object(session_bridge, "ensure_bridge"),
            patch.object(
                session_bridge,
                "acompanhar_navegador",
                return_value=SimpleNamespace(cookie_ready=True, expired=False),
            ),
        ):
            at = AppTest.from_file("app.py", default_timeout=25).run()
            at.text_input[0].set_value("ADMINDEMO")
            at.text_input[1].set_value("Portfolio2026!")
            next(b for b in at.button if b.label == "Acessar painel").click().run()
            self.assertFalse(at.exception)
            next(b for b in at.button if b.key == "guia_fechar").click().run()
            at.text_input(key="busca_catalogo").set_value("91000007").run()
            next(b for b in at.button if b.label == "Pesquisar").click().run()
            next(b for b in at.button if b.label == "Selecionar todos").click().run()
            self.assertFalse(at.exception)
            next(b for b in at.button if b.label == "Solicitar diretamente").click().run()
            self.assertFalse(at.exception)
            self.assertGreater(at.session_state["confirmacao_solicitacao"]["registradas"], 0)
            self.assertTrue(any("sucesso" in x.value for x in at.success))

            at = AppTest.from_file("app.py", default_timeout=25).run()
            at.text_input[0].set_value("ADMINDEMO")
            at.text_input[1].set_value("Portfolio2026!")
            next(b for b in at.button if b.label == "Acessar painel").click().run()
            at.text_input(key="busca_catalogo").set_value("91000008").run()
            next(b for b in at.button if b.label == "Pesquisar").click().run()
            next(b for b in at.button if b.label == "Selecionar todos").click().run()
            next(b for b in at.button if b.label == "Revisar transferências").click().run()
            next(b for b in at.button if b.label == "Revisar transferências").click()
            next(b for b in at.button if b.label == "Registrar solicitações").click().run()
            self.assertFalse(at.exception)
            self.assertFalse(at.error, [x.value for x in at.error])
            with banco_local.conectar() as db:
                self.assertGreater(
                    db.execute("SELECT COUNT(*) FROM solicitacoes WHERE Prod_pai = '91000008'").fetchone()[0],
                    0,
                )


if __name__ == "__main__":
    unittest.main()
