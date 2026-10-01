"""Chaves de configuração que completam o que os arquivos não registram: `registro` por estrutura e
referência de frequências lida de uma tabela JSON."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _comum import DIMERO, ORCA_DIMERO, cli, dados_do_html, tem_ase


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def gerar(self, cfg):
        (self.dir / "painel.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        r = cli("gerar", self.dir / "painel.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return dados_do_html(self.dir / "painel.html")


@unittest.skipUnless(tem_ase(), "precisa do ASE para ler .xyz")
class TestRegistro(_Base):
    def setUp(self):
        super().setUp()
        for n in ("a", "b"):
            shutil.copy(DIMERO / "calc" / "geometrias" / "benzeno.xyz", self.dir / f"{n}.xyz")
        (self.dir / "a.json").write_text(json.dumps({"convergiu": True, "passos": 7, "tempo_s": 12.5}), encoding="utf-8")
        (self.dir / "b.json").write_text("{ isto não é json", encoding="utf-8")

    def test_registro_completa_convergencia_passos_e_tempo(self):
        D = self.gerar({"estruturas": [{"id": "e_{stem}", "arquivo": "*.xyz", "registro": "{stem}.json"}]})
        est = {e["id"]: e for e in D["est"]}
        self.assertIs(est["e_a"]["conv"], True)
        self.assertEqual(est["e_a"]["passos"], 7)
        self.assertEqual(est["e_a"]["t"], 12.5)

    def test_registro_ilegivel_vira_aviso(self):
        D = self.gerar({"estruturas": [{"id": "e_{stem}", "arquivo": "*.xyz", "registro": "{stem}.json"}]})
        est = {e["id"]: e for e in D["est"]}
        self.assertIsNone(est["e_b"]["conv"])                 # nada inventado
        self.assertTrue(any("e_b" in a and "registro" in a for a in D["avisos"]), D["avisos"])


class TestReferenciaFreqJson(_Base):
    def test_tabela_json_com_pareamento_proprio(self):
        tabela = {"validacao": {"tabela": [
            {"especie": "a1g", "descricao": "respiração", "exp_cm1": 993, "calc_cm1": 1000.0},
            {"especie": "e2g", "descricao": "anel", "exp_cm1": 608, "calc_cm1": 600.0},
            {"especie": "x", "descricao": "sem valor", "exp_cm1": None}]}}
        (self.dir / "ref.json").write_text(json.dumps(tabela), encoding="utf-8")
        D = self.gerar({"frequencias": {"sistemas": [{
            "id": "bz", "arquivo": str(ORCA_DIMERO / "benzeno" / "benzeno.out"),
            "referencia": {"json": "ref.json", "caminho": "validacao.tabela", "campo_rotulo": "{especie} · {descricao}",
                           "campo_valor": "exp_cm1", "campo_calc": "calc_cm1", "fonte": "teste"}}]}})
        v = D["freq"]["sistemas"][0]["valid"]
        self.assertEqual([x["rotulo"] for x in v["linhas"]], ["a1g · respiração", "e2g · anel"])
        self.assertEqual([x["calc"] for x in v["linhas"]], [1000.0, 600.0])
        self.assertAlmostEqual(v["mae"], 7.5)
        self.assertEqual(v["fonte"], "teste")

    def test_referencia_json_ausente_nao_quebra(self):
        D = self.gerar({"frequencias": {"sistemas": [{
            "id": "bz", "arquivo": str(ORCA_DIMERO / "benzeno" / "benzeno.out"), "referencia": {"json": "nao_existe.json"}}]}})
        self.assertIsNone(D["freq"]["sistemas"][0]["valid"])
        self.assertTrue(any("referência" in a for a in D["avisos"]), D["avisos"])


class TestExpressaoInvalida(_Base):
    def test_expressao_invalida_vira_aviso(self):
        D = self.gerar({"estruturas": [{"id": "bz", "arquivo": str(ORCA_DIMERO / "benzeno" / "benzeno.out")}],
                        "energia": {"termos": {"E": "bz"}, "parcelas": [{"nome": "ruim", "expr": "E +* 2"},
                                                                        {"nome": "zero", "expr": "E/(E-E)"}]}})
        self.assertGreaterEqual(sum("inválida" in a for a in D["avisos"]), 2, D["avisos"])


if __name__ == "__main__":
    unittest.main()
