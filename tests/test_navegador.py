"""Navegador headless (Playwright + Chromium): o painel gerado carrega sem erros de JavaScript e passa no smoke test interativo.

Sem Playwright instalado nada disto roda (skip explícito). Para rodar: `pip install playwright pytest && playwright install chromium`.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _comum import AMOSTRAS, CAPTURA_PY, DIMERO, SMOKE_JS, cli, tem_yaml


def tem_playwright():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def captura(*args, timeout=240):
    r = subprocess.run([sys.executable, str(CAPTURA_PY), *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return r


def resultado_avaliar(stdout):
    m = re.search(r"^avaliar:\s*(.*)$", stdout, re.M)
    if not m:
        raise AssertionError("captura.py não imprimiu 'avaliar: ...':\n" + stdout)
    return json.loads(m.group(1))


@unittest.skipUnless(tem_playwright() and tem_yaml(),
                     "Playwright (ou PyYAML) não está instalado neste Python: teste de navegador ignorado "
                     "(use um ambiente com `pip install playwright pyyaml` e `playwright install chromium`)")
class TestNavegador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._t.name)
        cls.html = {}
        for nome, ex in (("dimero", DIMERO), ("amostras", AMOSTRAS)):
            alvo = cls.tmp / f"{nome}.html"
            r = cli("gerar", ex / "painel.yaml", "-o", alvo)
            assert r.returncode == 0, r.stdout + r.stderr
            cls.html[nome] = alvo

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def test_smoke_interativo_do_dimero(self):
        js = SMOKE_JS.read_text(encoding="utf-8")
        passos = re.findall(r"passo\('(\w+)'", js)
        self.assertGreaterEqual(len(passos), 20)
        r = captura(self.html["dimero"], "-o", self.tmp / "d.png", "--avaliar", js)
        self.assertEqual(r.returncode, 0, f"exit {r.returncode}\n{r.stdout}\n{r.stderr}")
        res = resultado_avaliar(r.stdout)
        # cada passo termina em ':ok' (e na ordem do script); qualquer ':ERRO ...' ou erro de página fica fora desta lista
        self.assertEqual(res, [f"{p}:ok" for p in passos], res)
        self.assertTrue(all(x.endswith(":ok") for x in res))
        self.assertIn("0 erro(s) de JavaScript", r.stdout)
        png = self.tmp / "d.png"
        self.assertTrue(png.exists() and png.stat().st_size > 20_000, "captura de tela vazia")
        self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_amostras_carrega_sem_erros(self):
        r = captura(self.html["amostras"], "-o", self.tmp / "a.png")
        self.assertEqual(r.returncode, 0, f"exit {r.returncode}\n{r.stdout}\n{r.stderr}")
        self.assertIn("0 erro(s) de JavaScript", r.stdout)

    def test_unidade_e_dados_pelo_navegador(self):
        """as três unidades trocam de verdade e a página enxerga os dados embutidos."""
        expr = ("(() => { const o = {}; ['kcal','ev','kj'].forEach(u => { setUnit(u); o[u] = un(); });"
                " o.n_est = D.est.length; o.lang = document.documentElement.lang; return o; })()")
        r = captura(self.html["dimero"], "-o", self.tmp / "u.png", "--avaliar", expr)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(resultado_avaliar(r.stdout), {"kcal": "kcal/mol", "ev": "eV", "kj": "kJ/mol", "n_est": 14, "lang": "pt-BR"})

    def test_abrir_direto_no_modo_ampliar_pelo_hash(self):
        r = captura(self.html["dimero"], "-o", self.tmp / "z.png", "--hash", "#zoom=dimero_T_p0",
                    "--avaliar", "!document.getElementById('zoom').hidden")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIs(resultado_avaliar(r.stdout), True)

    def test_painel_em_ingles_no_navegador(self):
        r = captura(self.html["amostras"], "-o", self.tmp / "en.png", "--avaliar", "document.documentElement.lang")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(resultado_avaliar(r.stdout), "en")

    def test_erro_de_javascript_da_pagina_e_relatado_com_codigo_2(self):
        """o contrato de saída da captura: erro de JS na página => código 2 e o erro listado."""
        ruim = self.tmp / "ruim.html"
        ruim.write_text("<!doctype html><html><body><script>window.__erros=window.__erros||[];"
                        "window.addEventListener('error',e=>window.__erros.push(e.message));"
                        "throw new Error('erro-proposital-do-teste');</script></body></html>", encoding="utf-8")
        r = captura(ruim, "-o", self.tmp / "ruim.png")
        self.assertEqual(r.returncode, 2, f"{r.stdout}\n{r.stderr}")
        self.assertIn("erro-proposital-do-teste", r.stdout)


if __name__ == "__main__":
    unittest.main()
