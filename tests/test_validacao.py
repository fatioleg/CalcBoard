"""Forças por átomo, validação método × referência, energia relativa entre métodos, regra de decisão e ressalvas.

Cada leitor/seção tem controle positivo (o caso que deve funcionar) e negativo (o caso que deve ser recusado ou avisado)."""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from _comum import AMOSTRAS, DIMERO, ORCA_DIMERO, SKILL, L, tem_ase
from painel_lib import analise as A
from painel_lib.montar import Montador
from painel_lib.textos import TXT, Msg, traduzir

HA_BOHR = L.HA_BOHR_EVA
SP = ORCA_DIMERO / "sp_na_geometria_uma"


def montar(cfg, lang="pt", base=DIMERO):
    return Montador(dict(cfg, _dir=str(base), lang=lang)).montar()


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.addCleanup(self._t.cleanup)


# ----------------------------------------------------------------------------------------------------------
# leitores: forças e tensão
# ----------------------------------------------------------------------------------------------------------
class TestLeitoresForcas(_Tmp):
    def test_orca_bloco_cartesian_gradient_vira_forca(self):
        R = L.ler(SP / "sp_benzeno.out")
        F = R["quadros"][-1]["F"]
        self.assertEqual(F.shape, (12, 3))
        t = (SP / "sp_benzeno.out").read_text(errors="replace")
        bloco = t[t.index("CARTESIAN GRADIENT"):]
        g = np.array([[float(x) for x in m.groups()] for m in re.finditer(r"^\s*\d+\s+[A-Z][a-z]?\s*:\s+(\S+)\s+(\S+)\s+(\S+)\s*$", bloco, re.M)][:12])
        np.testing.assert_allclose(F, -g * HA_BOHR, atol=1e-9)
        self.assertLess(np.abs(F.sum(0)).max(), 1e-3)             # invariância translacional: soma das forças ~ 0

    def test_orca_sem_bloco_e_sem_engrad_nao_inventa_forca(self):
        t = (SP / "sp_benzeno.out").read_text(errors="replace")
        t = re.sub(r"CARTESIAN GRADIENT\n-+\n\s*\n.*?\n\s*\n", "", t, flags=re.S)
        (self.tmp / "x.out").write_text(t)
        self.assertIsNone(L.ler(self.tmp / "x.out")["quadros"][-1]["F"])

    def test_orca_engrad_ao_lado_substitui_o_bloco(self):
        t = (SP / "sp_benzeno.out").read_text(errors="replace")
        t = re.sub(r"CARTESIAN GRADIENT\n-+\n\s*\n.*?\n\s*\n", "", t, flags=re.S)
        (self.tmp / "y.out").write_text(t)
        g = np.linspace(-0.01, 0.02, 36)
        (self.tmp / "y.engrad").write_text("#\n# Number of atoms\n#\n 12\n#\n# The current total energy in Eh\n#\n  -231.0\n#\n"
                                           "# The current gradient in Eh/bohr\n#\n" + "\n".join(f"{x:.12f}" for x in g)
                                           + "\n#\n# The atomic numbers and current coordinates in Bohr\n#\n")
        F = L.ler(self.tmp / "y.out")["quadros"][-1]["F"]
        np.testing.assert_allclose(F, -g.reshape(12, 3) * HA_BOHR, atol=1e-12)
        # engrad com o número errado de átomos: recusado (F continua None)
        (self.tmp / "y.engrad").write_text("# The current gradient in Eh/bohr\n#\n0.1\n0.2\n0.3\n#\n")
        self.assertIsNone(L.ler(self.tmp / "y.out")["quadros"][-1]["F"])

    def test_cp2k_atomic_forces_em_unidades_atomicas(self):
        out = AMOSTRAS / "cp2k" / "agua_geo" / "SINTETICO_agua.out"
        f = np.array([[0, 0, -0.010], [0, 0.005, 0.005], [0, -0.005, 0.005]])
        bloco = ("\n ATOMIC FORCES in [a.u.]\n\n # Atom   Kind   Element          X              Y              Z\n"
                 + "".join(f"      {i + 1}      {1 if i == 0 else 2}      {'O' if i == 0 else 'H'}   {r[0]:14.8f} {r[1]:14.8f} {r[2]:14.8f}\n" for i, r in enumerate(f))
                 + " SUM OF ATOMIC FORCES   0.0 0.0 0.0\n")
        (self.tmp / "a.out").write_text(out.read_text(errors="replace") + bloco)
        R = L.ler(self.tmp / "a.out")
        np.testing.assert_allclose(R["quadros"][-1]["F"], f * HA_BOHR, atol=1e-9)
        # bloco com o número errado de átomos: não é atribuído a nenhum quadro
        (self.tmp / "b.out").write_text(out.read_text(errors="replace") + bloco.replace("      3      2      H", "#"))
        shutil.copy(AMOSTRAS / "cp2k" / "agua_geo" / "SINTETICO_agua-pos-1.xyz", self.tmp / "SINTETICO_agua-pos-1.xyz")
        self.assertTrue(all(q["F"] is None for q in L.ler(self.tmp / "b.out")["quadros"]))

    def test_vasp_forcas_e_tensao_no_sinal_do_ase(self):
        R = L.ler(AMOSTRAS / "vasp" / "si_relax" / "OUTCAR")
        q = R["quadros"][-1]
        self.assertEqual(q["F"].shape, (len(q["simbolos"]), 3))
        # "in kB" -0.3 (tensão de compressão no sinal do VASP) -> +0,03 GPa na convenção do ASE (tração positiva); Voigt xx yy zz yz zx xy
        np.testing.assert_allclose(q["S"], [0.03, 0.03, 0.03, 0, 0, 0], atol=1e-9)
        self.assertAlmostEqual(q["sigma_GPa"], 0.03)

    @unittest.skipUnless(tem_ase(), "precisa do ASE")
    def test_ase_extxyz_forcas_e_tensao_voigt(self):
        from ase.build import bulk
        from ase.calculators.singlepoint import SinglePointCalculator
        from ase.io import write
        a = bulk("Si", cubic=True)
        F = np.arange(24, dtype=float).reshape(8, 3) / 100
        s = np.array([0.001, 0.002, 0.003, 0.004, 0.005, 0.006])         # eV/Å³, Voigt do ASE
        a.calc = SinglePointCalculator(a, energy=-1.0, forces=F, stress=s)
        write(self.tmp / "si.extxyz", a)
        q = L.ler(self.tmp / "si.extxyz")["quadros"][-1]
        np.testing.assert_allclose(q["F"], F, atol=1e-8)
        np.testing.assert_allclose(q["S"], s * 160.21766208, rtol=1e-6)
        # molécula sem tensão: S ausente, não zero
        from ase.build import molecule
        m = molecule("H2O")
        m.calc = SinglePointCalculator(m, energy=-1.0, forces=np.zeros((3, 3)))
        write(self.tmp / "h2o.extxyz", m)
        q = L.ler(self.tmp / "h2o.extxyz")["quadros"][-1]
        self.assertIsNone(q["S"])
        self.assertIsNotNone(q["F"])

    def test_gaussian_forcas_so_com_nosymm(self):
        log = (AMOSTRAS / "gaussian" / "SINTETICO_agua.log").read_text(errors="replace")
        bloco = (" -------------------------------------------------------------------\n Center     Atomic                   Forces (Hartrees/Bohr)\n"
                 " Number     Number              X              Y              Z\n -------------------------------------------------------------------\n"
                 "      1        8           0.000000000    0.000000000    0.010000000\n      2        1           0.000000000    0.004000000   -0.005000000\n"
                 "      3        1           0.000000000   -0.004000000   -0.005000000\n -------------------------------------------------------------------\n")
        com = log.replace(" Requested convergence", bloco + " Requested convergence", 1)
        (self.tmp / "sem.log").write_text(com)
        self.assertIsNone(L.ler(self.tmp / "sem.log")["quadros"][0]["F"])     # sem nosymm a orientação do bloco é incerta: recusado
        (self.tmp / "com.log").write_text(com.replace("opt freq", "opt freq nosymm", 1))
        q = L.ler(self.tmp / "com.log")["quadros"][0]
        np.testing.assert_allclose(q["F"][0], [0, 0, 0.01 * HA_BOHR], atol=1e-9)


# ----------------------------------------------------------------------------------------------------------
# análises numéricas
# ----------------------------------------------------------------------------------------------------------
class TestAnalise(unittest.TestCase):
    def test_erro_de_forca(self):
        Fa = np.array([[0.1, 0, 0], [0, 0.2, 0]])
        Fb = np.array([[0.0, 0, 0], [0, 0.0, 0.1]])
        E = A.erro_forcas(Fa, Fb)
        np.testing.assert_allclose(E["eps"], [0.1, np.hypot(0.2, 0.1)])
        self.assertAlmostEqual(E["mae"], (0.1 + 0.2 + 0.1) / 6)          # média sobre as 3N componentes
        self.assertAlmostEqual(E["max_comp"], 0.2)
        with self.assertRaises(ValueError):
            A.erro_forcas(Fa, Fb[:1])                                    # número de átomos diferente

    def test_agregacao_e_concentracao(self):
        dF = np.array([[0.3, 0, 0], [0.1, 0, 0], [0.1, 0, 0], [0.0, 0.1, 0]])
        g = A.agregar_grupos(dF, ["F", "C", "C", "H"])
        self.assertAlmostEqual(sum(v["parcela"] for v in g.values()), 1.0)
        self.assertAlmostEqual(g["F"]["parcela"], 0.3 / 0.6)
        self.assertAlmostEqual(g["C"]["mae"], (0.1 + 0.1) / 6)
        c = A.concentracao(np.linalg.norm(dF, axis=1), (25, 50))
        self.assertEqual(c["25"]["n"], 1)
        self.assertAlmostEqual(c["25"]["fracao"], 0.5)
        self.assertAlmostEqual(c["50"]["fracao"], 0.4 / 0.6)
        # erro só por átomo (sem componentes): MAE por componente indisponível, parcela mantida
        g1 = A.agregar_grupos(np.array([0.3, 0.1, 0.1, 0.1]), ["F", "C", "C", "H"])
        self.assertIsNone(g1["F"]["mae"])
        self.assertAlmostEqual(g1["F"]["parcela"], 0.5)

    def test_correlacoes_de_posto_contra_scipy(self):
        try:
            from scipy import stats
        except ImportError:
            self.skipTest("sem scipy")
        rng = np.random.default_rng(3)
        for _ in range(5):
            x = np.round(rng.normal(size=9), 1)
            y = np.round(x + rng.normal(scale=0.7, size=9), 1)           # com empates
            self.assertAlmostEqual(A.spearman(x, y), stats.spearmanr(x, y).statistic, places=9)
            self.assertAlmostEqual(A.kendall(x, y), stats.kendalltau(x, y).statistic, places=9)
        self.assertIsNone(A.spearman([1, 2], [1, 2]))                     # menos de 3 pontos: não calcula
        self.assertIsNone(A.spearman([1, 1, 1], [1, 2, 3]))               # sem variância

    def test_energia_relativa_e_menor_energia(self):
        M = A.energia_relativa(["X", "Y", "Z"], [0.0, 1.0, 2.0], [1.0, 0.0, 2.0], 0)
        self.assertEqual((M["menor_a"], M["menor_b"], M["menor_difere"]), (0, 1, True))        # controle positivo: discordam
        np.testing.assert_allclose(M["da"], [0, 1, 2])
        np.testing.assert_allclose(M["db"], [0, -1, 1])
        self.assertAlmostEqual(M["spearman"], 0.5)
        self.assertAlmostEqual(M["kendall"], 1 / 3)
        self.assertAlmostEqual(M["mae"], (2 + 1) / 2)                      # erros 2 e 1 (sem a referência)
        self.assertAlmostEqual(M["max_abs"], 2.0)
        self.assertAlmostEqual(M["mae_centrado"], 0.5)                     # erros 2, 1: média 1,5
        M2 = A.energia_relativa(["X", "Y", "Z"], [0.0, 1.0, 2.0], [5.0, 5.5, 8.0], 0)
        self.assertFalse(M2["menor_difere"])                               # controle negativo: concordam (offset constante não importa)
        self.assertAlmostEqual(M2["spearman"], 1.0)

    def test_faixa_de_qualidade(self):
        lim = [30, 50, 100]
        self.assertEqual([A.faixa(x, lim) for x in (10, 30, 30.1, 50, 99, 100, 101)], [0, 0, 1, 1, 2, 2, 3])
        self.assertIsNone(A.faixa(None, lim))

    def test_avaliador_seguro(self):
        self.assertEqual(A.avaliar("max(a, 2) - min(a, 1)", {"a": 3}), 2.0)
        self.assertTrue(A.avaliar("T >= 2 and T < 5", {"T": 3}))
        self.assertEqual(A.nomes_expr("max(a, b) + c"), ["a", "b", "c"])           # função não é variável
        for ruim in ("__import__('os')", "a.b", "(lambda: 1)()", "a ** 2", "open('x')", "[1, 2]"):
            with self.assertRaises(Exception, msg=ruim):
                A.avaliar(ruim, {"a": 1})
        with self.assertRaises(ValueError):
            A.calc_expr("a > 1", {"a": 2})                                   # comparação não é aritmética
        self.assertEqual(sorted(A.limiares_condicao("T >= 2 and 0.5 < T", "T", {})), [(">", 0.5), (">=", 2.0)])


# ----------------------------------------------------------------------------------------------------------
# montagem: erro de força, validação, energia relativa
# ----------------------------------------------------------------------------------------------------------
ESTR = [
    {"id": "uma_bz", "arquivo": "calc/uma/estruturas/benzeno.extxyz", "grupo": "uma"},
    {"id": "sp_bz", "arquivo": "calc/orca/sp_na_geometria_uma/sp_benzeno.out", "grupo": "sp"},
    {"id": "uma_pd", "arquivo": "calc/uma/estruturas/dimero_PD__p0.extxyz", "grupo": "uma"},
    {"id": "sp_pd", "arquivo": "calc/orca/sp_na_geometria_uma/sp_dimero_PD__p0.out", "grupo": "sp"},
    {"id": "dft_bz", "arquivo": "calc/orca/benzeno/benzeno.out", "grupo": "dft"},
    {"id": "xyz_bz", "arquivo": "calc/geometrias/benzeno.xyz", "grupo": "xyz"},
]


@unittest.skipUnless(tem_ase(), "precisa do ASE")
class TestForcasMontagem(_Tmp):
    def test_par_de_forcas_estatisticas_e_coloracao(self):
        D = montar({"estruturas": ESTR, "forcas": {"pares": [{"id": "p", "a": "uma_bz", "b": "sp_bz", "rotulo_a": "UMA", "rotulo_b": "B97-3c"}]}})
        self.assertEqual(D["avisos"], [])
        s = D["valid"]["sistemas"][0]
        est = {e["id"]: e for e in D["est"]}
        qa = L.ler(DIMERO / "calc/uma/estruturas/benzeno.extxyz")["quadros"][-1]["F"]
        qb = L.ler(SP / "sp_benzeno.out")["quadros"][-1]["F"]
        ref = np.abs(qa - qb)
        self.assertAlmostEqual(s["mae"], ref.mean() * 1000, places=6)
        self.assertAlmostEqual(s["max_comp"], ref.max() * 1000, places=6)
        self.assertEqual(s["n"], 12)
        self.assertEqual(set(s["elementos"]), {"C", "H"})
        self.assertAlmostEqual(sum(v["parcela"] for v in s["elementos"].values()), 1.0)
        self.assertEqual(s["faixa_mae"], 0)                              # faixa padrão: ≤ 30 meV/Å
        self.assertTrue(D["valid"]["bandas"]["forca_mae"]["padrao"])
        # as duas estruturas ganham o |ΔF| por átomo (meV/Å) e o rótulo do par
        for k in ("uma_bz", "sp_bz"):
            self.assertEqual(len(est[k]["dF"]), 12)
            self.assertEqual(est[k]["dF_rot"], "UMA × B97-3c")
        np.testing.assert_allclose(est["uma_bz"]["dF"], np.rint(np.linalg.norm(qa - qb, axis=1) * 1000), atol=1)
        self.assertNotIn("dF", est["xyz_bz"])

    def test_faixas_vem_da_configuracao_e_nada_e_fixo(self):
        base = {"estruturas": ESTR, "forcas": {"pares": [{"a": "uma_pd", "b": "sp_pd"}]}}
        D = montar(dict(base, validacao={"bandas": {"forca_mae": {"limites": [1, 2, 3], "rotulos": ["a", "b", "c", "d"]}}}))
        b = D["valid"]["bandas"]["forca_mae"]
        self.assertEqual((b["limites"], b["rotulos"], b["padrao"]), ([1.0, 2.0, 3.0], ["a", "b", "c", "d"], False))
        s = D["valid"]["sistemas"][0]
        self.assertEqual(s["faixa_mae"], 3)                              # MAE ~8 meV/Å > 3: a última faixa
        # limites fora de ordem: recusados, com aviso
        D = montar(dict(base, validacao={"bandas": {"forca_mae": {"limites": [3, 1]}}}))
        self.assertNotIn("forca_mae", D["valid"]["bandas"])
        self.assertTrue(D["avisos"])

    def test_componentes_e_moleculas_por_conectividade(self):
        D = montar({"estruturas": ESTR, "forcas": [{"a": "uma_pd", "b": "sp_pd"}]})
        s = D["valid"]["sistemas"][0]
        self.assertIsNone(s["componentes"])
        self.assertEqual(sorted(s["moleculas"]), ["1 · C6H6", "2 · C6H6"])                   # duas moléculas achadas pela conectividade
        self.assertAlmostEqual(sum(v["parcela"] for v in s["moleculas"].values()), 1.0)
        D = montar({"estruturas": [dict(e, componentes=[{"nome": "anel", "formula": "C6H6", "cor": "#ff0000"}]) for e in ESTR],
                    "forcas": [{"a": "uma_pd", "b": "sp_pd"}]})
        s = D["valid"]["sistemas"][0]
        self.assertIsNone(s["componentes"])                                # uma só classe: não há divisão por componente
        D = montar({"estruturas": [dict(e, componentes=[{"nome": "monomero1", "indices": "0-11"}, {"nome": "monomero2", "indices": "12-23"}]) for e in ESTR],
                    "forcas": [{"a": "uma_pd", "b": "sp_pd"}]})
        self.assertEqual(sorted(D["valid"]["sistemas"][0]["componentes"]), ["monomero1", "monomero2"])

    def test_recusas_com_aviso(self):
        casos = {
            "geometrias diferentes": {"a": "uma_bz", "b": "dft_bz"},
            "numero de atomos diferente": {"a": "uma_bz", "b": "sp_pd"},
            "sem forcas no arquivo": {"a": "xyz_bz", "b": "sp_bz"},
            "estrutura ausente": {"a": "uma_bz", "b": "nao_existe"},
            "falta b": {"a": "uma_bz"},
        }
        for nome, par in casos.items():
            with self.subTest(nome):
                D = montar({"estruturas": ESTR, "forcas": [par]})
                self.assertIsNone(D["valid"], nome)
                self.assertEqual(len(D["avisos"]), 1, D["avisos"])
                self.assertTrue(all("dF" not in e for e in D["est"]))

    def test_forcas_precalculadas_por_atomo(self):
        (self.tmp / "dF.json").write_text(json.dumps({"sis": {"arrays": {"dF_eV_A": [0.01 * k for k in range(12)]}}}))
        cfg = {"estruturas": ESTR, "forcas": {"precalculado": [{"id": "pre", "estrutura": "uma_bz", "json": str(self.tmp / "dF.json"),
                                                               "caminho": "sis.arrays.dF_eV_A", "rotulo_a": "A", "rotulo_b": "B"}]}}
        D = montar(cfg)
        s = D["valid"]["sistemas"][0]
        self.assertEqual(s["mae_tipo"], "atomo")
        self.assertAlmostEqual(s["media_atomo"], 55.0)                      # média de 0..0,11 eV/Å = 55 meV/Å
        self.assertIsNone(s["max_comp"])
        est = {e["id"]: e for e in D["est"]}
        self.assertEqual(est["uma_bz"]["dF"], [10 * k for k in range(12)])
        # unidade meV/Å
        (self.tmp / "m.json").write_text(json.dumps([10 * k for k in range(12)]))
        D = montar(dict(cfg, forcas={"precalculado": [{"estrutura": "uma_bz", "json": str(self.tmp / "m.json"), "unidade": "meV/Å"}]}))
        self.assertAlmostEqual(D["valid"]["sistemas"][0]["media_atomo"], 55.0)
        # número de valores diferente do de átomos: recusado
        (self.tmp / "n.json").write_text(json.dumps([0.1, 0.2]))
        D = montar(dict(cfg, forcas={"precalculado": [{"estrutura": "uma_bz", "json": str(self.tmp / "n.json")}]}))
        self.assertIsNone(D["valid"])
        self.assertTrue(D["avisos"])

    def test_tensao_entre_dois_periodicos(self):
        from ase.build import bulk
        from ase.calculators.singlepoint import SinglePointCalculator
        from ase.io import write
        a = bulk("Si", cubic=True)
        F = np.zeros((8, 3))
        F[0] = [0.1, 0, 0]
        for nome, s in (("a", [0.001, 0.002, 0.003, 0, 0, 0]), ("b", [0.001, 0.001, 0.001, 0, 0, 0])):
            c = a.copy()
            c.calc = SinglePointCalculator(c, energy=-1.0, forces=F if nome == "a" else F * 0.5, stress=np.array(s))
            write(self.tmp / f"{nome}.extxyz", c)
        D = montar({"estruturas": [{"id": "a", "arquivo": "a.extxyz"}, {"id": "b", "arquivo": "b.extxyz"}], "forcas": [{"a": "a", "b": "b"}]}, base=self.tmp)
        s = D["valid"]["sistemas"][0]
        self.assertAlmostEqual(s["tensao"]["mae"], np.mean([0, 0.001, 0.002, 0, 0, 0]) * 160.21766208, places=6)
        self.assertAlmostEqual(s["tensao"]["max"], 0.002 * 160.21766208, places=6)
        self.assertAlmostEqual(s["max_comp"], 50.0, places=6)
        # molécula (sem tensão): sem bloco de tensão, sem zero inventado
        D = montar({"estruturas": ESTR, "forcas": [{"a": "uma_bz", "b": "sp_bz"}]})
        self.assertIsNone(D["valid"]["sistemas"][0]["tensao"])

    def test_pares_por_grupo(self):
        est = [{"id": "u_{item}", "arquivo": "calc/uma/estruturas/dimero_*__p0.extxyz", "padrao": "dimero_(?P<item>[A-Z]+)__p0", "grupo": "uma"},
               {"id": "s_{item}", "arquivo": "calc/orca/sp_na_geometria_uma/sp_dimero_*__p0.out", "padrao": "sp_dimero_(?P<item>[A-Z]+)__p0", "grupo": "sp"}]
        D = montar({"estruturas": est, "forcas": {"pares": [{"id": "f_{item}", "a_grupo": "uma", "b": "s_{item}", "sistema": "dímero {item}"}]}})
        self.assertEqual(D["avisos"], [])
        self.assertEqual(sorted(s["id"] for s in D["valid"]["sistemas"]), ["f_PD", "f_S", "f_T"])
        self.assertEqual(sorted(s["sistema"] for s in D["valid"]["sistemas"]), ["dímero PD", "dímero S", "dímero T"])


@unittest.skipUnless(tem_ase(), "precisa do ASE")
class TestEnergiaRelativa(unittest.TestCase):
    def item(self, rot, a, b):
        return {"rotulo": rot, "a": {"valor": a, "unidade": "kJ/mol"}, "b": {"valor": b, "unidade": "kJ/mol"}}

    def test_metricas_e_unidades(self):
        D = montar({"comparacao_energia": [{"id": "c", "titulo": "t", "referencia": "X", "rotulo_a": "A", "rotulo_b": "B",
                                            "itens": [self.item("X", -1000.0, -2000.0), self.item("Y", -999.0, -2001.0), self.item("Z", -998.0, -1999.0)]}]})
        c = D["relativa"][0]
        m = c["metricas"]
        ev = 1 / 96.48533212
        self.assertEqual((m["menor_a"], m["menor_b"], m["menor_difere"]), ("X", "Y", True))
        self.assertAlmostEqual(m["mae"], 1.5 * ev, places=9)                          # valores em eV internamente
        self.assertAlmostEqual(m["max_abs"], 2.0 * ev, places=9)
        self.assertAlmostEqual(c["itens"][1]["da"], 1.0 * ev, places=9)
        self.assertAlmostEqual(c["itens"][1]["db"], -1.0 * ev, places=9)
        self.assertEqual(c["ref"], "X")
        self.assertEqual(D["avisos"], [])                                          # números digitados não geram aviso de mistura

    def test_referencia_inexistente_e_poucos_itens(self):
        D = montar({"comparacao_energia": [{"id": "c", "referencia": "Q", "itens": [self.item("X", 0, 0), self.item("Y", 1, 1)]}]})
        self.assertEqual(D["relativa"][0]["ref"], "X")
        self.assertTrue(any("'Q'" in a for a in D["avisos"]), D["avisos"])
        D = montar({"comparacao_energia": [{"id": "c", "itens": [self.item("X", 0, 0)]}]})
        self.assertEqual(D["relativa"], [])
        self.assertTrue(D["avisos"])
        D = montar({"comparacao_energia": [{"id": "c"}]})
        self.assertEqual(D["relativa"], [])

    def test_estruturas_reais_e_mistura_de_niveis(self):
        est = [{"id": "uma_pd", "arquivo": "calc/uma/estruturas/dimero_PD__p0.extxyz"}, {"id": "uma_t", "arquivo": "calc/uma/estruturas/dimero_T__p0.extxyz"},
               {"id": "sp_pd", "arquivo": "calc/orca/sp_na_geometria_uma/sp_dimero_PD__p0.out"}, {"id": "sp_t", "arquivo": "calc/orca/sp_na_geometria_uma/sp_dimero_T__p0.out"}]
        ok = {"id": "c", "referencia": "PD", "itens": [{"rotulo": "PD", "a": "uma_pd", "b": "sp_pd"}, {"rotulo": "T", "a": "uma_t", "b": "sp_t"}]}
        D = montar({"estruturas": est, "comparacao_energia": [ok]})
        self.assertEqual(D["avisos"], [])
        self.assertEqual(len(D["relativa"][0]["selos_a"]), 1)
        # controle negativo: um item do lado B vem de outro nível (UMA no lugar do ORCA): aviso de mistura
        ruim = {"id": "c", "referencia": "PD", "itens": [{"rotulo": "PD", "a": "uma_pd", "b": "sp_pd"}, {"rotulo": "T", "a": "uma_t", "b": "uma_t"}]}
        D = montar({"estruturas": est, "comparacao_energia": [ruim]})
        self.assertTrue(any("mistura" in a for a in D["avisos"]), D["avisos"])


# ----------------------------------------------------------------------------------------------------------
# regra de decisão
# ----------------------------------------------------------------------------------------------------------
def regra(R=5.0, U=1.0, **extra):
    r = {"id": "r", "titulo": "regra", "grandezas": {"R": {"valor": R, "unidade": "kJ/mol"}, "U": {"valor": U, "unidade": "kJ/mol"}},
         "estatistica": {"nome": "T", "expr": "R / U", "casas": 2},
         "resultados": [{"id": "est", "rotulo": "estabelecido", "quando": "T >= 2", "severidade": "ok"},
                        {"id": "ref", "rotulo": "refutado", "quando": "T <= -2", "severidade": "bad"},
                        {"id": "inc", "rotulo": "inconclusivo", "severidade": "warn"}]}
    r.update(extra)
    return r


class TestRegraDeDecisao(unittest.TestCase):
    def go(self, **kw):
        return montar({"regras": [regra(**kw)]})

    def test_tres_veredictos_e_margem(self):
        for R, esperado, marg, op in ((5.0, "est", 3.0, ">="), (-5.0, "ref", 3.0, "<="), (1.0, "inc", 1.0, ">=")):
            with self.subTest(R=R):
                r = self.go(R=R)["regras"][0]
                self.assertEqual(r["resultado"]["id"], esperado)
                self.assertAlmostEqual(r["estatistica"]["valor"], R)
                self.assertAlmostEqual(r["margem"]["valor"], marg)
                self.assertEqual(r["margem"]["op"], op)
                self.assertEqual(r["margem"]["satisfeito"], esperado != "inc")
        r = self.go(R=2.0)["regras"][0]                                    # exatamente no limiar: ">=" vale
        self.assertEqual(r["resultado"]["id"], "est")
        self.assertAlmostEqual(r["margem"]["valor"], 0.0)

    def test_grandeza_de_energia_segue_a_unidade_declarada(self):
        r = self.go()["regras"][0]
        g = {x["id"]: x for x in r["grandezas"]}
        self.assertEqual(g["R"]["valor"], 5.0)
        self.assertAlmostEqual(g["R"]["fator_ev"], 1 / 96.48533212)         # o painel converte para a unidade escolhida no topo
        self.assertTrue(g["R"]["digitado"])

    def test_sem_grandeza_nao_ha_veredito_e_o_painel_nao_presume(self):
        r = montar({"regras": [regra(grandezas={"R": {"estrutura": "nao_existe", "unidade": "kJ/mol"}, "U": {"valor": 1.0}})]})
        reg = r["regras"][0]
        self.assertIsNone(reg["resultado"])
        self.assertIsNone(reg["estatistica"]["valor"])
        self.assertIn("R", reg["faltam"])
        self.assertTrue(any("sem veredito" in a for a in r["avisos"]), r["avisos"])

    def test_expressoes_encadeadas_funcoes_e_dependencias(self):
        r = self.go(grandezas={"R": {"valor": 6.0}, "a": {"valor": 1.0}, "b": {"valor": 3.0}, "U": {"expr": "max(a, b, piso)"}, "piso": {"valor": 0.1}})["regras"][0]
        self.assertAlmostEqual(r["estatistica"]["valor"], 2.0)             # U = máx(1; 3; 0,1) = 3 (dependência declarada depois do uso)
        self.assertEqual(r["resultado"]["id"], "est")
        # dependência circular ou nome desconhecido: aviso e sem veredito, nunca exceção
        d = self.go(grandezas={"R": {"valor": 6.0}, "U": {"expr": "U + x"}})
        self.assertIsNone(d["regras"][0]["resultado"])
        self.assertTrue(d["avisos"])
        d = self.go(grandezas={"R": {"valor": 6.0}, "U": {"expr": "__import__('os').getcwd()"}})
        self.assertIsNone(d["regras"][0]["resultado"])

    def test_sensibilidade_muda_o_veredito(self):
        r = self.go(R=3.0, sensibilidade=[{"rotulo": "U menor", "grandezas": {"U": {"valor": 0.5}}},
                                          {"rotulo": "U maior", "grandezas": {"U": {"valor": 10.0}}}])["regras"][0]
        self.assertEqual(r["resultado"]["id"], "est")
        self.assertEqual([s["resultado"]["id"] for s in r["sensibilidade"]], ["est", "inc"])
        self.assertTrue(r["veredito_muda"])
        r = self.go(R=30.0, sensibilidade=[{"rotulo": "U maior", "grandezas": {"U": {"valor": 2.0}}}])["regras"][0]
        self.assertFalse(r["veredito_muda"])                               # controle negativo: estável
        self.assertAlmostEqual(r["sensibilidade"][0]["T"], 15.0)

    def test_estatistica_fixada_depois_sem_sensibilidade_avisa(self):
        d = self.go(pre_registrada=False)
        self.assertTrue(any("depois de ver os dados" in a for a in d["avisos"]), d["avisos"])
        self.assertIs(d["regras"][0]["pre_registrada"], False)
        d = self.go(pre_registrada=False, sensibilidade=[{"rotulo": "x", "grandezas": {"U": {"valor": 2.0}}}])
        self.assertEqual(d["avisos"], [])                                  # com a tabela de sensibilidade, nada a avisar
        self.assertEqual(self.go(pre_registrada=True)["avisos"], [])
        self.assertIsNone(self.go()["regras"][0]["pre_registrada"])        # não declarado continua não declarado

    def test_grandezas_vindas_de_comparacao_e_de_forcas(self):
        est = [{"id": "uma_pd", "arquivo": "calc/uma/estruturas/dimero_PD__p0.extxyz"}, {"id": "uma_t", "arquivo": "calc/uma/estruturas/dimero_T__p0.extxyz"},
               {"id": "sp_pd", "arquivo": "calc/orca/sp_na_geometria_uma/sp_dimero_PD__p0.out"}, {"id": "sp_t", "arquivo": "calc/orca/sp_na_geometria_uma/sp_dimero_T__p0.out"}]
        cfg = {"estruturas": est, "forcas": [{"id": "fpd", "a": "uma_pd", "b": "sp_pd"}],
               "comparacao_energia": [{"id": "c", "referencia": "PD", "itens": [{"rotulo": "PD", "a": "uma_pd", "b": "sp_pd"}, {"rotulo": "T", "a": "uma_t", "b": "sp_t"}]}],
               "regras": [regra(grandezas={"R": {"valor": 1.0, "unidade": "kJ/mol"}, "U": {"comparacao": "c.max_abs", "unidade": "kJ/mol"},
                                            "F": {"forcas": "fpd.mae"}})]}
        D = montar(cfg)
        c = D["relativa"][0]["metricas"]
        g = {x["id"]: x for x in D["regras"][0]["grandezas"]}
        self.assertAlmostEqual(g["U"]["valor"], c["max_abs"] * 96.48533212, places=9)       # eV -> kJ/mol
        self.assertEqual(g["F"]["unidade"], "meV/Å")
        self.assertAlmostEqual(g["F"]["valor"], D["valid"]["sistemas"][0]["mae"])
        # campo inexistente: aviso e sem veredito
        cfg["regras"][0]["grandezas"]["U"] = {"comparacao": "naoexiste.max_abs"}
        D = montar(cfg)
        self.assertIsNone(D["regras"][0]["resultado"])


# ----------------------------------------------------------------------------------------------------------
# ressalvas
# ----------------------------------------------------------------------------------------------------------
@unittest.skipUnless(tem_ase(), "precisa do ASE")
class TestRessalvas(unittest.TestCase):
    def test_por_secao_por_estrutura_globais_e_inline(self):
        cfg = {"estruturas": [{"id": "a", "arquivo": "calc/uma/estruturas/benzeno.extxyz", "grupo": "g", "ressalvas": ["própria da estrutura a"]},
                              {"id": "b", "arquivo": "calc/uma/estruturas/dimero_PD__p0.extxyz", "grupo": "g"}],
               "ressalvas": [{"texto": "só na seção de ranking", "severidade": "info", "secoes": ["ranking"]},
                             {"texto": "no grupo g", "severidade": "erro", "estruturas": ["g"]},
                             {"texto": "global"},
                             "só texto"]}
        D = montar(cfg)
        rs = D["ressalvas"]
        self.assertEqual([(r["texto"], r["sev"], r["secoes"], r["estruturas"]) for r in rs],
                         [("só na seção de ranking", "info", ["ranking"], []), ("no grupo g", "bad", [], ["g"]), ("global", "warn", [], []), ("só texto", "warn", [], [])])
        est = {e["id"]: e for e in D["est"]}
        self.assertEqual({r["texto"] for r in est["a"]["rs"]}, {"no grupo g", "própria da estrutura a"})
        self.assertEqual([r["texto"] for r in est["b"]["rs"]], ["no grupo g"])
        self.assertEqual(D["avisos"], [])

    def test_inline_em_parcelas_ranking_forcas_comparacao_e_regra(self):
        est = [{"id": "uma_pd", "arquivo": "calc/uma/estruturas/dimero_PD__p0.extxyz", "grupo": "u", "item": "PD"}, {"id": "sp_pd", "arquivo": "calc/orca/sp_na_geometria_uma/sp_dimero_PD__p0.out"}]
        cfg = {"estruturas": est, "energia": {"termos": {"A": "uma_pd"}, "parcelas": [{"nome": "p", "expr": "A - A", "ressalvas": ["da parcela"]}]},
               "ranking": [{"grupo": "u", "ressalvas": [{"texto": "do ranking", "severidade": "bad"}]}],
               "forcas": [{"a": "uma_pd", "b": "sp_pd", "ressalvas": ["da força"]}],
               "comparacao_energia": [{"id": "c", "ressalvas": ["da comparação"], "itens": [
                   {"rotulo": "X", "a": {"valor": 0}, "b": {"valor": 0}}, {"rotulo": "Y", "a": {"valor": 1}, "b": {"valor": 1}}]}],
               "regras": [regra(ressalvas=["da regra"])]}
        D = montar(cfg)
        self.assertEqual(D["energia"]["parcelas"][0]["rs"], [{"texto": "da parcela", "sev": "warn"}])
        self.assertEqual(D["ranking"][0]["rs"], [{"texto": "do ranking", "sev": "bad"}])
        self.assertEqual(D["valid"]["sistemas"][0]["ressalvas"], [{"texto": "da força", "sev": "warn"}])
        self.assertEqual(D["relativa"][0]["ressalvas"], [{"texto": "da comparação", "sev": "warn"}])
        self.assertEqual(D["regras"][0]["ressalvas"], [{"texto": "da regra", "sev": "warn"}])

    def test_ressalva_sem_texto_e_alvo_inexistente_avisam(self):
        D = montar({"estruturas": [{"id": "a", "arquivo": "calc/uma/estruturas/benzeno.extxyz"}],
                    "ressalvas": [{"texto": "  "}, {"severidade": "bad"}, {"texto": "x", "id": "r1", "estruturas": ["nao_existe"]}]})
        self.assertEqual(len(D["ressalvas"]), 1)                           # só a que tem texto; as sem texto são ignoradas
        self.assertEqual(sum("sem texto" in a for a in D["avisos"]), 1)    # (aviso único: mesma mensagem)
        self.assertTrue(any("nao_existe" in a for a in D["avisos"]), D["avisos"])


# ----------------------------------------------------------------------------------------------------------
# idioma: nenhuma mensagem do lado Python fica só em português
# ----------------------------------------------------------------------------------------------------------
class TestIdioma(unittest.TestCase):
    def test_textos_pt_e_en_tem_as_mesmas_chaves(self):
        self.assertEqual(set(TXT["pt"]), set(TXT["en"]))
        for k in TXT["pt"]:
            if not isinstance(TXT["pt"][k], str):
                continue
            self.assertEqual(TXT["pt"][k].count("{"), TXT["en"][k].count("{"), k)      # mesmos campos de formatação

    def test_chaves_do_template_pt_e_en_coincidem(self):
        h = (SKILL / "assets" / "painel_template.html").read_text(encoding="utf-8")
        i, j, k = h.index("const I18N = {"), h.index("\nen: {"), h.index("const t = k =>")
        chaves = lambda bloco: set(re.findall(r"(?:^|[,{])\s*([A-Za-z_][A-Za-z0-9_]*):\s*['`]", bloco, re.M))   # noqa: E731
        pt, en = chaves(h[i:j]), chaves(h[j:k])
        self.assertEqual(pt - en, set(), "chaves do template sem tradução em inglês")
        self.assertEqual(en - pt, set())
        self.assertGreater(len(pt), 250)

    def test_msg_traduz_recursivamente_e_exceções(self):
        m = Msg("r_nao_li", arq="x.out", tipo="ValueError", erro=ValueError(Msg("r_e_sel", t="q")))
        self.assertIn("não consegui ler", m)
        self.assertEqual(traduzir(m, "en"), "x.out: could not read (ValueError: unknown selection: q)")
        self.assertEqual(traduzir(ValueError(Msg("r_e_sel", t="q")), "pt"), "seleção desconhecida: q")
        self.assertEqual(traduzir("texto comum", "en"), "texto comum")

    def test_notas_dos_leitores_saem_no_idioma_da_configuracao(self):
        fila = [{"saida": "orca/dimero_PD_em_andamento.out", "nome": "o"}, {"saida": "cp2k/agua_geo/SINTETICO_agua.out", "nome": "c"}]
        en = montar({"fila": fila}, lang="en", base=AMOSTRAS)
        pt = montar({"fila": fila}, lang="pt", base=AMOSTRAS)
        nota = lambda D, n: next(j for j in D["fila"] if j["nome"] == n)["criterio"]["nota"]       # noqa: E731
        self.assertTrue(nota(en, "o").startswith("ORCA also requires TolRMSP"), nota(en, "o"))
        self.assertTrue(nota(pt, "o").startswith("o ORCA exige também TolRMSP"), nota(pt, "o"))
        self.assertTrue(nota(en, "c").startswith("compare CP2K's Convergence column"), nota(en, "c"))
        self.assertTrue(nota(pt, "c").startswith("compare a coluna Convergence do CP2K"), nota(pt, "c"))
        # o cartão de métodos também usa a nota traduzida
        campos = [c for card in en["metodos"]["cards"] for c in card["campos"] if c[0] == "SCF criterion"]
        self.assertTrue(campos and all("ORCA also" in c[1] or "CP2K's Convergence" in c[1] or "not recorded" in c[1] for c in campos), campos)

    @unittest.skipUnless(tem_ase(), "precisa do ASE")
    def test_selo_da_tarefa_do_mlip_no_idioma(self):
        est = [{"id": "a", "arquivo": "calc/uma/estruturas/benzeno.extxyz"}]
        self.assertEqual(montar({"estruturas": est}, lang="pt")["est"][0]["selo"], "uma-s-1p2p1 (tarefa omol) · fairchem-core 2.22.0")
        self.assertEqual(montar({"estruturas": est}, lang="en")["est"][0]["selo"], "uma-s-1p2p1 (task omol) · fairchem-core 2.22.0")

    def test_avisos_do_lado_python_em_ingles(self):
        D = montar({"estruturas": [{"id": "a", "arquivo": "nao_existe.xyz"}], "ressalvas": [{"texto": " "}], "forcas": [{"a": "x"}]}, lang="en")
        self.assertTrue(D["avisos"])
        for a in D["avisos"]:
            self.assertFalse(re.search(r"não|ausente|ilegível|sem |faltam|forças|estrutura ", a), a)


if __name__ == "__main__":
    unittest.main()
