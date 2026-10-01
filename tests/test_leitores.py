"""Leitores: valores esperados lidos DIRETO dos arquivos de exemplo (regex no texto), não da saída do leitor."""
import json
import re
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from _comum import AMOSTRAS, DIMERO, ORCA_DIMERO, cli, energia_final_orca, tem_ase, L

HA = L.HA_EV
RY = L.RY_EV
UMA = DIMERO / "calc" / "uma"


def txt(p):
    return Path(p).read_text(encoding="utf-8", errors="replace")


def freqs_orca_out(p):
    """frequências da seção VIBRATIONAL FREQUENCIES do .out (cm-1), em ordem crescente."""
    t = txt(p)
    bloco = t.split("VIBRATIONAL FREQUENCIES", 1)[1].split("NORMAL MODES", 1)[0]
    return sorted(float(x) for x in re.findall(r"^\s*\d+:\s+(-?\d+\.\d+)\s+cm", bloco, re.M))


def zpe_esperada(freqs):
    """metade da soma das frequências reais (descartados os modos de translação/rotação, ≈ 0 cm-1), em kJ/mol."""
    pos = [f for f in freqs if f > 1e-3]
    return 0.5 * sum(pos) * 0.011962656


class TestOrcaReal(unittest.TestCase):
    """B97-3c Opt Freq do benzeno e do dímero PD (ORCA 6.1.1, dados reais)."""

    @classmethod
    def setUpClass(cls):
        cls.R = {n: L.ler(ORCA_DIMERO / n / f"{n}.out") for n in ("benzeno", "dimero_PD")}

    def test_identificacao_e_nivel(self):
        for n, R in self.R.items():
            with self.subTest(n):
                self.assertEqual(R["programa"], "ORCA")
                self.assertEqual(R["versao"], "6.1.1")
                self.assertEqual(R["nivel"]["metodo"], "B97-3c")
                self.assertEqual(R["nivel"]["linha"], "! B97-3c Opt Freq TightSCF")
                self.assertEqual(R["tipo"], "opt+freq")
                self.assertEqual(L.estado_final(R), "concluido")
                self.assertTrue(R["convergiu"])
                self.assertEqual(R["avisos"], [])

    def test_energia_final(self):
        for n, R in self.R.items():
            with self.subTest(n):
                esperado = energia_final_orca(ORCA_DIMERO / n / f"{n}.out") * HA
                self.assertAlmostEqual(R["energia_eV"], esperado, places=6)
        self.assertAlmostEqual(self.R["benzeno"]["energia_eV"], -232.130430103136 * HA, places=6)

    def test_geometrias_e_passos_da_otimizacao(self):
        for n, nat in (("benzeno", 12), ("dimero_PD", 24)):
            with self.subTest(n):
                R = self.R[n]
                p = ORCA_DIMERO / n / f"{n}.out"
                fspe = [float(x) for x in re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", txt(p))]
                trj = (ORCA_DIMERO / n / f"{n}_trj.xyz").read_text()
                n_trj = len(re.findall(rf"^\s*{nat}\s*$", trj, re.M))
                self.assertEqual(len(R["quadros"]), n_trj)
                self.assertEqual(len(R["quadros"]), len(fspe))          # um quadro por energia de ciclo
                self.assertTrue(all(len(q["simbolos"]) == nat for q in R["quadros"]))
                self.assertEqual(R["quadros"][0]["simbolos"].count("C"), nat // 2)
                np.testing.assert_allclose([q["E_eV"] for q in R["quadros"]], np.array(fspe) * HA, atol=1e-5)
                self.assertEqual(R["extra"]["n_ciclos_opt"], txt(p).count("GEOMETRY OPTIMIZATION CYCLE"))
                E = [q["E_eV"] for q in R["quadros"]]
                self.assertTrue(all(b <= a + 1e-6 for a, b in zip(E, E[1:])))   # energia não sobe numa otimização

    def test_frequencias(self):
        for n, nfreq, nimag_out in (("benzeno", 36, 0), ("dimero_PD", 72, 2)):
            with self.subTest(n):
                R = self.R[n]
                fr = R["freq"]
                self.assertIsNotNone(fr)
                esperadas = freqs_orca_out(ORCA_DIMERO / n / f"{n}.out")
                self.assertEqual(len(esperadas), nfreq)
                self.assertEqual(len(fr["freqs_cm1"]), nfreq)
                np.testing.assert_allclose(fr["freqs_cm1"], esperadas, atol=0.05)
                self.assertEqual(sum(1 for f in esperadas if f < 0), nimag_out)
                self.assertEqual(fr["freqs_cm1"], sorted(fr["freqs_cm1"]))
                self.assertEqual(len(fr["modos"]), nfreq)
                self.assertEqual(len(fr["modos"][0]), len(R["quadros"][0]["simbolos"]))
                self.assertAlmostEqual(fr["zpe_kJmol"], zpe_esperada(esperadas), delta=0.01)

    def test_imaginarias_pequenas_sao_ruido(self):
        """o dímero tem -16,06 e -7,39 cm-1 (ruído numérico, acima do limiar de -20): ficam na lista, mas n_imag = 0."""
        fr = self.R["dimero_PD"]["freq"]
        self.assertIn(-16.06, fr["freqs_cm1"])
        self.assertIn(-7.39, fr["freqs_cm1"])
        self.assertEqual(fr["n_imag"], 0)
        self.assertEqual(self.R["benzeno"]["freq"]["n_imag"], 0)

    def test_limiar_de_imaginarias(self):
        f = L.montar_freq([-350.0, -5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0, 200.0])
        self.assertEqual(f["n_imag"], 1)                                # só -350 passa do limiar de -20 cm-1
        self.assertEqual(f["freqs_cm1"][0], -350.0)
        self.assertAlmostEqual(f["zpe_kJmol"], 0.5 * (100 + 200) * 0.011962656, places=3)

    def test_scf(self):
        for n, R in self.R.items():
            with self.subTest(n):
                self.assertEqual(R["n_ciclos_scf"], 4)
                self.assertTrue(R["scf_convergiu"])
                self.assertEqual(R["scf_criterio"]["nome"], "TolE")
                self.assertEqual(R["scf_criterio"]["valor"], 1e-8)
                ciclos = [int(x) for x in re.findall(r"SCF CONVERGED AFTER\s+(\d+) CYCLES", txt(ORCA_DIMERO / n / f"{n}.out"))]
                self.assertEqual(len(ciclos), 4)
                self.assertEqual(len(R["scf"]), ciclos[-1])             # iterações do último ciclo SCF
                self.assertEqual([it["it"] for it in R["scf"]], list(range(1, ciclos[-1] + 1)))
                self.assertTrue(abs(R["scf"][-1]["dE"]) < R["scf_criterio"]["valor"] * 1e3)

    def test_duracao(self):
        self.assertAlmostEqual(self.R["benzeno"]["duracao_s"], 49.386, places=3)
        self.assertAlmostEqual(self.R["dimero_PD"]["duracao_s"], 4 * 60 + 34.445, places=3)

    def test_carga_multiplicidade(self):
        for R in self.R.values():
            self.assertEqual((R["carga"], R["mult"]), (0, 1))

    def test_hess(self):
        p = ORCA_DIMERO / "benzeno" / "benzeno.hess"
        H = L.ler(p)
        self.assertEqual(L.detectar(p), "orca_hess")
        self.assertEqual(len(H["freq"]["freqs_cm1"]), 36)
        self.assertEqual(len(H["quadros"][0]["simbolos"]), 12)
        self.assertIsNone(H["versao"])                                  # o .hess não traz versão: não se inventa
        self.assertEqual(H["nivel"], {})


class TestOrcaSP(unittest.TestCase):
    def test_single_points_na_geometria_uma(self):
        for nome, nat in (("sp_benzeno", 12), ("sp_dimero_PD__p0", 24)):
            with self.subTest(nome):
                p = ORCA_DIMERO / "sp_na_geometria_uma" / f"{nome}.out"
                R = L.ler(p)
                self.assertEqual((R["programa"], R["versao"]), ("ORCA", "6.1.1"))
                self.assertEqual(R["nivel"]["metodo"], "B97-3c")
                self.assertEqual(R["nivel"]["linha"], "! B97-3c TightSCF EnGrad")
                self.assertEqual(R["tipo"], "sp")
                self.assertEqual(L.estado_final(R), "concluido")
                self.assertAlmostEqual(R["energia_eV"], energia_final_orca(p) * HA, places=6)
                self.assertEqual(len(R["quadros"]), 1)
                self.assertEqual(len(R["quadros"][0]["simbolos"]), nat)
                self.assertIsNone(R["freq"])
                self.assertIsNone(R["convergiu"])                       # não é otimização
                self.assertEqual(R["n_ciclos_scf"], 1)

    def test_energia_de_interacao_plausivel(self):
        """E(dímero) - 2 E(benzeno) com o B97-3c: atração de dispersão de poucas dezenas de kJ/mol, no máximo."""
        eb = L.ler(ORCA_DIMERO / "benzeno" / "benzeno.out")["energia_eV"]
        ed = L.ler(ORCA_DIMERO / "dimero_PD" / "dimero_PD.out")["energia_eV"]
        esperado = (energia_final_orca(ORCA_DIMERO / "dimero_PD" / "dimero_PD.out")
                    - 2 * energia_final_orca(ORCA_DIMERO / "benzeno" / "benzeno.out")) * HA * 96.48533212
        kj = (ed - 2 * eb) * 96.48533212
        self.assertAlmostEqual(kj, esperado, places=4)
        self.assertTrue(-20 < kj < -5, kj)


class TestOrcaEmAndamento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = AMOSTRAS / "orca" / "dimero_PD_em_andamento.out"
        cls.R = L.ler(cls.p)

    def test_estado_rodando_ou_parado_conforme_a_idade(self):
        self.assertEqual(self.R["estado"], "rodando?")                  # sem 'TERMINATED NORMALLY'
        mt = self.R["mtime"]
        self.assertEqual(L.estado_final(self.R, ativo_s=1800, agora=mt + 60), "rodando")
        self.assertEqual(L.estado_final(self.R, ativo_s=1800, agora=mt + 7200), "parado")

    def test_conteudo_parcial(self):
        R = self.R
        self.assertEqual((R["programa"], R["versao"]), ("ORCA", "6.1.1"))
        self.assertEqual(R["nivel"]["metodo"], "B97-3c")
        self.assertEqual(R["tipo"], "opt+freq")
        self.assertEqual(len(R["quadros"]), 2)                          # ciclos 1 e 2 (o 2º ainda sem energia)
        self.assertEqual(len(R["quadros"][0]["simbolos"]), 24)
        self.assertAlmostEqual(R["quadros"][0]["E_eV"], -464.264496486363 * HA, places=6)
        self.assertIsNone(R["quadros"][1]["E_eV"])
        self.assertAlmostEqual(R["energia_eV"], -464.264496486363 * HA, places=6)
        self.assertEqual(R["n_ciclos_scf"], 2)
        self.assertIsNone(R["freq"])
        self.assertIsNone(R["duracao_s"])                               # sem TOTAL RUN TIME
        self.assertIsNone(R["convergiu"])
        self.assertIsNone(R["fim"])


class TestCP2K(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = AMOSTRAS / "cp2k"
        cls.agua = L.ler(cls.dir / "agua_geo" / "SINTETICO_agua.out")
        cls.falhou = L.ler(cls.dir / "falhou" / "SINTETICO_falhou.out")

    @staticmethod
    def _ultimo_bloco_scf(p):
        """(iteração, Convergence, energia) das linhas 'OT DIIS' do último bloco SCF, lidas por regex no texto."""
        t = txt(p)
        bloco = re.split(r"Step\s+Update method\s+Time\s+Convergence\s+Total energy\s+Change", t)[-1]
        linhas = re.findall(r"^\s*(\d+)\s+OT DIIS\s+\S+\s+\S+\s+(\d\.\d+)\s+(-\d+\.\d+)\s+(\S+)\s*$", bloco, re.M)
        return [(int(i), float(c), float(e)) for i, c, e, _ in linhas]

    def test_cabecalho_e_nivel(self):
        R = self.agua
        self.assertEqual((R["programa"], R["versao"]), ("CP2K", "2024.1"))
        self.assertEqual(R["tipo"], "opt")                              # Run type GEO_OPT
        n = R["nivel"]
        self.assertEqual((n["funcional"], n["dispersao"], n["base"], n["corte"], n["scf"]),
                         ("PBE", "DFT-D3", "DZVP-MOLOPT-SR-GTH", "400 Ry", "OT"))
        self.assertEqual(n["metodo"], "PBE DFT-D3")
        self.assertEqual((R["carga"], R["mult"]), (0, 1))

    def test_estado_rodando_sem_program_ended(self):
        self.assertEqual(self.agua["estado"], "rodando?")
        self.assertEqual(L.estado_final(self.agua, agora=self.agua["mtime"] + 5), "rodando")
        self.assertIsNone(self.agua["fim"])

    def test_geometria_e_energias_do_xyz(self):
        R = self.agua
        self.assertEqual(len(R["quadros"]), 3)
        self.assertTrue(all(q["simbolos"] == ["O", "H", "H"] for q in R["quadros"]))
        esperado = [float(x) for x in re.findall(r"E =\s+(-?\d+\.\d+)", txt(self.dir / "agua_geo" / "SINTETICO_agua-pos-1.xyz"))]
        self.assertEqual(len(esperado), 3)
        np.testing.assert_allclose([q["E_eV"] for q in R["quadros"]], np.array(esperado) * HA, atol=1e-6)
        ens = [float(x) for x in re.findall(r"Total FORCE_EVAL \( QS \) energy \[a\.u\.\]:\s+(-?\d+\.\d+)",
                                            txt(self.dir / "agua_geo" / "SINTETICO_agua.out"))]
        self.assertAlmostEqual(R["energia_eV"], ens[-1] * HA, places=6)

    def test_scf_coluna_convergence(self):
        R = self.agua
        self.assertEqual(R["scf_criterio"]["nome"], "EPS_SCF")
        self.assertEqual(R["scf_criterio"]["valor"], 1e-6)
        self.assertEqual(R["scf_criterio"]["coluna"], "Convergence")
        self.assertEqual(R["n_ciclos_scf"], 4)
        esperado = self._ultimo_bloco_scf(self.dir / "agua_geo" / "SINTETICO_agua.out")
        self.assertEqual(len(esperado), 5)
        self.assertEqual([it["it"] for it in R["scf"]], [i for i, _, _ in esperado])
        np.testing.assert_allclose([it["conv"] for it in R["scf"]], [c for _, c, _ in esperado])
        np.testing.assert_allclose([it["E"] for it in R["scf"]], [e for _, _, e in esperado])
        self.assertEqual(R["scf_unidade_E"], "Ha")
        # o último ciclo está em curso: ainda acima de EPS_SCF, e o SCF não é dado como convergido
        self.assertGreater(R["scf"][-1]["conv"], R["scf_criterio"]["valor"])
        self.assertFalse(R["scf_convergiu"])

    def test_falhou_scf_nao_convergiu(self):
        R = self.falhou
        self.assertEqual(R["estado"], "falhou")
        self.assertEqual(L.estado_final(R), "falhou")                   # 'falhou' não depende da idade do arquivo
        self.assertFalse(R["scf_convergiu"])
        self.assertTrue(any("SCF" in a and "não convergiu" in a for a in R["avisos"]), R["avisos"])
        self.assertEqual(len(R["scf"]), 50)
        esperado = self._ultimo_bloco_scf(self.dir / "falhou" / "SINTETICO_falhou.out")
        np.testing.assert_allclose([it["conv"] for it in R["scf"]], [c for _, c, _ in esperado])
        self.assertAlmostEqual(R["scf"][-1]["conv"], 0.09720114)
        self.assertGreater(min(it["conv"] for it in R["scf"]), R["scf_criterio"]["valor"])
        self.assertIsNone(R["energia_eV"])                              # nenhuma energia final impressa
        self.assertEqual(R["quadros"], [])
        self.assertEqual(R["duracao_s"], 1200)                          # 09:00:00 -> 09:20:00
        self.assertIsNone(R["convergiu"])

    def test_nivel_nao_inventado_sem_cabecalho(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "min.out"
            p.write_text(" **** PROGRAM STARTED AT 2026-10-01 09:00:00.000\n CP2K| version string: CP2K version 9.9\n"
                         " GLOBAL| Run type ENERGY\n **** PROGRAM ENDED AT 2026-10-01 09:00:05.000\n")
            R = L.ler(p)
            self.assertEqual(R["versao"], "9.9")
            self.assertIsNone(R["nivel"]["metodo"])
            self.assertIsNone(R["nivel"]["funcional"])
            self.assertIsNone(R["energia_eV"])
            self.assertEqual(R["duracao_s"], 5)


class TestVASP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = AMOSTRAS / "vasp" / "si_relax"
        cls.R = L.ler(cls.dir / "OUTCAR")

    def test_outcar(self):
        R = self.R
        self.assertEqual(L.detectar(self.dir / "OUTCAR"), "vasp_outcar")
        self.assertEqual((R["programa"], R["versao"]), ("VASP", "6.4.2"))
        n = R["nivel"]
        self.assertEqual((n["funcional"], n["dispersao"], n["corte"], n["metodo"]), ("PBE", "DFT-D3(BJ)", "520 eV", "PBE DFT-D3(BJ)"))
        self.assertEqual(R["tipo"], "opt-celula")                       # IBRION 2 + ISIF 3
        self.assertEqual(L.estado_final(R), "concluido")
        self.assertTrue(R["convergiu"])
        self.assertEqual(R["duracao_s"], 42.317)
        self.assertEqual(R["scf_criterio"]["nome"], "EDIFF")
        self.assertEqual(R["scf_criterio"]["valor"], 1e-6)

    def test_energia_e_geometria(self):
        R = self.R
        sigma0 = [float(x) for x in re.findall(r"energy\(sigma->0\)\s*=\s*(-?\d+\.\d+)", txt(self.dir / "OUTCAR"))]
        self.assertEqual(len(sigma0), 2)
        self.assertEqual(R["energia_eV"], sigma0[-1])
        self.assertEqual(len(R["quadros"]), 2)
        self.assertEqual(R["quadros"][0]["simbolos"], ["Si", "Si"])
        self.assertEqual([q["E_eV"] for q in R["quadros"]], sigma0)
        self.assertIsNotNone(R["quadros"][0]["celula"])
        self.assertTrue(R["quadros"][0]["pbc"])
        self.assertAlmostEqual(R["quadros"][-1]["fmax"], float(np.hypot(0.01, 0.01)))

    def test_scf_do_oszicar(self):
        t = txt(self.dir / "OSZICAR")
        ciclos = re.split(r"^\s*\d+ F=.*$", t, flags=re.M)
        n_it = [len(re.findall(r"^DAV:", c, re.M)) for c in ciclos if "DAV:" in c]
        self.assertEqual(n_it, [8, 5])
        self.assertEqual(self.R["n_ciclos_scf"], 2)
        self.assertEqual(len(self.R["scf"]), n_it[-1])                  # último ciclo eletrônico
        O = L.ler(self.dir / "OSZICAR")
        self.assertEqual(L.detectar(self.dir / "OSZICAR"), "vasp_oszicar")
        self.assertEqual(O["n_ciclos_scf"], 2)
        self.assertAlmostEqual(O["energia_eV"], -10.8265)               # E0 do último passo iônico
        self.assertEqual(O["quadros"], [])
        self.assertIn(L.estado_final(O), ("rodando", "parado"))         # OSZICAR sozinho não diz se terminou


class TestGaussian(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = AMOSTRAS / "gaussian" / "SINTETICO_agua.log"
        cls.R = L.ler(cls.p)

    def test_cabecalho_nivel_estado(self):
        R = self.R
        self.assertEqual(R["programa"], "Gaussian")
        self.assertEqual(R["versao"], "16 (ES64L-G16RevC.01)")
        self.assertEqual(R["nivel"]["metodo"], "B3LYP/6-31G(d)")
        self.assertEqual(R["nivel"]["dispersao"], "GD3BJ")
        self.assertEqual(R["tipo"], "opt+freq")
        self.assertEqual((R["carga"], R["mult"]), (0, 1))
        self.assertEqual(L.estado_final(R), "concluido")
        self.assertTrue(R["convergiu"])
        self.assertEqual(R["duracao_s"], 12.3)

    def test_energia_scf_e_otimizacao(self):
        R = self.R
        ens = [float(x) for x in re.findall(r"SCF Done:\s+E\(\w+\)\s+=\s+(-?\d+\.\d+)", txt(self.p))]
        self.assertEqual(len(ens), 3)
        self.assertAlmostEqual(R["energia_eV"], ens[-1] * HA, places=6)
        self.assertEqual(len(R["quadros"]), 3)
        self.assertTrue(all(q["simbolos"] == ["O", "H", "H"] for q in R["quadros"]))
        self.assertEqual(R["n_ciclos_scf"], 3)
        self.assertIsNot(R["scf_convergiu"], False)                     # o leitor não decide (None), mas não marca falha

    def test_frequencias(self):
        esperadas = [float(x) for x in re.findall(r"Frequencies --\s+(.*)", txt(self.p))[0].split()]
        fr = self.R["freq"]
        self.assertEqual(fr["freqs_cm1"], esperadas)
        self.assertEqual(len(fr["freqs_cm1"]), 3)
        self.assertEqual(fr["n_imag"], 0)
        self.assertEqual(len(fr["modos"]), 3)
        self.assertAlmostEqual(fr["zpe_kJmol"], 0.5 * sum(esperadas) * 0.011962656, places=2)   # 3N-6 = 3 modos, nenhum excluído


class TestQE(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = AMOSTRAS / "qe" / "SINTETICO_si_relax.out"
        cls.R = L.ler(cls.p)

    def test_cabecalho_nivel_estado(self):
        R = self.R
        self.assertEqual((R["programa"], R["versao"]), ("Quantum ESPRESSO (pw.x)", "7.2"))
        self.assertEqual(R["nivel"]["funcional"], "PBE")
        self.assertEqual(R["nivel"]["corte"], "30 Ry")
        self.assertIsNone(R["nivel"]["dispersao"])                      # sem vdw_corr no arquivo
        self.assertEqual(L.estado_final(R), "concluido")

    def test_energia_final_e_scf(self):
        R = self.R
        t = txt(self.p)
        final = float(re.search(r"Final energy\s+=\s+(-?\d+\.\d+)", t).group(1))
        bang = [float(x) for x in re.findall(r"^!\s+total energy\s+=\s+(-?\d+\.\d+)", t, re.M)]
        self.assertEqual(final, bang[-1])
        self.assertAlmostEqual(R["energia_eV"], final * RY, places=6)
        self.assertEqual(R["n_ciclos_scf"], len(bang))
        self.assertEqual(R["scf_criterio"]["nome"], "conv_thr")
        self.assertTrue(R["scf_convergiu"])
        self.assertEqual(len(R["scf"]), 4)                              # último ciclo: 4 iterações

    @unittest.skipUnless(tem_ase(), "ASE não instalado: as geometrias do pw.x são lidas via ase.io (espresso-out)")
    def test_geometrias_via_ase(self):
        R = self.R
        self.assertEqual(len(R["quadros"]), 2)
        self.assertEqual(R["quadros"][0]["simbolos"], ["Si", "Si"])
        self.assertTrue(R["convergiu"])
        self.assertEqual(R["avisos"], [])

    @unittest.skipIf(tem_ase(), "só vale sem ASE")
    def test_sem_ase_avisa_em_vez_de_quebrar(self):
        self.assertEqual(self.R["quadros"], [])
        self.assertTrue(any("ase" in a.lower() for a in self.R["avisos"]), self.R["avisos"])


@unittest.skipUnless(tem_ase(), "ASE não instalado")
class TestASE(unittest.TestCase):
    def test_extxyz_uma(self):
        from ase.io import read
        p = UMA / "estruturas" / "benzeno.extxyz"
        a = read(p)
        R = L.ler(p)
        self.assertEqual(L.detectar(p), "ase")
        self.assertEqual(R["programa"], "fairchem-core")
        self.assertEqual(R["versao"], "2.22.0")
        self.assertEqual(R["nivel"]["modelo"], "uma-s-1p2p1")
        self.assertEqual(R["nivel"]["tarefa"], "omol")
        self.assertEqual(R["nivel"]["metodo"], "uma-s-1p2p1")
        self.assertEqual(len(R["quadros"]), 1)
        self.assertEqual(len(R["quadros"][0]["simbolos"]), len(a))
        self.assertAlmostEqual(R["energia_eV"], a.get_potential_energy(), places=9)
        self.assertEqual(L.classe_programa(R["programa"]), "MLIP")
        self.assertTrue(R["convergiu"])                                 # convergiu=T no cabeçalho do extxyz

    def test_traj_sem_nivel_nao_inventa(self):
        from ase.io import read
        p = UMA / "traj" / "benzeno.traj"
        fr = read(p, ":")
        R = L.ler(p)
        self.assertEqual(len(R["quadros"]), len(fr))
        self.assertEqual(len(R["quadros"]), 4)
        self.assertEqual(R["tipo"], "opt")
        self.assertAlmostEqual(R["energia_eV"], fr[-1].get_potential_energy(), places=9)
        np.testing.assert_allclose([q["E_eV"] for q in R["quadros"]], [a.get_potential_energy() for a in fr])
        self.assertIsNone(R["nivel"].get("metodo"))                     # o .traj não registra o nível
        self.assertIsNone(R["versao"])

    def test_dimero_extxyz(self):
        R = L.ler(UMA / "estruturas" / "dimero_PD__p0.extxyz")
        self.assertEqual(len(R["quadros"][0]["simbolos"]), 24)
        self.assertEqual(R["nivel"]["metodo"], "uma-s-1p2p1")

    def test_xyz_simples_sem_energia(self):
        R = L.ler(DIMERO / "calc" / "geometrias" / "benzeno.xyz")
        self.assertEqual(len(R["quadros"][0]["simbolos"]), 12)
        self.assertIsNone(R["programa"])
        self.assertIsNone(R["nivel"].get("metodo"))

    def test_formato_explicito(self):
        R = L.ler(UMA / "estruturas" / "benzeno.extxyz", formato="extxyz")
        self.assertEqual(len(R["quadros"][0]["simbolos"]), 12)


class TestJSON(unittest.TestCase):
    def test_freq_json_uma(self):
        for nome, nat in (("benzeno", 12), ("dimero_PD__p0", 24)):
            with self.subTest(nome):
                p = UMA / "freq" / f"{nome}.json"
                d = json.loads(p.read_text())
                R = L.ler(p)
                self.assertEqual(R["programa"], "fairchem-core")
                self.assertEqual(R["versao"], "2.22.0")
                self.assertEqual(R["nivel"]["modelo"], "uma-s-1p2p1")
                self.assertEqual(R["nivel"]["metodo"], "uma-s-1p2p1")
                self.assertEqual(len(R["freq"]["freqs_cm1"]), len(d["freqs_cm1"]))
                self.assertEqual(len(R["freq"]["freqs_cm1"]), 3 * nat)
                np.testing.assert_allclose(R["freq"]["freqs_cm1"], sorted(d["freqs_cm1"]), atol=0.006)
                self.assertEqual(R["freq"]["n_imag"], d["n_imaginarias"])
                self.assertEqual(R["freq"]["zpe_kJmol"], d["zpe_kJmol"])   # o valor do arquivo prevalece
                self.assertEqual(R["extra"]["rotulo"], "EXPLORATÓRIO")
                self.assertEqual(R["tipo"], "freq")
                self.assertEqual(L.estado_final(R), "concluido")

    def test_json_generico_com_energia(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.json"
            p.write_text(json.dumps({"programa": "X", "versao": "1", "nivel": "metodo-y", "energia_Ha": -1.5, "convergiu": True}))
            R = L.ler(p)
            self.assertAlmostEqual(R["energia_eV"], -1.5 * HA)
            self.assertEqual((R["programa"], R["versao"], R["nivel"]["metodo"]), ("X", "1", "metodo-y"))
            self.assertEqual(L.estado_final(R), "concluido")
            p.write_text(json.dumps({"energia_eV": -3.0}))
            R = L.ler(p)
            self.assertEqual(R["energia_eV"], -3.0)
            self.assertIsNone(R["programa"])                            # ausente => None, nunca inventado
            self.assertEqual(R["nivel"], {})

    def test_json_sem_esquema_e_ilegivel_com_aviso(self):
        R = L.ler(AMOSTRAS / "vivo" / "ao_vivo.json")                   # lido pela fila (json_vivo), não pelo leitor genérico
        self.assertEqual(R["estado"], "ilegivel")
        self.assertTrue(R["avisos"])


class TestJSONL(unittest.TestCase):
    def test_progresso_concluido(self):
        p = UMA / "progresso" / "benzeno.jsonl"
        linhas = [json.loads(x) for x in p.read_text().splitlines()]
        passos = [x for x in linhas if "passo" in x]
        R = L.ler(p)
        pr = R["progresso"]
        self.assertEqual(pr["n"], len(passos))
        self.assertEqual(pr["n"], 4)
        self.assertEqual(pr["serie"]["passo"], [0, 1, 2, 3])
        np.testing.assert_allclose(pr["serie"]["E"], [x["E_eV"] for x in passos])
        np.testing.assert_allclose(pr["serie"]["fmax"], [x["fmax_eVA"] for x in passos])
        self.assertTrue(pr["fim"]["convergiu"])
        self.assertEqual(L.estado_final(R), "concluido")

    def test_sem_linha_fim_e_rodando(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "p.jsonl"
            p.write_text('{"passo": 0, "E_eV": -1.0, "fmax_eVA": 0.5}\nlixo nao json\n{"passo": 1, "E_eV": -1.1, "fmax_eVA": 0.3}\n')
            R = L.ler(p)
            self.assertEqual(R["progresso"]["n"], 2)                    # linha inválida é ignorada
            self.assertEqual(R["estado"], "rodando?")
            self.assertEqual(L.estado_final(R, agora=time.time()), "rodando")


class TestDeteccaoEAusencia(unittest.TestCase):
    def test_detectar(self):
        casos = [(AMOSTRAS / "orca" / "dimero_PD_em_andamento.out", "orca"),
                 (AMOSTRAS / "cp2k" / "agua_geo" / "SINTETICO_agua.out", "cp2k"),
                 (AMOSTRAS / "gaussian" / "SINTETICO_agua.log", "gaussian"),
                 (AMOSTRAS / "qe" / "SINTETICO_si_relax.out", "qe"),
                 (AMOSTRAS / "vasp" / "si_relax" / "OUTCAR", "vasp_outcar"),
                 (AMOSTRAS / "cp2k" / "agua_geo" / "SINTETICO_agua-pos-1.xyz", "xyz_cp2k"),
                 (ORCA_DIMERO / "benzeno" / "benzeno_trj.xyz", "xyz_orca"),
                 (UMA / "progresso" / "benzeno.jsonl", "jsonl")]
        for p, esperado in casos:
            with self.subTest(p.name):
                self.assertEqual(L.detectar(p), esperado)

    def test_arquivo_ausente(self):
        R = L.ler(AMOSTRAS / "nao_existe.out")
        self.assertEqual(R["estado"], "ausente")
        self.assertTrue(R["avisos"])

    def test_xyz_orca_trj_direto(self):
        R = L.ler(ORCA_DIMERO / "benzeno" / "benzeno_trj.xyz")
        self.assertEqual(R["programa"], "ORCA")
        self.assertEqual(len(R["quadros"]), 4)
        self.assertAlmostEqual(R["energia_eV"], -232.130430103136 * HA, places=6)
        self.assertEqual(R["estado"], "desconhecido")                   # um .xyz não diz se o cálculo terminou

    def test_resultado_tem_sempre_as_mesmas_chaves(self):
        ref = set(L.novo("x").keys())
        arquivos = [AMOSTRAS / "orca" / "dimero_PD_em_andamento.out", AMOSTRAS / "cp2k" / "falhou" / "SINTETICO_falhou.out",
                    AMOSTRAS / "gaussian" / "SINTETICO_agua.log", AMOSTRAS / "vasp" / "si_relax" / "OUTCAR",
                    AMOSTRAS / "qe" / "SINTETICO_si_relax.out", ORCA_DIMERO / "benzeno" / "benzeno.out",
                    UMA / "freq" / "benzeno.json", AMOSTRAS / "nao_existe.out", AMOSTRAS / "vivo" / "ao_vivo.json"]
        for p in arquivos:
            with self.subTest(p.name):
                self.assertEqual(set(L.ler(p).keys()) - {"progresso", "scf_unidade_E"}, ref)


class TestCLILer(unittest.TestCase):
    def test_ler_imprime_o_resumo(self):
        r = cli("ler", ORCA_DIMERO / "benzeno" / "benzeno.out", AMOSTRAS / "cp2k" / "falhou" / "SINTETICO_falhou.out")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = r.stdout
        self.assertIn("detectado: orca · programa ORCA 6.1.1 · estado concluido", s)
        self.assertIn("nível: {'metodo': 'B97-3c'", s)
        self.assertIn("4 quadros (12 átomos)", s)
        self.assertIn("frequências: 36 (0 imaginárias)", s)
        self.assertIn("detectado: cp2k · programa CP2K 2024.1 · estado falhou", s)
        self.assertIn("aviso: SCF não convergiu", s)

    def test_ler_arquivo_inexistente_nao_quebra(self):
        r = cli("ler", AMOSTRAS / "nao_existe.out")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("aviso: arquivo não encontrado", r.stdout)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
