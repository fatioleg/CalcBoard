"""Robustez: arquivo vazio, binário, lixo ou truncado nunca levanta exceção; vira estado 'ilegivel' + aviso
(ou um estado de execução honesto, nunca 'concluido' inventado) e o painel continua sendo gerado."""
import os
import tempfile
import unittest
from pathlib import Path

from _comum import AMOSTRAS, DIMERO, ORCA_DIMERO, cli, dados_do_html, tem_yaml, L

UMA = DIMERO / "calc" / "uma"
ESTADOS_OK = {"ilegivel", "rodando?", "falhou", "desconhecido", "ausente"}     # tudo, menos 'concluido' inventado

# arquivo real (completo) -> nome sob o qual a cópia truncada é gravada (o nome decide o leitor)
REAIS = {
    "orca": (ORCA_DIMERO / "dimero_PD" / "dimero_PD.out", "x.out"),
    "orca_amostra": (AMOSTRAS / "orca" / "dimero_PD_em_andamento.out", "x.out"),
    "cp2k": (AMOSTRAS / "cp2k" / "agua_geo" / "SINTETICO_agua.out", "x.out"),
    "gaussian": (AMOSTRAS / "gaussian" / "SINTETICO_agua.log", "x.log"),
    "qe": (AMOSTRAS / "qe" / "SINTETICO_si_relax.out", "x.out"),
    "vasp": (AMOSTRAS / "vasp" / "si_relax" / "OUTCAR", "OUTCAR"),
    "oszicar": (AMOSTRAS / "vasp" / "si_relax" / "OSZICAR", "OSZICAR"),
    "hess": (ORCA_DIMERO / "benzeno" / "benzeno.hess", "x.hess"),
    "trj": (ORCA_DIMERO / "benzeno" / "benzeno_trj.xyz", "x_trj.xyz"),
    "extxyz": (UMA / "estruturas" / "benzeno.extxyz", "x.extxyz"),
    "freq_json": (UMA / "freq" / "benzeno.json", "x.json"),
    "jsonl": (UMA / "progresso" / "benzeno.jsonl", "x.jsonl"),
}


def lixo_binario(n=4096, semente=7):
    import random
    r = random.Random(semente)
    return bytes(r.randrange(256) for _ in range(n))


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def escrever(self, nome, dados):
        p = self.dir / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(dados if isinstance(dados, bytes) else dados.encode("utf-8"))
        return p

    def ler_sem_excecao(self, p, **kw):
        try:
            R = L.ler(p, **kw)
        except BaseException as e:  # noqa: BLE001
            self.fail(f"L.ler({Path(p).name}) levantou {type(e).__name__}: {e}")
        self.assertIsInstance(R, dict)
        self.assertEqual(set(L.novo(p).keys()) - set(R.keys()), set())     # mesma estrutura de sempre
        return R

    def checar_ilegivel(self, R, rotulo=""):
        self.assertEqual(R["estado"], "ilegivel", f"{rotulo}: {R['estado']} / {R['avisos']}")
        self.assertTrue(R["avisos"], f"{rotulo}: 'ilegivel' sem aviso")
        self.assertIsNone(R["energia_eV"], rotulo)
        self.assertEqual(R["quadros"], [], rotulo)
        self.assertEqual(L.estado_final(R), "ilegivel")


class TestArquivosDegenerados(_Base):
    NOMES = ["x.out", "x.log", "x.txt", "OUTCAR", "OSZICAR", "vasprun.xml", "x.json", "x.hess", "x_trj.xyz", "x-pos-1.xyz",
             "x.xyz", "x.extxyz", "x.traj", "x.cif", "CONTCAR", "x-VIBRATIONS-1.mol"]

    def test_arquivo_vazio(self):
        for nome in self.NOMES:
            with self.subTest(nome):
                R = self.ler_sem_excecao(self.escrever(nome, b""))
                if nome.endswith((".out", ".log", ".txt", ".xyz")) or nome in ("OUTCAR", "OSZICAR"):
                    # vazio: 'ilegivel', ou um estado honesto sem dados (um .xyz de trajetória recém-criado ainda não tem quadros)
                    self.assertIn(R["estado"], ESTADOS_OK)
                    self.assertIsNone(R["energia_eV"])
                    self.assertEqual(R["quadros"], [])
                else:
                    self.checar_ilegivel(R, nome)

    def test_binario_aleatorio(self):
        for nome in self.NOMES:
            with self.subTest(nome):
                R = self.ler_sem_excecao(self.escrever(nome, lixo_binario()))
                self.assertIn(R["estado"], ESTADOS_OK)
                self.assertNotEqual(R["estado"], "concluido")
                self.assertIsNone(R["energia_eV"])
                self.assertEqual(R["quadros"], [])
                if R["estado"] == "ilegivel":
                    self.assertTrue(R["avisos"])

    def test_texto_sem_sentido(self):
        lixo = "isto não é uma saída de programa nenhum\n1 2 3\n\x00\x00\xff\n" * 20
        for nome in self.NOMES:
            with self.subTest(nome):
                R = self.ler_sem_excecao(self.escrever(nome, lixo))
                self.assertNotEqual(R["estado"], "concluido")
                self.assertIsNone(R["energia_eV"])
                if R["estado"] == "ilegivel":
                    self.assertTrue(R["avisos"])

    def test_formato_forcado_errado(self):
        p = self.escrever("x.out", (ORCA_DIMERO / "benzeno" / "benzeno.out").read_bytes())
        for formato in ("cp2k", "vasp_outcar", "qe", "gaussian", "json", "orca_hess", "formato_inexistente"):
            with self.subTest(formato):
                R = self.ler_sem_excecao(p, formato=formato)
                self.assertNotEqual(R["estado"], "concluido")        # nenhum leitor errado "conclui" um arquivo alheio
                if R["estado"] == "ilegivel":
                    self.assertTrue(R["avisos"])

    def test_json_invalido_e_tipos_estranhos(self):
        for nome, conteudo in (("a.json", "{nao e json"), ("b.json", "[1, 2, 3]"), ("c.json", '{"freqs_cm1": "texto"}'),
                               ("d.json", '{"freqs_cm1": [1, 2], "modos": 5}'), ("e.json", "null"),
                               ("f.json", '{"energia_eV": "abc"}')):
            with self.subTest(nome):
                R = self.ler_sem_excecao(self.escrever(nome, conteudo))
                self.assertIn(R["estado"], ESTADOS_OK | {"concluido"})        # f.json: energia ilegível mas estrutura válida
                if R["estado"] == "ilegivel":
                    self.assertTrue(R["avisos"])

    def test_diretorio_no_lugar_de_arquivo(self):
        d = self.dir / "pasta.out"
        d.mkdir()
        R = self.ler_sem_excecao(d)
        self.assertIn(R["estado"], ESTADOS_OK)
        self.assertTrue(R["avisos"])

    def test_sem_permissao_de_leitura(self):
        if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            self.skipTest("permissões de arquivo não restringem esta conta (Windows ou root)")
        p = self.escrever("sem_permissao.out", "x")
        p.chmod(0)
        self.addCleanup(lambda: p.chmod(0o644))
        R = self.ler_sem_excecao(p)
        self.checar_ilegivel(R, "sem permissão")


class TestArquivosTruncados(_Base):
    """cada saída real cortada em vários pontos (inclusive no meio de uma linha): sem exceção e nunca 'concluido'."""

    FRACOES = (0.02, 0.1, 0.3, 0.5, 0.7, 0.9, 0.97)

    def test_truncamentos(self):
        for chave, (origem, nome) in REAIS.items():
            dados = origem.read_bytes()
            for f in self.FRACOES:
                with self.subTest(f"{chave}@{f}"):
                    p = self.escrever(f"{chave}_{f}/{nome}", dados[:max(1, int(len(dados) * f))])
                    R = self.ler_sem_excecao(p)
                    self.assertIn(R["estado"], ESTADOS_OK | {"concluido"} if chave in ("hess", "freq_json", "extxyz", "jsonl", "trj") else ESTADOS_OK,
                                  f"{R['estado']} {R['avisos']}")
                    if R["estado"] == "ilegivel":
                        self.assertTrue(R["avisos"])

    def test_saida_de_programa_cortada_nunca_conclui(self):
        """sem a linha final de término normal, o estado nunca é 'concluido' (ORCA, CP2K, Gaussian, QE, VASP)."""
        for chave in ("orca", "cp2k", "gaussian", "qe", "vasp"):
            origem, nome = REAIS[chave]
            dados = origem.read_bytes()
            for f in (0.3, 0.6, 0.9):
                with self.subTest(f"{chave}@{f}"):
                    R = self.ler_sem_excecao(self.escrever(f"{chave}_{f}/{nome}", dados[:int(len(dados) * f)]))
                    self.assertNotEqual(L.estado_final(R), "concluido")

    def test_truncado_nao_inventa_nivel_nem_energia_que_nao_leu(self):
        origem, nome = REAIS["orca"]
        cab = origem.read_text(encoding="utf-8").split("Program Version", 1)[0]       # só o banner: sem versão, sem ! linha
        R = self.ler_sem_excecao(self.escrever("cab/x.out", cab))
        self.assertIsNone(R["versao"])
        self.assertIsNone(R["energia_eV"])
        self.assertEqual(R["nivel"], {})
        self.assertEqual(R["quadros"], [])


@unittest.skipUnless(tem_yaml(), "PyYAML não instalado")
class TestGeracaoComArquivosRuins(_Base):
    """o painel inteiro tem de sair mesmo que alguns arquivos referenciados estejam quebrados."""

    def test_painel_sai_com_arquivos_quebrados(self):
        import yaml
        self.escrever("vazio.out", b"")
        self.escrever("lixo.out", lixo_binario())
        self.escrever("cortado.out", (AMOSTRAS / "cp2k" / "agua_geo" / "SINTETICO_agua.out").read_bytes()[:3000])
        self.escrever("ruim.json", "{ruim")
        self.escrever("bom.xyz", "3\nagua\nO 0 0 0.117\nH 0 0.757 -0.469\nH 0 -0.757 -0.469\n")
        cfg = {"titulo": "robustez", "estruturas": [
                   {"id": "vazio", "arquivo": "vazio.out"}, {"id": "lixo", "arquivo": "lixo.out"},
                   {"id": "cortado", "arquivo": "cortado.out"}, {"id": "ruim", "arquivo": "ruim.json"},
                   {"id": "bom", "arquivo": "bom.xyz"}],
               "frequencias": [{"id": "f", "arquivo": "ruim.json"}],
               "fila": [{"saida": "*.out"}]}
        (self.dir / "painel.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
        r = cli("gerar", self.dir / "painel.yaml", "-o", self.dir / "saida.html")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        D = dados_do_html(self.dir / "saida.html")
        ids = [e["id"] for e in D["est"]]
        self.assertIn("bom", ids)                                          # a estrutura válida continua no painel
        self.assertTrue(D["avisos"], "arquivos ilegíveis deveriam gerar avisos")
        for nome in ("vazio", "lixo", "ruim"):
            self.assertTrue(any(nome in a for a in D["avisos"]), (nome, D["avisos"]))
        # cada job da fila tem estado explícito; os quebrados não aparecem como 'concluido'
        for j in D["fila"]:
            if j["nome"] in ("vazio", "lixo"):
                self.assertNotEqual(j["estado"], "concluido")


if __name__ == "__main__":
    unittest.main()
