"""Utilidades compartilhadas pelos testes (caminhos, execução da CLI, leitura dos dados embutidos no HTML)."""
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILL = RAIZ / "painel-calculos"
SCRIPTS = SKILL / "scripts"
PAINEL_PY = SCRIPTS / "painel.py"
CAPTURA_PY = SCRIPTS / "captura.py"
SMOKE_JS = Path(__file__).resolve().parent / "smoke_painel.js"
AMOSTRAS = RAIZ / "examples" / "amostras"
DIMERO = RAIZ / "examples" / "dimero_benzeno"
ORCA_DIMERO = DIMERO / "calc" / "orca"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from painel_lib import leitores as L  # noqa: E402


def tem_ase():
    try:
        import ase  # noqa: F401
        return True
    except ImportError:
        return False


def tem_yaml():
    try:
        import yaml  # noqa: F401
        return True
    except ImportError:
        return False


def cli(*args, cwd=None, timeout=300, env=None):
    """roda `painel.py ARGS` como processo separado (testa a CLI de verdade). Devolve CompletedProcess com texto UTF-8."""
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    e.update(env or {})
    return subprocess.run([sys.executable, str(PAINEL_PY), *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=cwd, timeout=timeout, env=e)


def dados_do_html(html):
    """o objeto `const D = {...};` embutido na página, como dict."""
    if isinstance(html, Path):
        html = html.read_text(encoding="utf-8")
    i = html.index("const D = ") + len("const D = ")
    D, _ = json.JSONDecoder().raw_decode(html[i:])
    return D


class _Tags(HTMLParser):
    """coleta as tags de abertura (o conteúdo de <script> é tratado como texto, então JS embutido não gera tags falsas)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []          # (tag, dict de atributos)
        self.scripts = []       # texto dos <script> sem src
        self._em_script = None

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "script" and "src" not in dict(attrs):
            self._em_script = []

    def handle_data(self, data):
        if self._em_script is not None:
            self._em_script.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._em_script is not None:
            self.scripts.append("".join(self._em_script))
            self._em_script = None


def analisar_html(html):
    if isinstance(html, Path):
        html = html.read_text(encoding="utf-8")
    p = _Tags()
    p.feed(html)
    p.close()
    return p


def energia_final_orca(caminho):
    """último 'FINAL SINGLE POINT ENERGY' do .out (Eh), lido direto do texto."""
    v = re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", Path(caminho).read_text(encoding="utf-8", errors="replace"))
    return float(v[-1])
