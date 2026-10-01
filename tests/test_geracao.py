"""Geração do painel (CLI `painel.py gerar/init/descobrir/--vigiar`): HTML único e offline, dados embutidos, idiomas, avisos."""
import copy
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import os
from pathlib import Path

from _comum import (AMOSTRAS, DIMERO, ORCA_DIMERO, PAINEL_PY, SKILL, analisar_html, cli, dados_do_html, energia_final_orca,
                    tem_ase, tem_yaml, L)

HA = L.HA_EV
SECOES = ["meta", "etapas", "andamento", "est", "reacao", "filmes", "filmes_omitidos", "energia", "ranking", "medidas", "freq",
          "fila", "fila_meta", "glossario", "metodos", "avisos"]


def carregar_yaml(p):
    import yaml
    return yaml.safe_load(Path(p).read_text(encoding="utf-8"))


def gravar_yaml(p, cfg):
    import yaml
    Path(p).write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


@unittest.skipUnless(tem_yaml(), "PyYAML não instalado")
class _ComTmp(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.addCleanup(self._t.cleanup)

    def config_derivada(self, exemplo, **mudancas):
        """cópia da configuração do exemplo gravada no tmp, apontando `raiz` para o exemplo (não toca em examples/)."""
        cfg = carregar_yaml(exemplo / "painel.yaml")
        cfg["raiz"] = str(exemplo)
        cfg.update(mudancas)
        p = self.tmp / "painel.yaml"
        gravar_yaml(p, cfg)
        return p

    def gerar(self, cfg, nome="saida.html"):
        r = cli("gerar", cfg, "-o", self.tmp / nome)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        return self.tmp / nome, r


@unittest.skipUnless(tem_yaml(), "PyYAML não instalado")
class _ExemplosGerados(unittest.TestCase):
    """gera cada exemplo UMA vez numa pasta temporária (o painel.html do repositório não é tocado)."""

    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._t.name)
        cls.saida = {}
        cls.stdout = {}
        for nome, ex in (("dimero", DIMERO), ("amostras", AMOSTRAS)):
            alvo = cls.tmp / f"{nome}.html"
            r = cli("gerar", ex / "painel.yaml", "-o", alvo)
            assert r.returncode == 0, r.stdout + r.stderr
            cls.saida[nome], cls.stdout[nome] = alvo, r.stdout
        cls.html = {k: v.read_text(encoding="utf-8") for k, v in cls.saida.items()}
        cls.D = {k: dados_do_html(h) for k, h in cls.html.items()}
        cls.pag = {k: analisar_html(h) for k, h in cls.html.items()}

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()


class TestHTMLUnicoOffline(_ExemplosGerados):
    def test_nenhum_recurso_externo(self):
        for nome, pag in self.pag.items():
            with self.subTest(nome):
                for tag, at in pag.tags:
                    for atr in ("src", "href", "data", "poster", "action"):
                        v = (at.get(atr) or "").strip().lower()
                        self.assertFalse(v.startswith(("http:", "https:", "//", "ftp:")), f"<{tag} {atr}={v}>")
                self.assertFalse([a for t, a in pag.tags if t == "script" and "src" in a], "todo <script> deve ser embutido")
                self.assertFalse([a for t, a in pag.tags if t == "link"], "sem <link> externo (CSS embutido)")
                self.assertFalse([a for t, a in pag.tags if t == "img" and (a.get("src") or "").startswith("http")])

    def test_3dmol_e_plotly_embutidos(self):
        for nome, pag in self.pag.items():
            with self.subTest(nome):
                grandes = [s for s in pag.scripts if len(s) > 100_000]
                self.assertGreaterEqual(len(grandes), 2)
                tres = [s for s in grandes if "3Dmol" in s[:400000] and "$3Dmol" in s]
                plotly = [s for s in grandes if "Plotly" in s and "plotly.js" in s]
                self.assertTrue(tres, "3Dmol.js não está embutido")
                self.assertTrue(plotly, "plotly.js não está embutido")
                # idêntico ao arquivo de assets/vendor (menos a proteção de '</script')
                v3 = (SKILL / "assets" / "vendor" / "3Dmol-min.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
                vp = (SKILL / "assets" / "vendor" / "plotly.min.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
                self.assertIn(v3, self.html[nome])
                self.assertIn(vp, self.html[nome])

    def test_marcadores_do_modelo_todos_substituidos(self):
        for nome, h in self.html.items():
            with self.subTest(nome):
                for marca in ("__DADOS__", "__LANG__", "__TITULO__", "/*__VENDOR_3DMOL__*/", "/*__VENDOR_PLOTLY__*/"):
                    self.assertNotIn(marca, h)
                self.assertTrue(h.lstrip().lower().startswith("<!doctype html"))

    def test_seletor_de_unidade(self):
        for nome, h in self.html.items():
            with self.subTest(nome):
                for u, rot in (("kj", "kJ/mol"), ("kcal", "kcal/mol"), ("ev", "eV")):
                    self.assertIn(f'<button data-u="{u}">{rot}</button>', h)
                self.assertIn("function setUnit(", h)
                self.assertIn("localStorage", h)                         # a escolha da unidade fica salva

    def test_unidade_inicial_vem_da_configuracao(self):
        self.assertEqual(self.D["dimero"]["meta"]["unidade"], "kj")
        self.assertEqual(self.D["amostras"]["meta"]["unidade"], "ev")

    def test_modo_ampliar_zoom(self):
        for nome, h in self.html.items():
            with self.subTest(nome):
                self.assertIn('id="zoom"', h)
                self.assertIn("function abrirZoom(", h)
                self.assertIn("function fecharZoom(", h)
                self.assertIn("🔍 Ampliar", h)
                self.assertIn("🔍 Zoom", h)

    def test_recarga_automatica(self):
        for nome, h in self.html.items():
            with self.subTest(nome):
                self.assertIn("location.reload()", h)
                self.assertIn("D.meta.recarga_s", h)
        self.assertEqual(self.D["dimero"]["meta"]["recarga_s"], 300)       # painel.yaml do exemplo
        self.assertEqual(self.D["amostras"]["meta"]["recarga_s"], 0)       # amostra estática: sem recarga
        # a recarga é adiada com o modo Ampliar aberto ou uso recente
        self.assertRegex(self.html["dimero"], r"!zAberto\s*&&\s*Date\.now\(\)\s*-\s*ult\s*>=\s*OCIOSO")

    def test_secoes_dos_dados_embutidos(self):
        for nome, D in self.D.items():
            with self.subTest(nome):
                self.assertEqual(list(D.keys()), SECOES)

    def test_json_embutido_nao_fecha_script(self):
        for nome, h in self.html.items():
            i = h.index("const D = ")
            fim = h.index(";\n", i)
            self.assertNotIn("</", h[i:fim])

    def test_gerado_em_nao_altera_arquivos_do_repositorio(self):
        r = subprocess.run(["git", "status", "--porcelain", "--", "examples"], cwd=DIMERO.parent.parent, capture_output=True, text=True)
        if r.returncode == 0:
            self.assertEqual(r.stdout.strip(), "", r.stdout)


class TestDimeroBenzeno(_ExemplosGerados):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.D1 = cls.D["dimero"]
        cls.est = {e["id"]: e for e in cls.D1["est"]}

    def test_contagens_e_sem_avisos(self):
        D = self.D1
        self.assertEqual(len(D["est"]), 14)                              # 1 monômero + 9 dímeros UMA + 4 ORCA
        self.assertEqual(len(D["filmes"]), 12)
        self.assertEqual(len(D["fila"]), 4)
        self.assertEqual(D["avisos"], [])
        self.assertIn("14 estruturas, 12 filmes, 4 jobs na fila, 0 avisos", self.stdout["dimero"])

    def test_selos_nivel_e_programa(self):
        uma = "uma-s-1p2p1 (tarefa omol) · fairchem-core 2.22.0"
        orca = "B97-3c · ORCA 6.1.1"
        for i in ("benzeno_uma", "dimero_PD_p0", "dimero_S_p2", "dimero_T_p1"):
            self.assertEqual(self.est[i]["selo"], uma, i)
        for i in ("benzeno_dft", "dimero_dft", "sp_benzeno", "sp_dimero"):
            self.assertEqual(self.est[i]["selo"], orca, i)
        for j in self.D1["fila"]:
            self.assertEqual(j["selo"], orca)
        for f in self.D1["filmes"]:
            self.assertTrue(f["selo"] and "·" in f["selo"], f)
        # a página desenha o selo
        self.assertIn("seloHtml", self.html["dimero"])
        self.assertIn('class="selo', self.html["dimero"])

    def test_nada_inventado_nos_selos(self):
        for e in self.D1["est"]:
            self.assertNotIn("não registrado", e["selo"], e["id"])       # todos têm nível e versão no arquivo
        # sem nível no arquivo, o selo diz 'não registrado' (nunca presume um método)
        with tempfile.TemporaryDirectory() as d:
            import painel_lib.montar as M
            cfg = {"_dir": d, "estruturas": []}
            m = M.Montador(cfg)
            self.assertEqual(m.selo(L.novo("x")), "não registrado · programa não registrado")
            self.assertEqual(m.selo({"nivel": {}, "programa": "Foo", "versao": None}), "não registrado · Foo (versão não registrada)")

    def test_energias_vem_dos_arquivos(self):
        e = self.est["benzeno_dft"]["E"]
        self.assertAlmostEqual(e, energia_final_orca(ORCA_DIMERO / "benzeno" / "benzeno.out") * HA, places=6)
        self.assertAlmostEqual(self.est["dimero_dft"]["E"], energia_final_orca(ORCA_DIMERO / "dimero_PD" / "dimero_PD.out") * HA, places=6)
        self.assertEqual(self.est["dimero_dft"]["estado"], "concluido")
        self.assertGreaterEqual(self.est["dimero_PD_p0"]["n_quadros"], 2)
        self.assertEqual(len(self.est["dimero_dft"]["el"]), 24)
        self.assertEqual(self.est["dimero_dft"]["el"].count("C"), 12)

    def test_parcelas_de_energia_de_interacao(self):
        D = self.D1
        self.assertEqual(D["energia"]["variantes"], ["UMA", "B97-3c (geometria própria)", "B97-3c na geometria UMA"])
        p = {x["nome"]: x for x in D["energia"]["parcelas"]}
        pd = p["Energia de interação (PD)"]["ev"]
        eb = energia_final_orca(ORCA_DIMERO / "benzeno" / "benzeno.out")
        ed = energia_final_orca(ORCA_DIMERO / "dimero_PD" / "dimero_PD.out")
        self.assertAlmostEqual(pd["B97-3c (geometria própria)"], (ed - 2 * eb) * HA, places=6)
        sb = energia_final_orca(ORCA_DIMERO / "sp_na_geometria_uma" / "sp_benzeno.out")
        sd = energia_final_orca(ORCA_DIMERO / "sp_na_geometria_uma" / "sp_dimero_PD__p0.out")
        self.assertAlmostEqual(pd["B97-3c na geometria UMA"], (sd - 2 * sb) * HA, places=6)
        for v, x in pd.items():
            self.assertLess(x, 0, v)                                       # atração em todos os níveis
        # cada variante carrega o selo do seu nível: nunca se misturam níveis sem aviso
        selos = D["energia"]["selos"]
        self.assertEqual(selos["B97-3c (geometria própria)"], ["B97-3c · ORCA 6.1.1"])
        self.assertEqual(selos["UMA"], ["uma-s-1p2p1 (tarefa omol) · fairchem-core 2.22.0"])
        self.assertEqual(D["energia"]["avisos"], [])

    def test_ranking_dos_arranjos(self):
        r = self.D1["ranking"][0]
        self.assertEqual([i["rotulo"] for i in r["itens"]], ["PD", "T", "S"])        # PD mais estável, depois T, depois S
        self.assertEqual(r["itens"][0]["rel"], 0.0)
        self.assertTrue(all(i["n"] == 3 for i in r["itens"]))
        rel = [i["rel"] for i in r["itens"]]
        self.assertEqual(rel, sorted(rel))

    def test_frequencias_e_comparacao(self):
        f = self.D1["freq"]
        s = {x["id"]: x for x in f["sistemas"]}
        self.assertEqual(set(s), {"bz_uma", "bz_dft", "pd_uma", "pd_dft"})
        self.assertEqual((len(s["bz_uma"]["freqs"]), len(s["bz_dft"]["freqs"])), (36, 36))
        self.assertEqual((len(s["pd_uma"]["freqs"]), len(s["pd_dft"]["freqs"])), (72, 72))
        self.assertEqual(s["bz_uma"]["classe"], "MLIP")
        self.assertEqual(s["bz_dft"]["classe"], "QM")
        self.assertEqual(s["bz_uma"]["rotulo"], "EXPLORATÓRIO")

    def test_etapas(self):
        e = {x["id"]: x for x in self.D1["etapas"]}
        self.assertEqual(list(e), ["E1", "E2", "E3", "E4", "E5"])
        for x in e.values():
            self.assertEqual(x["estado"], "concluido", x["id"])
        self.assertEqual((e["E2"]["feito"], e["E2"]["total"]), (10, 10))

    def test_metodos_e_glossario(self):
        m = self.D1["metodos"]["cards"]
        titulos = [c["titulo"] for c in m]
        self.assertIn("fairchem-core 2.22.0", titulos)
        self.assertTrue(any("ORCA" in t for t in titulos))
        self.assertGreaterEqual(len(self.D1["glossario"]), 17)
        termos = [g[0] for g in self.D1["glossario"]]
        self.assertIn("B97-3c", termos)                                  # o glossário da configuração entra
        self.assertIn("DFT", termos)                                     # e o padrão também

    def test_pt_por_padrao(self):
        self.assertEqual(self.D1["meta"]["lang"], "pt")
        self.assertIn('<html lang="pt-BR">', self.html["dimero"])
        self.assertIn("Nível / método", str(self.D1["metodos"]))


class TestAmostras(_ExemplosGerados):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.D1 = cls.D["amostras"]

    def test_estruturas_com_selos(self):
        ids = {e["id"]: e for e in self.D1["est"]}
        esperado = {"si_vasp": "PBE DFT-D3(BJ) · VASP 6.4.2",
                    "agua_cp2k": "PBE DFT-D3 / DZVP-MOLOPT-SR-GTH · CP2K 2024.1",
                    "agua_g16": "B3LYP/6-31G(d) · Gaussian 16 (ES64L-G16RevC.01)",
                    "dimero_orca_run": "B97-3c · ORCA 6.1.1"}
        for i, selo in esperado.items():
            self.assertEqual(ids[i]["selo"], selo)
        if tem_ase():
            self.assertEqual(ids["si_qe"]["selo"], "PBE · Quantum ESPRESSO (pw.x) 7.2")
            self.assertEqual(len(ids), 5)
        else:
            self.assertNotIn("si_qe", ids)                                # sem ASE o pw.x não tem geometria: sai com aviso
            self.assertTrue(any("si_qe" in a for a in self.D1["avisos"]))

    def test_fila_estados(self):
        j = {x["nome"]: x for x in self.D1["fila"]}
        self.assertEqual(len(j), 6)
        self.assertEqual(j["SINTETICO_agua"]["estado"], "rodando")        # ativo_s enorme na configuração
        self.assertEqual(j["SINTETICO_falhou"]["estado"], "falhou")
        self.assertEqual(j["dimero_PD_em_andamento"]["estado"], "rodando")
        self.assertEqual(j["SINTETICO_remoto_sp"]["estado"], "rodando")
        self.assertEqual(j["SINTETICO_remoto_ok"]["estado"], "concluido")
        self.assertEqual(j["SINTETICO_remoto_fila"]["estado"], "pendente")
        self.assertIs(j["SINTETICO_falhou"]["scf_convergiu"], False)
        self.assertEqual(len(j["SINTETICO_falhou"]["scf"]), 50)
        self.assertIsNone(j["SINTETICO_falhou"]["energia_eV"])
        self.assertEqual(j["SINTETICO_falhou"]["criterio"]["valor"], 1e-6)

    def test_fila_viva_nao_inventa_nivel(self):
        for n in ("SINTETICO_remoto_sp", "SINTETICO_remoto_ok", "SINTETICO_remoto_fila"):
            j = next(x for x in self.D1["fila"] if x["nome"] == n)
            self.assertEqual(j["selo"], "not recorded · CP2K (version not recorded)")
        ok = next(x for x in self.D1["fila"] if x["nome"] == "SINTETICO_remoto_ok")
        self.assertAlmostEqual(ok["energia_eV"], -98.317312345 * HA, places=6)    # energia_Ha do JSON de acompanhamento
        self.assertEqual(ok["scf"][-1][3], 9e-7)
        self.assertEqual(self.D1["fila_meta"][0]["quando"], "2026-10-01 09:30:00")

    def test_aviso_da_falha_e_etapas(self):
        self.assertTrue(any("SINTETICO_falhou" in a and "SCF" in a for a in self.D1["avisos"]), self.D1["avisos"])
        e = {x["id"]: x["estado"] for x in self.D1["etapas"]}
        self.assertEqual(e["S4"], "falhou")
        self.assertEqual(e["S5"], "pendente")
        self.assertEqual(e["S3"], "rodando")
        if tem_ase():
            self.assertEqual(e["S1"], "concluido")

    def test_ingles(self):
        D = self.D1
        self.assertEqual(D["meta"]["lang"], "en")
        self.assertIn('<html lang="en">', self.html["amostras"])
        self.assertIn("<title>Reader test bench", self.html["amostras"])
        self.assertIn("Level / method", str(D["metodos"]))
        self.assertIn("Energy cutoff", str(D["metodos"]))
        self.assertNotIn("Nível / método", str(D["metodos"]))
        self.assertTrue(any(g[0] == "DFT" and g[1].startswith("Density functional theory") for g in D["glossario"]))
        self.assertEqual(D["energia"]["selos"]["toy model"], ["number typed in the configuration"])
        self.assertIn("1 eV = 96.485 kJ/mol", self.html["amostras"])      # tabela de conversão em inglês presente
        self.assertEqual(D["meta"]["titulo"], "Reader test bench: CP2K, VASP, Gaussian, Quantum ESPRESSO, ORCA")

    def test_numeros_digitados_marcados(self):
        d = self.D1["energia"]["digitados"]
        self.assertEqual(len(d), 4)
        self.assertTrue(all("illustrative" in x for x in d))


class TestIdiomaTrocado(_ComTmp):
    def test_dimero_em_ingles(self):
        cfg = self.config_derivada(DIMERO, lang="en")
        saida, _ = self.gerar(cfg)
        h = saida.read_text(encoding="utf-8")
        D = dados_do_html(h)
        self.assertIn('<html lang="en">', h)
        self.assertEqual(D["meta"]["lang"], "en")
        self.assertIn("Level / method", str(D["metodos"]))
        self.assertNotIn("Nível / método", str(D["metodos"]))
        self.assertIn("Density functional theory", str(D["glossario"]))
        # o selo de um arquivo com nível e versão continua o mesmo (vem do arquivo, não do idioma)
        self.assertTrue(any(e["selo"] == "B97-3c · ORCA 6.1.1" for e in D["est"]))
        # o glossário próprio da configuração (em português) é preservado
        self.assertTrue(any(g[0] == "B97-3c" for g in D["glossario"]))

    def test_idioma_desconhecido_cai_em_portugues_sem_quebrar(self):
        cfg = self.config_derivada(AMOSTRAS, lang="xx")
        saida, _ = self.gerar(cfg)
        self.assertIn("Nível / método", str(dados_do_html(saida)["metodos"]))


class TestArquivosAusentes(_ComTmp):
    def test_estrutura_frequencia_e_fila_ausentes_viram_aviso(self):
        cfg = {"titulo": "falta", "raiz": str(AMOSTRAS),
               "estruturas": [{"id": "existe", "arquivo": "gaussian/SINTETICO_agua.log"},
                              {"id": "nao_existe", "arquivo": "orca/nao_existe_mesmo.out"}],
               "frequencias": [{"id": "ff", "arquivo": "gaussian/nao_existe_freq.log"}],
               "fila": [{"saida": "cp2k/nada/*.out"}, {"saida": "orca/inexistente.out"}]}
        gravar_yaml(self.tmp / "painel.yaml", cfg)
        saida, r = self.gerar(self.tmp / "painel.yaml")
        D = dados_do_html(saida)
        self.assertEqual([e["id"] for e in D["est"]], ["existe"])
        self.assertTrue(any("nao_existe" in a and "não encontrado" in a for a in D["avisos"]), D["avisos"])
        self.assertTrue(any("nao_existe_freq.log" in a for a in D["avisos"]), D["avisos"])
        self.assertIn("aviso:", r.stdout)                                  # a CLI imprime os avisos

    def test_termo_de_energia_com_estrutura_inexistente(self):
        cfg = {"titulo": "e", "raiz": str(AMOSTRAS),
               "estruturas": [{"id": "a", "arquivo": "gaussian/SINTETICO_agua.log"}],
               "energia": {"termos": {"A": "a", "B": "nao_existe"},
                           "parcelas": [{"nome": "dif", "expr": "A - B"}]}}
        gravar_yaml(self.tmp / "painel.yaml", cfg)
        saida, _ = self.gerar(self.tmp / "painel.yaml")
        D = dados_do_html(saida)
        self.assertTrue(D["avisos"] or D["energia"]["avisos"], "esperava aviso sobre o termo B")

    def test_expressao_invalida_vira_aviso_e_nao_executa_codigo(self):
        marca = self.tmp / "executou.txt"
        cfg = {"titulo": "e", "raiz": str(AMOSTRAS),
               "estruturas": [{"id": "a", "arquivo": "gaussian/SINTETICO_agua.log"}],
               "energia": {"termos": {"A": "a"},
                           "parcelas": [{"nome": "injecao", "expr": f"A + __import__('pathlib').Path('{marca}').touch()"},
                                        {"nome": "zero", "expr": "A / 0"},
                                        {"nome": "sintaxe", "expr": "A +* 2"},
                                        {"nome": "potencia", "expr": "A ** 2"},
                                        {"nome": "boa", "expr": "A - A"}]}}
        gravar_yaml(self.tmp / "painel.yaml", cfg)
        saida, _ = self.gerar(self.tmp / "painel.yaml")
        D = dados_do_html(saida)
        self.assertFalse(marca.exists(), "a expressão foi executada!")
        p = {x["nome"]: x["ev"] for x in D["energia"]["parcelas"]}
        self.assertTrue(all(v is None for v in p["zero"].values()))
        self.assertTrue(all(v is None for v in p["sintaxe"].values()))
        self.assertTrue(all(v is None for v in p["potencia"].values()))
        self.assertTrue(any("A / 0" in a and "ZeroDivisionError" in a for a in D["avisos"]), D["avisos"])
        self.assertTrue(any("A +* 2" in a for a in D["avisos"]), D["avisos"])
        self.assertTrue(any("A ** 2" in a for a in D["avisos"]), D["avisos"])
        self.assertTrue(all(v == 0.0 for v in p["boa"].values()))

    def test_configuracao_inexistente_ou_invalida(self):
        r = cli("gerar", self.tmp / "nao.yaml")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("configuração não encontrada", r.stderr + r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        (self.tmp / "lista.yaml").write_text("- a\n- b\n")
        r = cli("gerar", self.tmp / "lista.yaml")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("dicionário", r.stderr + r.stdout)

    def test_config_vazia_gera_painel_minimo(self):
        (self.tmp / "vazia.yaml").write_text("titulo: só o título\n")
        saida, _ = self.gerar(self.tmp / "vazia.yaml")
        D = dados_do_html(saida)
        self.assertEqual(D["est"], [])
        self.assertEqual(D["meta"]["titulo"], "só o título")

    def test_titulo_hostil_e_escapado(self):
        (self.tmp / "h.yaml").write_text('titulo: "A </script><img src=x onerror=alert(1)> B"\n')
        saida, _ = self.gerar(self.tmp / "h.yaml")
        h = saida.read_text(encoding="utf-8")
        self.assertFalse([1 for t, a in analisar_html(h).tags if t == "img"], "o título injetou uma tag <img>")
        self.assertEqual(dados_do_html(h)["meta"]["titulo"], "A </script><img src=x onerror=alert(1)> B")

    def test_saida_sem_arquivo_temporario(self):
        cfg = self.config_derivada(AMOSTRAS)
        self.gerar(cfg)
        self.assertEqual([p.name for p in self.tmp.glob("*.tmp")], [])


class TestInit(_ComTmp):
    def test_init_copia_o_modelo_e_nao_sobrescreve(self):
        alvo = self.tmp / "novo.yaml"
        r = cli("init", "-o", alvo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("modelo copiado", r.stdout)
        self.assertEqual(alvo.read_text(encoding="utf-8"), (SKILL / "assets" / "painel_modelo.yaml").read_text(encoding="utf-8"))
        cfg = carregar_yaml(alvo)
        self.assertIsInstance(cfg, dict)
        self.assertIn("titulo", cfg)
        alvo.write_text("# editado pelo usuário\n")
        r = cli("init", "-o", alvo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("já existe", r.stdout + r.stderr)
        self.assertEqual(alvo.read_text(), "# editado pelo usuário\n")

    def test_init_padrao_escreve_no_diretorio_atual(self):
        r = cli("init", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tmp / "painel.yaml").exists())

    def test_modelo_gera_um_painel_vazio(self):
        """o modelo comentado, sem editar, ainda é uma configuração válida (as seções sem dado somem)."""
        cli("init", "-o", self.tmp / "m.yaml")
        r = cli("gerar", self.tmp / "m.yaml", "-o", self.tmp / "m.html")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(list(dados_do_html(self.tmp / "m.html").keys()), SECOES)


class TestDescobrir(_ComTmp):
    def test_descobrir_stdout(self):
        r = cli("descobrir", AMOSTRAS)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = r.stdout
        self.assertIn("estruturas:", s)
        for arq in ("cp2k/agua_geo/SINTETICO_agua.out", "gaussian/SINTETICO_agua.log", "orca/dimero_PD_em_andamento.out",
                    "vasp/si_relax/OUTCAR"):
            self.assertIn(f"arquivo: {arq}", s)
            self.assertIn(f"saida: {arq}", s)
        self.assertIn("frequencias:", s)                                   # só o Gaussian tem frequências
        self.assertIn("arquivo: gaussian/SINTETICO_agua.log", s.split("frequencias:")[1])
        self.assertIn("programa: ORCA 6.1.1 · 2 quadros", s)
        self.assertIn("programa: CP2K 2024.1 · 3 quadros", s)
        self.assertNotIn("falhou/SINTETICO_falhou.out", s)                 # sem geometria lida: o rascunho não o lista
        self.assertNotIn(".git", s)

    def test_ids_do_rascunho_sao_unicos(self):
        cfg = carregar_yaml_texto(cli("descobrir", AMOSTRAS).stdout)
        ids = [e["id"] for e in cfg["estruturas"]]
        self.assertEqual(len(ids), len(set(ids)), ids)
        self.assertIn("SINTETICO_agua", ids)
        self.assertIn("SINTETICO_agua_2", ids)                             # CP2K e Gaussian com o mesmo nome de arquivo

    def test_descobrir_escreve_arquivo_e_rascunho_gera_painel(self):
        pasta = self.tmp / "amostras"
        shutil.copytree(AMOSTRAS, pasta, ignore=shutil.ignore_patterns("painel.html", "__pycache__"))
        r = cli("descobrir", pasta, "-o", pasta / "rascunho.yaml")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("rascunho em", r.stdout)
        cfg = carregar_yaml(pasta / "rascunho.yaml")
        self.assertEqual(cfg["lang"], "pt")
        self.assertGreaterEqual(len(cfg["estruturas"]), 4)
        r = cli("gerar", pasta / "rascunho.yaml", "-o", self.tmp / "r.html")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        D = dados_do_html(self.tmp / "r.html")
        self.assertGreaterEqual(len(D["est"]), 4)
        self.assertEqual(len({e["id"] for e in D["est"]}), len(D["est"]))
        self.assertEqual(len(D["fila"]), len(cfg["fila"]))

    def test_descobrir_em_pasta_vazia(self):
        r = cli("descobrir", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("estruturas:\n  -", r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_descobrir_ignora_pastas_ocultas_e_lixo(self):
        (self.tmp / ".oculta").mkdir()
        shutil.copy(AMOSTRAS / "gaussian" / "SINTETICO_agua.log", self.tmp / ".oculta" / "a.log")
        (self.tmp / "quebrado.out").write_bytes(b"\x00\xff\xfe lixo")
        r = cli("descobrir", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(".oculta", r.stdout)
        self.assertNotIn("quebrado.out", r.stdout)


def carregar_yaml_texto(t):
    import yaml
    return yaml.safe_load(t)


@unittest.skipUnless(tem_yaml(), "PyYAML não instalado")
class TestVigiar(_ComTmp):
    def test_vigiar_regenera_periodicamente(self):
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        cfg = self.config_derivada(AMOSTRAS)
        alvo = self.tmp / "v.html"
        p = subprocess.Popen([sys.executable, "-u", str(PAINEL_PY), "gerar", str(cfg), "-o", str(alvo), "--vigiar", "1"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
        try:
            t0 = time.time()
            while time.time() - t0 < 30 and (not alvo.exists()):
                time.sleep(0.2)
            self.assertTrue(alvo.exists(), "o --vigiar não gerou o HTML")
            m1 = alvo.stat().st_mtime_ns
            t0 = time.time()
            while time.time() - t0 < 20 and alvo.stat().st_mtime_ns == m1:
                time.sleep(0.2)
            self.assertNotEqual(alvo.stat().st_mtime_ns, m1, "o HTML não foi regenerado")
        finally:
            p.terminate()
            try:
                out, err = p.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                out, err = p.communicate()
        self.assertIn("vigiando: regenera a cada 1 s", out)
        self.assertGreaterEqual(out.count("estruturas,"), 2)
        self.assertNotIn("Traceback", err)
        self.assertEqual(list(self.tmp.glob("*.tmp")), [])
        dados_do_html(alvo)                                                 # arquivo íntegro (troca atômica)


if __name__ == "__main__":
    unittest.main()
