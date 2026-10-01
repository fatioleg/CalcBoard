#!/usr/bin/env python3
"""painel.py — painel HTML interativo e didático de cálculos de estrutura eletrônica / simulação atomística.

Uso
  python painel.py gerar painel.yaml [-o painel.html]      gera o HTML (padrão: ao lado da configuração)
  python painel.py gerar painel.yaml --vigiar 120           regenera a cada 120 s (acompanhar cálculos ao vivo)
  python painel.py descobrir PASTA [-o painel.yaml]         procura saídas reconhecíveis e escreve um rascunho de configuração
  python painel.py ler ARQUIVO [ARQUIVO...]                  mostra o que os leitores extraem de cada arquivo (diagnóstico)
  python painel.py init [-o painel.yaml]                     copia o modelo comentado de configuração

Somente leitura: o painel nunca altera resultados. Dependências: Python ≥ 3.9, numpy, ase; PyYAML para .yaml.
O HTML é um arquivo único e offline: 3Dmol.js e plotly.js vêm embutidos de assets/vendor/.
"""
import argparse
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SKILL = AQUI.parent
sys.path.insert(0, str(AQUI))

from painel_lib import leitores as L  # noqa: E402
from painel_lib.montar import Montador, carregar_config  # noqa: E402

VENDOR = SKILL / "assets" / "vendor"
TEMPLATE = SKILL / "assets" / "painel_template.html"
URLS = {"3Dmol-min.js": ["https://cdnjs.cloudflare.com/ajax/libs/3Dmol/2.4.0/3Dmol-min.js", "https://3Dmol.org/build/3Dmol-min.js"],
        "plotly.min.js": ["https://cdn.plot.ly/plotly-2.35.2.min.js"]}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def vendor(nome):
    """biblioteca JS embutida: assets/vendor/ (baixada uma vez); plotly também pode vir do pacote Python."""
    alvo = VENDOR / nome
    if alvo.exists() and alvo.stat().st_size > 100_000:
        return alvo.read_text(encoding="utf-8")
    if nome == "plotly.min.js":
        try:
            import plotly
            p = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
            if p.exists():
                VENDOR.mkdir(parents=True, exist_ok=True)
                shutil.copy(p, alvo)
                return alvo.read_text(encoding="utf-8")
        except ImportError:
            pass
    for url in URLS[nome]:
        try:
            dados = urllib.request.urlopen(url, timeout=60).read()
            if len(dados) > 100_000:
                VENDOR.mkdir(parents=True, exist_ok=True)
                alvo.write_bytes(dados)
                return dados.decode("utf-8")
        except Exception:
            continue
    raise SystemExit(f"não encontrei {nome} em {VENDOR} nem consegui baixá-lo")


def renderizar(D):
    html = TEMPLATE.read_text(encoding="utf-8")
    seg = lambda s: s.replace("</script", "<\\/script")  # noqa: E731
    dados = json.dumps(D, ensure_ascii=False, separators=(",", ":"), default=_json_padrao).replace("</", "<\\/")
    titulo = (D["meta"]["titulo"] or "").replace("<", "&lt;")
    return (html.replace("/*__VENDOR_3DMOL__*/", seg(vendor("3Dmol-min.js")))
                .replace("/*__VENDOR_PLOTLY__*/", seg(vendor("plotly.min.js")))
                .replace("__LANG__", "pt-BR" if D["meta"]["lang"] == "pt" else "en")
                .replace("__TITULO__", titulo)
                .replace("__DADOS__", dados))


def _json_padrao(o):
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    return str(o)


def gerar(cfg_path, saida=None, quieto=False):
    t0 = time.time()
    cfg = carregar_config(cfg_path)
    D = Montador(cfg).montar()
    saida = Path(saida) if saida else Path(cfg["_dir"]) / (cfg.get("saida") or "painel.html")
    saida.parent.mkdir(parents=True, exist_ok=True)
    tmp = saida.with_suffix(saida.suffix + ".tmp")
    tmp.write_text(renderizar(D), encoding="utf-8")
    tmp.replace(saida)                                 # troca atômica: quem estiver lendo nunca vê arquivo pela metade
    if not quieto:
        mb = saida.stat().st_size / 1e6
        print(f"{saida}  ({mb:.1f} MB; {len(D['est'])} estruturas, {len(D['filmes'])} filmes, "
              f"{len(D['fila'])} jobs na fila, {len(D['avisos'])} avisos; {time.time() - t0:.1f} s)")
        for a in D["avisos"]:
            print("  aviso:", a)
        if mb > 25:
            print("  AVISO: HTML maior que 25 MB (reduza estruturas, filmes ou modos de vibração)")
    return saida, D


def cmd_gerar(a):
    if not a.vigiar:
        gerar(a.config, a.saida)
        return
    print(f"vigiando: regenera a cada {a.vigiar} s (Ctrl+C para parar)")
    try:
        while True:
            try:
                gerar(a.config, a.saida, quieto=False)
            except Exception as e:  # noqa: BLE001
                print("falha ao gerar:", e)
            time.sleep(a.vigiar)
    except KeyboardInterrupt:
        pass


def cmd_ler(a):
    for f in a.arquivos:
        R = L.ler(f, a.formato)
        q = R["quadros"]
        print(f"== {f}")
        print(f"   detectado: {L.detectar(f) if Path(f).exists() else '—'} · programa {R['programa']} {R['versao']} · estado {L.estado_final(R)}")
        print(f"   nível: {R['nivel']}")
        print(f"   tipo {R['tipo']} · energia {R['energia_eV']} eV · {len(q)} quadros" + (f" ({len(q[-1]['simbolos'])} átomos)" if q else ""))
        if R["scf"]:
            print(f"   SCF: {len(R['scf'])} iterações no último ciclo ({R['n_ciclos_scf']} ciclos) · critério {R['scf_criterio']}")
        if R["freq"]:
            fr = R["freq"]["freqs_cm1"]
            print(f"   frequências: {len(fr)} ({R['freq']['n_imag']} imaginárias) · modos {'sim' if R['freq']['modos'] else 'não'} · ZPE {R['freq']['zpe_kJmol']} kJ/mol")
        if R["duracao_s"]:
            print(f"   duração: {R['duracao_s']:.0f} s")
        for x in R["extra"].get("notas", []):
            print("   nota:", x)
        for x in R["avisos"]:
            print("   aviso:", x)


PADROES = ["**/*.out", "**/*.log", "**/OUTCAR", "**/vasprun.xml", "**/*.extxyz", "**/*.traj", "**/*_trj.xyz", "**/*-pos-*.xyz",
           "**/*.hess", "**/*-VIBRATIONS-*.mol", "**/*.cif", "**/CONTCAR", "**/*.jsonl", "**/*freq*.json"]


def cmd_descobrir(a):
    raiz = Path(a.pasta).resolve()
    achados = {}
    for pad in PADROES:
        for p in raiz.glob(pad):
            if p.is_file() and not any(x.startswith(".") for x in p.relative_to(raiz).parts) and p.stat().st_size < 2e9:
                achados[p] = None
    linhas = ["# Rascunho gerado por `painel.py descobrir` — REVISE: escolha estruturas, papéis, energias e etapas.",
              f"titulo: \"Painel dos cálculos — {raiz.name}\"", "lang: pt", "unidade: kJ/mol", "recarga_s: 120", "",
              "estruturas:"]
    freq, fila, ids_usados = [], [], set()
    for p in sorted(achados):
        tipo = L.detectar(p)
        r = p.relative_to(raiz)
        if tipo in ("orca", "cp2k", "gaussian", "qe", "vasp_outcar", "vasprun", "ase") and p.suffix not in (".jsonl",):
            R = L.ler(p)
            if R["estado"] in ("ilegivel",) or not R["quadros"]:
                continue
            nome = p.stem if p.stem not in ("OUTCAR", "vasprun", "CONTCAR") else p.parent.name
            base_nome, k = nome, 1
            while nome in ids_usados:                  # ids precisam ser únicos na configuração (dois programas podem compartilhar o nome)
                k += 1
                nome = f"{base_nome}_{k}"
            ids_usados.add(nome)
            linhas += [f"  - id: {nome}", f"    arquivo: {r}", f"    # programa: {R['programa']} {R['versao'] or ''} · {len(R['quadros'])} quadros · estado {L.estado_final(R)}"]
            if R["freq"]:
                freq.append(r)
            if tipo in ("orca", "cp2k", "gaussian", "qe", "vasp_outcar"):
                fila.append(r)
        elif tipo in ("orca_hess", "cp2k_molden") or (tipo == "json" and "freq" in p.name):
            freq.append(r)
    if freq:
        linhas += ["", "frequencias:"] + [f"  - arquivo: {x}" for x in freq]
    if fila:
        linhas += ["", "fila:"] + [f"  - saida: {x}" for x in fila]
    linhas += ["", "# Próximos passos: veja references/formato-config.md (reacao, energia, ranking, medidas, etapas, glossario)."]
    txt = "\n".join(linhas) + "\n"
    if a.saida:
        Path(a.saida).write_text(txt, encoding="utf-8")
        print(f"rascunho em {a.saida} ({len(achados)} arquivos examinados)")
    else:
        print(txt)


def cmd_init(a):
    alvo = Path(a.saida or "painel.yaml")
    if alvo.exists():
        raise SystemExit(f"{alvo} já existe; não sobrescrevo")
    shutil.copy(SKILL / "assets" / "painel_modelo.yaml", alvo)
    print(f"modelo copiado para {alvo}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Painel HTML de cálculos atomísticos (somente leitura).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gerar", help="gera o HTML a partir da configuração")
    g.add_argument("config")
    g.add_argument("-o", "--saida", default=None)
    g.add_argument("--vigiar", type=int, default=0, metavar="N", help="regenera a cada N segundos")
    g.set_defaults(f=cmd_gerar)
    d = sub.add_parser("descobrir", help="rascunho de configuração a partir das saídas encontradas")
    d.add_argument("pasta")
    d.add_argument("-o", "--saida", default=None)
    d.set_defaults(f=cmd_descobrir)
    r = sub.add_parser("ler", help="diagnóstico: o que os leitores extraem")
    r.add_argument("arquivos", nargs="+")
    r.add_argument("--formato", default=None)
    r.set_defaults(f=cmd_ler)
    i = sub.add_parser("init", help="copia o modelo comentado de painel.yaml")
    i.add_argument("-o", "--saida", default=None)
    i.set_defaults(f=cmd_init)
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
