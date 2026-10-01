"""Monta o dicionário de dados do painel (D) a partir de um painel.yaml / painel.json.

Princípios: só lê (nunca escreve nos resultados); um arquivo que falha vira aviso; nenhum número é inventado
(o que o arquivo não registra aparece como "não registrado"); números digitados na configuração são marcados.
"""
import glob
import json
import math
import os
import re
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from . import geometria as G
from . import leitores as L
from .analise import (agregar_grupos, avaliar, calc_expr, concentracao, energia_relativa, erro_forcas, erro_tensao, faixa,
                      limiares_condicao, nomes_expr)
from .textos import GLOSSARIO, TXT, traduzir

EV_KJ = 96.48533212
UNID_EV = {"ev": 1.0, "ha": L.HA_EV, "hartree": L.HA_EV, "eh": L.HA_EV, "ry": L.RY_EV, "kj/mol": 1 / EV_KJ,
           "kcal/mol": 4.184 / EV_KJ, "mev": 1e-3}
PALETA = ["#6c8ebf", "#ff7f0e", "#9aa0a6", "#2ca02c", "#9467bd", "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#d62728"]
FILM_MAX_QUADROS = 60
FILM_ORCAMENTO_B = 12_000_000
FREQ_ORCAMENTO_B = 6_000_000


# ----------------------------------------------------------------------------------------------------------
# configuração
# ----------------------------------------------------------------------------------------------------------
def carregar_config(caminho):
    p = Path(caminho)
    if not p.is_file():
        raise SystemExit(f"configuração não encontrada: {p}")
    txt = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:
            raise SystemExit("PyYAML não está instalado: use painel.json (mesmas chaves) ou `pip install pyyaml`") from e
        cfg = yaml.safe_load(txt) or {}
    else:
        cfg = json.loads(txt)
    if not isinstance(cfg, dict):
        raise SystemExit(f"{p}: a configuração precisa ser um dicionário")
    cfg["_dir"] = str(p.resolve().parent)
    return cfg


class Leitura:
    """cache de leituras por (caminho, mtime, tamanho): o modo --vigiar relê só o que mudou."""

    def __init__(self):
        self.cache = {}

    def ler(self, p, formato=None):
        p = Path(p)
        try:
            st = p.stat()
            k = (str(p), st.st_mtime, st.st_size, formato)
        except OSError:
            k = (str(p), None, None, formato)
        if k not in self.cache:
            self.cache[k] = L.ler(p, formato)
        return self.cache[k]


LEITURA = Leitura()


class Montador:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lang = (cfg.get("lang") or "pt").lower()[:2]
        self.T = TXT[self.lang if self.lang in TXT else "pt"]
        self.base = Path(cfg["_dir"]) / cfg.get("raiz", ".")
        self.avisos = []
        self.usados = []            # (rotulo, Resultado, declarado) para a seção de métodos
        self.est = {}               # id -> dados internos
        self.ativo_s = float(cfg.get("ativo_s", 1800))

    # -------------------------------------------------------------- utilidades
    def caminho(self, x):
        x = os.path.expanduser(str(x))
        return Path(x) if os.path.isabs(x) else (self.base / x)

    def expandir(self, padrao):
        p = self.caminho(padrao)
        if any(c in str(padrao) for c in "*?["):
            return [Path(x) for x in sorted(glob.glob(str(p), recursive=True))]
        return [p]

    def aviso(self, msg):
        if msg not in self.avisos:
            self.avisos.append(msg)

    def nz(self, v):
        return self.T["nao_registrado"] if v in (None, "", [], {}) else str(v)

    def selo(self, R, declarado=None):
        """'nível · programa versão' lido do arquivo; o que falta vem da configuração (marcado) ou 'não registrado'."""
        niv = (R or {}).get("nivel") or {}
        metodo = niv.get("metodo")
        partes_extra = [niv.get(k) for k in ("base",) if niv.get(k) and niv.get(k) not in (metodo or "")]
        prog = (R or {}).get("programa")
        ver = (R or {}).get("versao")
        dec = declarado if isinstance(declarado, dict) else ({"nivel": declarado} if declarado else {})
        marc = []
        if not metodo and dec.get("nivel"):
            metodo = dec["nivel"]
            marc.append("nível")
        if not prog and dec.get("programa"):
            prog = dec["programa"]
            marc.append("programa")
        if not ver and dec.get("versao"):
            ver = dec["versao"]
            marc.append("versão")
        tarefa = niv.get("tarefa") or niv.get("task")
        if metodo and tarefa:
            metodo = f"{metodo} ({self.T['m_tarefa_curto']} {tarefa})"
        nivel_txt = " / ".join([metodo] + partes_extra) if metodo else self.T["nao_registrado"]
        prog_txt = f"{prog} {ver}" if prog and ver else (f"{prog} ({self.T['versao_nr']})" if prog else self.T["programa_nr"])
        s = f"{nivel_txt} · {prog_txt}"
        if marc:
            s += f" ({self.T['declarado']}: {', '.join(marc)})"
        return s

    def registrar_uso(self, rotulo, R, declarado):
        self.usados.append((rotulo, R, declarado))

    # -------------------------------------------------------------- estruturas
    def coletar_estruturas(self):
        lista = []
        comps_glob = self.cfg.get("componentes") or []
        for e in self.cfg.get("estruturas") or []:
            if isinstance(e, str):
                e = {"arquivo": e}
            arqs = self.expandir(e["arquivo"])
            if not arqs:
                self.aviso(self.T["av_sem_arquivo"].format(e["arquivo"]))
                continue
            for arq in arqs:
                d = dict(e)
                d["arquivo"] = arq
                ident = str(e.get("id") or arq.stem)
                campos = {"stem": arq.stem, "pasta": arq.parent.name}
                if e.get("padrao"):
                    m = re.search(e["padrao"], arq.name)
                    if m:
                        campos.update({k: v for k, v in m.groupdict().items() if v is not None})
                if len(arqs) > 1 and "{" not in ident:
                    ident = ident + "_" + arq.stem
                try:
                    d["id"] = ident.format(**campos)
                    for k in ("nome", "item", "replica", "grupo", "inicial", "trajetoria", "progresso", "registro", "nota"):
                        if isinstance(e.get(k), str):
                            d[k] = e[k].format(**campos)
                except (KeyError, IndexError):
                    d["id"] = ident
                for k in ("item", "replica"):
                    if k not in d and k in campos:
                        d[k] = campos[k]
                if any(x["id"] == d["id"] for x in lista):   # id repetido sobrescreveria a estrutura anterior em silêncio
                    self.aviso(self.T["av_id_repetido"].format(d["id"], rel(arq, self.base)))
                    continue
                lista.append(d)
        for e in lista:
            try:
                self._estrutura(e, comps_glob)
            except Exception as ex:  # noqa: BLE001
                self.aviso(f"{e['id']}: {type(ex).__name__}: {str(self.tr(ex))[:200]}")
        return lista

    def _estrutura(self, e, comps_glob):
        R = LEITURA.ler(e["arquivo"], e.get("formato"))
        for a in R["avisos"]:
            self.aviso(f"{e['id']}: {self.tr(a)}")
        if R["estado"] in ("ilegivel", "ausente"):
            return
        quadros = list(R["quadros"])
        if e.get("trajetoria"):
            for tp in self.expandir(e["trajetoria"]):
                T = LEITURA.ler(tp)
                if T["quadros"]:
                    quadros = T["quadros"]
                    if R["energia_eV"] is None:
                        R = dict(R, energia_eV=T["quadros"][-1]["E_eV"])
                for a in T["avisos"]:
                    self.aviso(f"{e['id']}: {self.tr(a)}")
        if not quadros:
            self.aviso(self.T["av_sem_geometria"].format(e["id"]))
            return
        ini_q = quadros[0]
        if e.get("inicial"):
            I = LEITURA.ler(self.caminho(e["inicial"]))
            if I["quadros"]:
                ini_q = I["quadros"][-1] if not e.get("inicial_primeiro") else I["quadros"][0]
            else:
                self.aviso(self.T["av_inicial"].format(e["id"], e["inicial"]))
        fin_q = quadros[-1]
        caixa = bool(e.get("molecula_em_caixa")) or fin_q["celula"] is None or not fin_q.get("pbc", True)
        cel_i = None if caixa else ini_q["celula"]
        cel_f = None if caixa else fin_q["celula"]
        sim = fin_q["simbolos"]
        mesmo = list(ini_q["simbolos"]) == list(sim)
        if not mesmo:
            ini_q = fin_q
            cel_i = cel_f
        u, lab, pares = G.desembrulhar(ini_q["simbolos"], ini_q["pos"], cel_i)
        cart, disp = G.mapear(u, ini_q["pos"], cel_i, fin_q["pos"], cel_f)
        comps = e.get("componentes") or comps_glob
        ctx = G.Contexto(sim, lab, pares, comps)
        papel = ctx.papel
        if not comps:                                     # automático: uma classe por fórmula distinta
            fs = []
            for f in ctx.formulas:
                if f not in fs:
                    fs.append(f)
            if 1 < len(fs) <= len(PALETA):
                comps = [{"nome": f, "formula": f} for f in fs]
                ctx = G.Contexto(sim, lab, pares, comps)
                papel = ctx.papel
        lista_comps = [{"nome": c.get("nome") or c.get("formula") or f"#{k + 1}", "cor": c.get("cor") or PALETA[k % len(PALETA)]}
                       for k, c in enumerate(comps)]
        n_fu = float(e.get("n_fu", 1) or 1)
        E = R["energia_eV"] if R["energia_eV"] is not None else fin_q["E_eV"]
        selo = self.selo(R, e.get("nivel"))
        self.registrar_uso(e.get("nome") or e["id"], R, e.get("nivel"))
        estado = L.estado_final(R, self.ativo_s)
        prog = None
        if e.get("progresso"):
            ps = self.expandir(e["progresso"])
            if ps and ps[0].exists():
                prog = L.ler_jsonl_progresso(ps[0])
                if prog["fim"] is None and prog["n"]:
                    idade = time.time() - ps[0].stat().st_mtime
                    estado = "rodando" if idade < self.ativo_s else "parado"
        reg = {}
        if e.get("registro"):                         # JSON por estrutura: completa o que o arquivo não registra
            try:
                reg = json.loads(self.caminho(e["registro"]).read_text(encoding="utf-8"))
                reg = reg if isinstance(reg, dict) else {}
            except Exception as ex:  # noqa: BLE001
                self.aviso(self.T["av_registro"].format(e["id"], e["registro"], type(ex).__name__))
        pega = lambda d, *ks: next((d[k] for k in ks if d.get(k) is not None), None)  # noqa: E731
        conv = R.get("convergiu")
        if conv is None and prog and prog["fim"] is not None:
            conv = prog["fim"].get("convergiu")
        if conv is None and pega(reg, "convergiu", "converged") is not None:
            conv = bool(pega(reg, "convergiu", "converged"))
        fmax_f = fin_q.get("fmax")
        passos = (len(quadros) - 1) if len(quadros) > 1 else None
        if prog and prog["fim"] and prog["fim"].get("passos") is not None:
            passos = prog["fim"]["passos"]
        if passos is None:
            passos = pega(reg, "passos", "steps", "n_passos")
        self.est[e["id"]] = {"cfg": e, "R": R, "quadros": quadros, "ini_q": ini_q, "fin_q": fin_q, "u": u, "cart": cart,
                             "cel_i": cel_i, "cel_f": cel_f, "ctx": ctx, "prog": prog, "selo": selo, "E": E}
        self.est[e["id"]]["json"] = {
            "id": e["id"], "nome": e.get("nome") or e["id"], "grupo": e.get("grupo"), "item": e.get("item"),
            "replica": e.get("replica"), "papel": e.get("papel"), "n_fu": n_fu, "rotulo_fu": e.get("rotulo_fu"),
            "el": list(sim), "comp": [int(x) for x in papel], "comps": lista_comps, "caixa": caixa,
            "ini": ints(u, 1000), "cel_i": cel_list(cel_i), "cp_i": cellpar(cel_i),
            "pos": ints(cart, 1000), "cel": cel_list(cel_f), "cp": cellpar(cel_f), "disp": ints(disp, 100),
            "E": E, "conv": conv, "passos": passos, "fmax": fmax_f, "sig": fin_q.get("sigma_GPa"),
            "t": R.get("duracao_s") or (prog["fim"].get("tempo_s") if prog and prog["fim"] else None) or pega(reg, "tempo_s", "duracao_s", "elapsed_s"),
            "estado": estado, "selo": selo, "arquivo": rel(e["arquivo"], self.base), "programa": R.get("programa"),
            "inicial": rel(self.caminho(e["inicial"]), self.base) if e.get("inicial") else None,
            "nota": e.get("nota"), "n_quadros": len(quadros), "mesmo_ini": mesmo,
        }

    # -------------------------------------------------------------- filmes
    def coletar_filmes(self):
        filmes, usado, omitidos = [], 0, 0
        cands = []
        for k, X in self.est.items():
            if len(X["quadros"]) >= 2:
                cands.append((k, X["json"]["nome"], X["quadros"], X["prog"], X))
        for f in self.cfg.get("filmes") or []:
            for arq in self.expandir(f["arquivo"]):
                R = LEITURA.ler(arq)
                if len(R["quadros"]) < 2:
                    continue
                prog = None
                if f.get("progresso"):
                    ps = self.expandir(f["progresso"].format(stem=arq.stem))
                    if ps and ps[0].exists():
                        prog = L.ler_jsonl_progresso(ps[0])
                cands.append((None, (f.get("nome") or arq.stem).format(stem=arq.stem), R["quadros"], prog,
                              {"selo": self.selo(R, f.get("nivel"))}))
        for est_id, nome, Q, prog, X in cands:
            n = len(Q[0]["simbolos"])
            if any(len(q["simbolos"]) != n for q in Q):
                continue
            idx = amostrar(len(Q), min(FILM_MAX_QUADROS, max(8, 120_000 // max(n, 1))))
            custo = len(idx) * n * 3 * 6
            if usado + custo > FILM_ORCAMENTO_B:
                omitidos += 1
                continue
            usado += custo
            fr, cells, Eq = [], [], []
            for k in idx:
                q = Q[k]
                if est_id and X["cel_i"] is not None and q["celula"] is not None and list(q["simbolos"]) == list(X["ini_q"]["simbolos"]):
                    c = G.mapear(X["u"], X["ini_q"]["pos"], X["cel_i"], q["pos"], q["celula"])[0]
                elif est_id and X["cel_i"] is None and list(q["simbolos"]) == list(X["ini_q"]["simbolos"]):
                    c = G.alinhar(q["pos"], X["u"])
                else:
                    c = q["pos"]
                fr.append(ints(c, 100))
                cells.append(cel_list(q["celula"]) if (q["celula"] is not None and not (est_id and self.est[est_id]["json"]["caixa"])) else None)
                Eq.append(q["E_eV"])
            serie = None
            if prog and prog["n"]:
                serie = {k2: prog["serie"][k2] for k2 in ("passo", "fase", "E", "fmax", "sig")}
            else:
                serie = {"passo": list(range(len(Q))), "fase": [None] * len(Q), "E": [q["E_eV"] for q in Q],
                         "fmax": [q["fmax"] for q in Q], "sig": [q["sigma_GPa"] for q in Q]}
            filmes.append({"id": f"f{len(filmes)}", "nome": nome, "est": est_id, "n": n, "el": list(Q[0]["simbolos"]),
                           "quadros_originais": len(Q), "idx": idx, "pos": fr, "cells": cells, "Eq": Eq, "serie": serie,
                           "viva": bool(prog and prog["n"] and prog["fim"] is None), "selo": X["selo"]})
        return filmes, omitidos

    # -------------------------------------------------------------- etapas ("você está aqui")
    def coletar_etapas(self, fila):
        out = []
        por_nome_fila = {j["nome"]: j for j in fila}
        for k, e in enumerate(self.cfg.get("etapas") or []):
            itens = []          # (estado, inicio, fim, duracao)
            for padrao in as_list(e.get("arquivos")):
                for arq in self.expandir(padrao):
                    R = LEITURA.ler(arq)
                    st_arq = L.estado_final(R, self.ativo_s)
                    if st_arq in ("ilegivel", "desconhecido"):
                        st_arq = "concluido"          # artefato presente, sem estado próprio legível: conta como feito
                    itens.append((st_arq if R["estado"] != "ausente" else "pendente",
                                  R.get("inicio"), R.get("fim") or (R.get("mtime") if R["estado"] == "concluido" else None), R.get("duracao_s"),
                                  R.get("mtime")))
            for ident in as_list(e.get("estruturas")):
                X = self.est.get(ident)
                if X:
                    R = X["R"]
                    itens.append((X["json"]["estado"], R.get("inicio"), R.get("fim"), R.get("duracao_s") or X["json"]["t"], R.get("mtime")))
                else:
                    itens.append(("pendente", None, None, None, None))
            for nm in as_list(e.get("fila")):
                j = por_nome_fila.get(nm)
                itens.append((j["estado"] if j else "pendente", None, None, j.get("duracao_s") if j else None, None))
            total = e.get("total") or (len(itens) or None)
            feito = sum(1 for x in itens if x[0] == "concluido")
            rod = sum(1 for x in itens if x[0] == "rodando")
            falhou = sum(1 for x in itens if x[0] == "falhou")
            parado = sum(1 for x in itens if x[0] == "parado")
            if e.get("estado"):
                st = {"concluído": "concluido", "done": "concluido", "running": "rodando", "pending": "pendente",
                      "failed": "falhou"}.get(e["estado"], e["estado"])
            elif not itens or (feito == 0 and rod == 0 and falhou == 0 and parado == 0):
                st = "pendente"
            elif total and feito >= total:
                st = "concluido"
            elif rod:
                st = "rodando"
            elif falhou:
                st = "falhou"
            elif parado:
                st = "parado"
            else:
                st = "parcial"
            eta = estimar_eta_etapa(itens, total, feito, rod, e.get("paralelo", 1)) if st in ("rodando", "parcial") else None
            ts = max([x[4] for x in itens if x[4]] or [0]) or None
            out.append({"id": e.get("id") or f"E{k + 1}", "nome": e.get("nome") or e.get("id") or f"E{k + 1}", "estado": st,
                        "feito": feito if (total and total > 1 or e.get("total")) else None, "total": total if (total and total > 1 or e.get("total")) else None,
                        "rodando": rod, "falhou": falhou, "nota": e.get("nota"), "depende_de": as_list(e.get("depende_de")),
                        "ts": quando(ts) if ts else None, "eta": eta, "selo": e.get("selo")})
        return out

    def coletar_andamento(self, filmes):
        out = []
        agora = time.time()
        for f in filmes:
            if not f["viva"]:
                continue
            s = f["serie"]
            k = len(s["E"]) - 1
            out.append({"nome": f["nome"], "passo": s["passo"][k], "fase": s["fase"][k], "E": s["E"][k], "fmax": s["fmax"][k],
                        "sig": s["sig"][k], "filme": f["id"]})
        for X in self.est.values():
            j = X["json"]
            if j["estado"] == "rodando" and not any(o["nome"] == j["nome"] for o in out):
                q = X["fin_q"]
                out.append({"nome": j["nome"], "passo": j["n_quadros"] - 1, "fase": None, "E": q["E_eV"], "fmax": q["fmax"],
                            "sig": q["sigma_GPa"], "idade_s": int(agora - (X["R"]["mtime"] or agora))})
        return out

    # -------------------------------------------------------------- fila de cálculos externos
    def coletar_fila(self):
        jobs, metas = [], []
        for ent in self.cfg.get("fila") or []:
            if isinstance(ent, str):
                ent = {"saida": ent}
            if ent.get("json_vivo"):
                for arq in self.expandir(ent["json_vivo"]):
                    try:
                        V = json.loads(arq.read_text(encoding="utf-8"))
                    except Exception as ex:  # noqa: BLE001
                        self.aviso(self.T["av_json_vivo"].format(arq.name, ex))
                        continue
                    metas.append({"arquivo": arq.name, "quando": V.get("quando"), "log": (V.get("fila_log") or [])[-10:],
                                  "grupo": ent.get("grupo")})
                    vistos = set()
                    for j in V.get("jobs", []):
                        jobs.append(self._job_vivo(j, V.get("quando"), ent))
                        vistos.add(jobs[-1]["nome"])
                    nomes = []                       # jobs previstos que o JSON ainda não cita: pendentes
                    for lst in as_list(ent.get("nomes_de")):
                        for f in self.expandir(lst):
                            if f.exists():
                                nomes += [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
                    for pd in as_list(ent.get("pastas")):
                        nomes += [d.name for d in self.expandir(pd) if d.is_dir()]
                    for nm in nomes:
                        if nm not in vistos:
                            vistos.add(nm)
                            jobs.append({"nome": nm, "estado": "pendente", "grupo": ent.get("grupo"), "scf": [],
                                         "selo": self.selo({"programa": ent.get("programa"), "versao": None, "nivel": {}}, ent.get("nivel"))})
                continue
            for arq in self.expandir(ent.get("saida") or ent.get("arquivo")):
                if arq.is_dir():
                    saidas = sorted([x for x in arq.iterdir() if x.suffix in (".out", ".log") and x.is_file()], key=lambda x: x.stat().st_mtime)
                    R = LEITURA.ler(saidas[-1]) if saidas else None
                    nome = (ent.get("nome") or "{pasta}").format(pasta=arq.name, stem=arq.name)
                else:
                    R = LEITURA.ler(arq) if arq.exists() else None
                    nome = (ent.get("nome") or "{stem}").format(stem=arq.stem, pasta=arq.parent.name)
                jobs.append(self._job_saida(nome, R, ent))
        return jobs, metas

    def _job_saida(self, nome, R, ent):
        if R is None or R["estado"] == "ausente":
            return {"nome": nome, "estado": "pendente", "grupo": ent.get("grupo"), "selo": self.selo(None, ent.get("nivel")), "scf": []}
        for a in R["avisos"]:
            self.aviso(f"{nome}: {self.tr(a)}")
        st = L.estado_final(R, float(ent.get("ativo_s", self.ativo_s)))
        if ent.get("estado"):
            st = ent["estado"]
        scf = [[r["it"], r.get("E"), r.get("dE"), r.get("conv"), r.get("t_s")] for r in R["scf"]]
        crit = R.get("scf_criterio")
        if crit and crit.get("nota") is not None:
            crit = dict(crit, nota=self.tr(crit["nota"]))
        if ent.get("criterio"):
            crit = dict(crit or {}, **ent["criterio"])
        self.registrar_uso(nome, R, ent.get("nivel"))
        j = {"nome": nome, "estado": st, "grupo": ent.get("grupo"), "programa": R.get("programa"), "tipo": R.get("tipo"),
             "selo": self.selo(R, ent.get("nivel")), "scf": scf, "criterio": crit, "scf_convergiu": R.get("scf_convergiu"),
             "n_ciclos_scf": R.get("n_ciclos_scf"), "energia_eV": R.get("energia_eV"), "duracao_s": R.get("duracao_s"),
             "ts": quando(R["mtime"]) if R.get("mtime") else None, "arquivo": rel(Path(R["arquivo"]), self.base),
             "n_atomos": len(R["quadros"][-1]["simbolos"]) if R["quadros"] else None, "unidade_E": R.get("scf_unidade_E"),
             "inicio": quando(R["inicio"]) if R.get("inicio") else None, "nota": ent.get("nota")}
        if st == "rodando":
            agora = time.time()
            ini = R.get("inicio")
            j["eta"] = estimar_eta_scf(scf, crit, (agora - ini) if ini else None)
        return j

    def _job_vivo(self, J, quando_txt, ent):
        mapa = {"ok": "concluido", "pendente": "pendente", "rodando": "rodando", "falhou": "falhou", "concluido": "concluido",
                "running": "rodando", "done": "concluido", "failed": "falhou", "pending": "pendente"}
        st = mapa.get(J.get("estado") or J.get("status"), J.get("estado") or "desconhecido")
        scf = [list(r) + [None] * (5 - len(r)) for r in (J.get("scf") or [])]
        crit = ent.get("criterio") or ({"nome": "EPS_SCF", "valor": 1e-6, "coluna": "Convergence"} if any(r[3] for r in scf) else None)
        if crit and ent.get("criterio") is None:
            crit["nota"] = self.T["crit_padrao_vivo"]
        decorrido = None
        for l in J.get("walltime") or []:
            m = re.search(r"START\s+\w+\s+(\w+\s+\d+\s+[\d:]+)", l)
            if m and quando_txt:
                try:
                    t0 = time.mktime(time.strptime(m.group(1) + " " + quando_txt[:4], "%b %d %H:%M:%S %Y"))
                    t1 = time.mktime(time.strptime(quando_txt, "%Y-%m-%d %H:%M:%S"))
                    decorrido = t1 - t0
                except Exception:
                    pass
        E = J.get("energia_Ha")
        j = {"nome": J.get("job") or J.get("nome"), "estado": st, "grupo": ent.get("grupo"), "programa": ent.get("programa"),
             "selo": self.selo({"programa": ent.get("programa"), "versao": ent.get("versao"), "nivel": {}}, ent.get("nivel")),
             "scf": scf, "criterio": crit, "scf_convergiu": J.get("scf_convergiu"), "abortou": bool(J.get("abortou")),
             "energia_eV": float(E) * L.HA_EV if E not in (None, "") else None, "walltime": J.get("walltime") or [],
             "ts": quando_txt, "unidade_E": "Ha", "nota": ent.get("nota")}
        if st == "rodando":
            j["eta"] = estimar_eta_scf(scf, crit, decorrido)
        return j

    # -------------------------------------------------------------- energia (diagramas e parcelas)
    def coletar_energia(self):
        cfg = self.cfg.get("energia")
        if not cfg:
            return None
        termos = cfg.get("termos") or {}
        variantes = {cfg.get("nome_principal") or self.T["principal"]: {}}
        variantes.update(cfg.get("variantes") or {})
        out = {"variantes": list(variantes), "diagramas": [], "parcelas": [], "selos": {}, "avisos": [], "rotulo_por": cfg.get("por"),
               "digitados": []}
        valores = {}
        principal = next(iter(variantes))
        for vn, sobre in variantes.items():
            sobre = dict(sobre or {})
            herdar = sobre.pop("herdar", False)          # variantes não herdam termos (evita misturar níveis sem querer)
            tv = dict(termos) if (vn == principal or herdar) else {}
            tv.update(sobre)
            vals, selos = {}, {}
            for nome, t in tv.items():
                try:
                    vals[nome], selos[nome] = self._termo(nome, t, out)
                except Exception as ex:  # noqa: BLE001
                    out["avisos"].append(self.T["av_termo"].format(nome, vn, ex))
            valores[vn] = (vals, selos)
        def avaliar(expr, vn):
            vals, selos = valores[vn]
            try:
                nomes = nomes_expr(expr)
                if any(n not in vals for n in nomes):
                    return None, set()
                return calc_expr(expr, vals), {selos[n] for n in nomes}
            except Exception as ex:  # noqa: BLE001  (sintaxe inválida, divisão por zero, construção não permitida)
                out["avisos"].append(self.T["av_expr"].format(expr, f"{type(ex).__name__}: {ex}"))
                return None, set()
        def checar(ss, onde, vn):
            if len(ss) > 1:
                out["avisos"].append(self.T["av_mistura"].format(onde, vn, " | ".join(sorted(ss))))
        for dg in cfg.get("diagramas") or ([cfg["diagrama"]] if cfg.get("diagrama") else []):
            niveis = []
            for nv in dg.get("niveis") or []:
                ev, todos = {}, set()
                for vn in variantes:
                    v, ss = avaliar(nv["expr"], vn)
                    if v is not None and dg.get("referencia"):
                        r, ss2 = avaliar(dg["referencia"], vn)
                        v = None if r is None else v - r
                        ss |= ss2
                    ev[vn] = v
                    checar(ss, nv.get("rotulo", nv["expr"]), vn)
                niveis.append({"rotulo": nv.get("rotulo") or nv["expr"], "ev": ev, "cor": nv.get("cor"), "x": nv.get("x")})
            out["diagramas"].append({"titulo": dg.get("titulo"), "tipo": dg.get("tipo", "niveis"), "niveis": niveis,
                                     "passos": dg.get("passos") or [], "nota": dg.get("nota"),
                                     "ligar": dg.get("ligar", dg.get("tipo", "niveis") == "perfil")})
        for pc in cfg.get("parcelas") or []:
            ev = {}
            for vn in variantes:
                v, ss = avaliar(pc["expr"], vn)
                ev[vn] = v
                checar(ss, pc.get("nome", pc["expr"]), vn)
            out["parcelas"].append({"nome": pc.get("nome") or pc["expr"], "ev": ev, "classe": pc.get("classe", "auto"),
                                    "txt": pc.get("explicacao"), "expr": pc["expr"],
                                    "rs": self._ressalvas_inline(pc.get("ressalvas"), pc.get("nome") or pc["expr"])})
        for vn in variantes:
            out["selos"][vn] = sorted(set(valores[vn][1].values()))
        out["avisos"] = list(dict.fromkeys(out["avisos"]))
        for a in out["avisos"]:
            self.aviso(a)
        return out

    def _termo(self, nome, t, out):
        if isinstance(t, (int, float)):
            out["digitados"].append(nome)
            return float(t), self.T["digitado"]
        if isinstance(t, str):
            t = {"estrutura": t}
        if "estrutura" in t:
            X = self.est.get(t["estrutura"])
            if X is None or X["E"] is None:
                raise ValueError(self.T["av_sem_energia"].format(t["estrutura"]))
            E = X["E"] / (X["json"]["n_fu"] if t.get("por_fu") else 1)
            return E, X["selo"]
        if "json" in t:
            arq = self.caminho(t["json"])
            d = json.loads(arq.read_text(encoding="utf-8"))
            for k in str(t.get("caminho", "")).split("."):
                if k:
                    d = d[int(k)] if isinstance(d, list) else d[k]
            v = float(d) * UNID_EV[str(t.get("unidade", "eV")).lower()]
            sel = self.selo({"programa": None, "versao": None, "nivel": {}}, t.get("nivel")) if t.get("nivel") else f"{self.T['nao_registrado']} ({arq.name})"
            return v, sel
        if "valor" in t:
            out["digitados"].append(f"{nome} ({t.get('fonte') or self.T['sem_fonte']})")
            v = float(t["valor"]) * UNID_EV[str(t.get("unidade", "eV")).lower()]
            return v, self.T["digitado"]
        raise ValueError(self.T["av_termo_tipo"])

    # -------------------------------------------------------------- ranking
    def coletar_ranking(self):
        out = []
        for rk in self.cfg.get("ranking") or []:
            itens = {}
            selo = set()
            if rk.get("json"):
                d = json.loads(self.caminho(rk["json"]).read_text(encoding="utf-8"))
                for k in str(rk.get("caminho", "")).split("."):
                    if k:
                        d = d[k]
                ue = UNID_EV[str(rk.get("unidade", "eV")).lower()]
                uerr = UNID_EV[str(rk.get("unidade_erro", rk.get("unidade", "eV"))).lower()]
                for nome, v in d.items():
                    E = v.get(rk.get("campo_energia", "E")) if isinstance(v, dict) else v
                    if E is None:
                        continue
                    er = v.get(rk["campo_erro"]) if isinstance(v, dict) and rk.get("campo_erro") else None
                    rot = re.sub(rk.get("tirar_prefixo", "^$"), "", nome)
                    alvo = None
                    if rk.get("abre_estrutura"):
                        alvo = rk["abre_estrutura"].format(nome=nome, **(v if isinstance(v, dict) else {}))
                    itens[nome] = {"rotulo": rot, "E": float(E) * ue, "erro": None if er is None else float(er) * uerr, "n": v.get("n_partidas") if isinstance(v, dict) else None,
                                   "est": alvo if alvo in self.est else None}
                selo.add(self.selo({"programa": None, "versao": None, "nivel": {}}, rk.get("nivel")) if rk.get("nivel") else self.T["nao_registrado"])
            else:
                grupo = rk.get("grupo")
                por = {}
                for k, X in self.est.items():
                    j = X["json"]
                    if grupo and j["grupo"] != grupo:
                        continue
                    if X["E"] is None:
                        continue
                    if rk.get("so_convergidas", True) and j["conv"] is False:
                        continue
                    por.setdefault(str(j["item"] or j["id"]), []).append((X["E"] / (j["n_fu"] if rk.get("por_fu", True) else 1), k, X["selo"]))
                for it, lst in por.items():
                    lst.sort()
                    Es = [x[0] for x in lst]
                    itens[it] = {"rotulo": rk.get("rotulos", {}).get(it, it), "E": Es[0], "erro": (max(Es) - min(Es)) if len(Es) > 1 else None,
                                 "n": len(Es), "est": lst[0][1]}
                    selo |= {x[2] for x in lst}
            if not itens:
                continue
            emin = min(v["E"] for v in itens.values())
            lista = sorted(({**v, "rel": v["E"] - emin} for v in itens.values()), key=lambda v: v["rel"])
            out.append({"titulo": rk.get("titulo") or self.T["ranking"], "itens": lista, "selos": sorted(selo),
                        "nota": rk.get("nota"), "rotulo_por": rk.get("por"), "erro_rotulo": rk.get("erro_rotulo"),
                        "rs": self._ressalvas_inline(rk.get("ressalvas"), rk.get("titulo") or "ranking")})
            if len(selo) > 1:
                self.aviso(self.T["av_mistura"].format(rk.get("titulo") or self.T["ranking"], "", " | ".join(sorted(selo))))
        return out

    # -------------------------------------------------------------- medidas
    def coletar_medidas(self):
        defs = self.cfg.get("medidas") or []
        if not defs:
            return None
        out = {"defs": [], "val": {}, "des": {}, "des_ini": {}}
        nomeados = self.cfg.get("grupos") or {}
        for k, md in enumerate(defs):
            mid = md.get("id") or f"m{k + 1}"
            un = G.TIPOS_MEDIDA.get(md.get("tipo", "distancia"), "")
            ref = md.get("referencia")
            refv, reff = None, None
            if isinstance(ref, (int, float)):
                refv, reff = float(ref), self.T["digitado"]
            elif isinstance(ref, dict) and "valor" in ref:
                refv, reff = float(ref["valor"]), ref.get("fonte") or self.T["digitado"]
            elif isinstance(ref, dict) and "estrutura" in ref:
                reff = ref["estrutura"]
            elif isinstance(ref, dict) and "json" in ref:
                try:
                    d = json.loads(self.caminho(ref["json"]).read_text(encoding="utf-8"))
                    for k2 in str(ref.get("caminho", "")).split("."):
                        if k2:
                            d = d[int(k2)] if isinstance(d, list) else d[k2]
                    refv, reff = float(d), ref.get("fonte") or Path(ref["json"]).name
                except Exception as ex:  # noqa: BLE001
                    self.aviso(self.T["av_ref_ilegivel"].format(mid, ex))
            out["defs"].append({"id": mid, "nome": md.get("nome") or mid, "tipo": md.get("tipo", "distancia"), "un": un,
                                "dig": md.get("casas", 3 if un == "Å" else 1), "tol": md.get("tolerancia"), "ref": refv,
                                "ref_fonte": reff, "ref_est": ref.get("estrutura") if isinstance(ref, dict) else None,
                                "ref_inicial": bool(isinstance(ref, dict) and ref.get("inicial")), "expl": md.get("explicacao"),
                                "a": md.get("a"), "b": md.get("b"), "aplicar_a": None,
                                "_aplicar": ref.get("aplicar_a") if isinstance(ref, dict) else None})
        for eid, X in self.est.items():
            j = X["json"]
            for k, md in enumerate(defs):
                mid = out["defs"][k]["id"]
                alvo = md.get("estruturas")
                if alvo and eid not in alvo and j["grupo"] not in alvo:
                    continue
                try:
                    rf = G.medir(md, X["ctx"], X["cart"], X["cel_f"], nomeados)
                    ri = G.medir(md, X["ctx"], X["u"], X["cel_i"], nomeados)
                except Exception as ex:  # noqa: BLE001
                    self.aviso(f"{mid} @ {eid}: {self.tr(ex)}")
                    continue
                if rf["valor"] is None and ri["valor"] is None:
                    continue
                out["val"].setdefault(eid, {})[mid] = {"f": rf["valor"], "i": ri["valor"], "lista": rf["valores"]}
                out["des"].setdefault(eid, {})[mid] = rf["desenho"]
                out["des_ini"].setdefault(eid, {})[mid] = ri["desenho"]
        for d in out["defs"]:                     # a referência vale só para estas estruturas (ids ou grupos)
            alvo = d.pop("_aplicar")
            if alvo:
                d["aplicar_a"] = [k for k, X in self.est.items() if k in alvo or X["json"]["grupo"] in alvo or str(X["json"]["item"]) in alvo]
        for d in out["defs"]:                     # referência dada por outra estrutura (inicial ou final)
            if d["ref_est"]:
                v = out["val"].get(d["ref_est"], {}).get(d["id"])
                d["ref"] = None if v is None else v["i" if d["ref_inicial"] else "f"]
                X = self.est.get(d["ref_est"])
                d["ref_fonte"] = (X["json"]["nome"] if X else d["ref_est"]) + (f" ({self.T['geom_inicial']})" if d["ref_inicial"] else "")
        return out

    # -------------------------------------------------------------- frequências
    def coletar_freq(self):
        cfg = self.cfg.get("frequencias")
        if not cfg:
            return None
        sistemas = cfg if isinstance(cfg, list) else cfg.get("sistemas", [])
        comparar = [] if isinstance(cfg, list) else cfg.get("comparar", [])
        comparar = comparar or self.cfg.get("comparar_frequencias") or []
        out = {"sistemas": [], "comparar": [], "omitidos": 0}
        orc = 0
        for k, s in enumerate(sistemas):
            if isinstance(s, str):
                s = {"arquivo": s}
            for arq in self.expandir(s["arquivo"]):
                R = LEITURA.ler(arq)
                for a in R["avisos"]:
                    self.aviso(f"{arq.name}: {self.tr(a)}")
                if not R.get("freq"):
                    self.aviso(self.T["av_sem_freq"].format(arq.name))
                    continue
                F = R["freq"]
                dec = s.get("nivel") if isinstance(s.get("nivel"), dict) else {}
                classe = s.get("classe") or L.classe_programa(R.get("programa") or dec.get("programa")) or "?"
                self.registrar_uso(s.get("nome") or arq.stem, R, s.get("nivel"))
                modos = F["modos"]
                if modos:
                    modos = [[[round(float(x), 3) for x in v] for v in m] for m in modos]
                    tam = len(json.dumps(modos))
                    if orc + tam > FREQ_ORCAMENTO_B:
                        modos = None
                        out["omitidos"] += 1
                    else:
                        orc += tam
                ident = s.get("id") or arq.stem
                if len(self.expandir(s["arquivo"])) > 1:
                    ident = f"{ident}_{arq.stem}"
                val = None
                if s.get("referencia"):
                    ref = s["referencia"]
                    if isinstance(ref, dict) and ref.get("json"):
                        try:
                            ref = self._ref_freq_json(ref)
                        except Exception as ex:  # noqa: BLE001
                            self.aviso(self.T["av_ref_ilegivel"].format(ident, f"{type(ex).__name__}: {ex}"))
                            ref = None
                    val = validar_freq(F["freqs_cm1"], ref) if ref else None
                out["sistemas"].append({"id": ident, "nome": s.get("nome") or ident, "classe": classe, "rotulo": s.get("rotulo") or R["extra"].get("rotulo"),
                                        "selo": self.selo(R, s.get("nivel")), "freqs": F["freqs_cm1"], "modos": modos, "sim": F["simbolos"],
                                        "pos": F["pos"], "idx": F["idx"], "cel": F.get("celula"), "nimag": F["n_imag"],
                                        "zpe": None if F.get("zpe_kJmol") is None else F["zpe_kJmol"] / EV_KJ, "valid": val,
                                        "est": s.get("estrutura"), "arquivo": rel(arq, self.base)})
        ids = {x["id"] for x in out["sistemas"]}
        for par in comparar:
            a, b = (par[0], par[1]) if isinstance(par, list) else (par.get("a"), par.get("b"))
            if a in ids and b in ids:
                A = next(x for x in out["sistemas"] if x["id"] == a)
                B = next(x for x in out["sistemas"] if x["id"] == b)
                lim = (par.get("acima_de", 300) if isinstance(par, dict) else 300)
                out["comparar"].append({"a": a, "b": b, **comparar_freq(A["freqs"], B["freqs"], lim)})
            else:
                self.aviso(self.T["av_comparar"].format(a, b))
        return out

    def _ref_freq_json(self, ref):
        """tabela de referência num JSON: lista de dicionários; campo_rotulo aceita modelo ('{especie} · {descricao}')."""
        d = json.loads(self.caminho(ref["json"]).read_text(encoding="utf-8"))
        for k in str(ref.get("caminho", "")).split("."):
            if k:
                d = d[int(k)] if isinstance(d, list) else d[k]
        cr, cv, cc = ref.get("campo_rotulo", "rotulo"), ref.get("campo_valor", "valor"), ref.get("campo_calc")
        modos = []
        for r in d if isinstance(d, list) else []:
            if not isinstance(r, dict) or r.get(cv) is None:
                continue
            m = {"rotulo": cr.format(**r) if "{" in cr else r.get(cr), "valor": r[cv]}
            if cc and r.get(cc) is not None:
                m["calc"] = r[cc]
            modos.append(m)
        return dict({k: v for k, v in ref.items() if k not in ("json", "caminho", "campo_rotulo", "campo_valor", "campo_calc")}, modos=modos)

    # -------------------------------------------------------------- utilidades das novas seções
    def tr(self, x):
        return traduzir(x, self.lang)

    def _lista(self, chave, valor):
        """valor da configuração que precisa ser lista (aceita um item solto)."""
        if valor is None:
            return []
        if isinstance(valor, dict):
            return [valor]
        if not isinstance(valor, list):
            self.aviso(self.T["av_cfg_tipo"].format(chave))
            return []
        return valor

    def _expandir_pares(self, spec):
        """(a, b, campos) de uma especificação: `a`/`b` explícitos, ou `a_grupo` + `b` com {item}, {replica}, {id}, {stem}."""
        if spec.get("a_grupo"):
            for k, X in self.est.items():
                j = X["json"]
                if j["grupo"] != spec["a_grupo"]:
                    continue
                campos = {"id": k, "item": j.get("item") or "", "replica": j.get("replica") or "", "grupo": j.get("grupo") or "",
                          "stem": Path(X["cfg"]["arquivo"]).stem}
                try:
                    yield k, str(spec["b"]).format(**campos), campos
                except (KeyError, IndexError):
                    continue
        else:
            yield spec.get("a"), spec.get("b"), {"id": spec.get("a") or "", "item": "", "replica": ""}

    def _ressalvas_inline(self, rs, onde):
        """lista de {texto, sev} a partir de ressalvas escritas junto do objeto ao qual se aplicam."""
        out = []
        for r in as_list(rs):
            n = self._ressalva(r, onde)
            if n:
                out.append({"texto": n["texto"], "sev": n["sev"]})
        return out

    def _ressalva(self, r, onde=""):
        if isinstance(r, str):
            r = {"texto": r}
        if not isinstance(r, dict) or not str(r.get("texto") or "").strip():
            self.aviso(self.T["av_ressalva"])
            return None
        sev = str(r.get("severidade") or r.get("sev") or "warn").lower()
        sev = {"info": "info", "informacao": "info", "informação": "info", "aviso": "warn", "warn": "warn", "warning": "warn", "atencao": "warn",
               "atenção": "warn", "bad": "bad", "erro": "bad", "error": "bad", "grave": "bad", "critico": "bad", "crítico": "bad"}.get(sev, "warn")
        return {"id": r.get("id"), "texto": str(r["texto"]).strip(), "sev": sev, "secoes": as_list(r.get("secoes")),
                "estruturas": as_list(r.get("estruturas")), "onde": onde}

    # -------------------------------------------------------------- erro de força por átomo e validação
    def coletar_forcas(self):
        cfg = self.cfg.get("forcas")
        if not cfg:
            return None
        if isinstance(cfg, list):
            cfg = {"pares": cfg}
        pcts = [float(x) for x in as_list(cfg.get("piores_pct")) or [5, 10]]
        tol = float(cfg.get("tol_geom", 0.02))
        out = {"pares": [], "piores_pct": pcts}
        usados = set()
        for spec in self._lista("forcas.pares", cfg.get("pares")):
            for a, b, campos in self._expandir_pares(spec):
                ident = str(spec["id"]).format(**campos) if spec.get("id") else f"{a}_x_{b}"
                try:
                    r = self._par_forcas(ident, a, b, spec, campos, pcts, tol, usados)
                except Exception as ex:  # noqa: BLE001
                    self.aviso(f"{ident}: {type(ex).__name__}: {str(self.tr(ex))[:200]}")
                    continue
                if r:
                    out["pares"].append(r)
        for spec in self._lista("forcas.precalculado", cfg.get("precalculado")):
            ident = str(spec.get("id") or spec.get("estrutura") or "pre")
            try:
                r = self._forcas_precalculadas(ident, spec, pcts, usados)
            except Exception as ex:  # noqa: BLE001
                self.aviso(self.T["av_forca_json"].format(ident, f"{type(ex).__name__}: {str(ex)[:160]}"))
                continue
            if r:
                out["pares"].append(r)
        return out if out["pares"] else None

    def _rotulos_atomo(self, X):
        j = X["json"]
        comps = j.get("comps") or []
        por_el = list(j["el"])
        por_comp = [comps[c]["nome"] if 0 <= c < len(comps) else "—" for c in j["comp"]] if comps else None
        ctx = X["ctx"]
        por_mol = None
        if 2 <= len(ctx.mols) <= 8:                 # por molécula (conectividade) quando não há classes de componente
            por_mol = [None] * len(j["el"])
            for k, m in enumerate(ctx.mols):
                for i in m:
                    por_mol[i] = f"{k + 1} · {ctx.formulas[k]}"
        return por_el, por_comp, {c["nome"]: c["cor"] for c in comps}, por_mol

    def _atribuir_df(self, ident, X, eps, rotulo, usados, spec):
        j = X["json"]
        if j["id"] in usados:
            self.aviso(self.T["av_forca_dup"].format(ident, j["id"]))
            return
        usados.add(j["id"])
        j["dF"] = ints(eps, 1000)                   # meV/Å por átomo
        j["dF_rot"] = rotulo

    def _par_forcas(self, ident, a, b, spec, campos, pcts, tol, usados):
        if not a or not b:
            self.aviso(self.T["av_forca_def"].format(ident))
            return None
        for k in (a, b):
            if k not in self.est:
                self.aviso(self.T["av_forca_ausente"].format(ident, k))
                return None
        XA, XB = self.est[a], self.est[b]
        qa, qb = XA["fin_q"], XB["fin_q"]
        for k, q in ((a, qa), (b, qb)):
            if q.get("F") is None:
                self.aviso(self.T["av_forca_sem"].format(ident, k))
                return None
        if len(qa["simbolos"]) != len(qb["simbolos"]) or list(qa["simbolos"]) != list(qb["simbolos"]):
            self.aviso(self.T["av_forca_n"].format(ident, a, b))
            return None
        pa, pb = np.asarray(qa["pos"], float), np.asarray(qb["pos"], float)
        if qa["celula"] is not None and qb["celula"] is not None:
            C = np.asarray(qb["celula"], float)
            d = (pa - pb) @ np.linalg.inv(C)
            d = (d - np.rint(d)) @ C
        else:
            d = (pa - pa.mean(0)) - (pb - pb.mean(0))
        desvio = float(np.linalg.norm(d, axis=1).max())
        if desvio > tol:
            self.aviso(self.T["av_forca_geom"].format(ident, a, b, desvio, tol))
            return None
        E = erro_forcas(qa["F"], qb["F"])
        por_el, por_comp, cores, por_mol = self._rotulos_atomo(XA)
        elementos = agregar_grupos(E["dF"], por_el)
        componentes = agregar_grupos(E["dF"], por_comp) if por_comp and len(set(por_comp)) > 1 else None
        moleculas = agregar_grupos(E["dF"], por_mol) if por_mol and not componentes else None
        if componentes:
            for k in componentes:
                componentes[k]["cor"] = cores.get(k)
        tensao = erro_tensao(qa["S"], qb["S"]) if qa.get("S") is not None and qb.get("S") is not None and len(qa["S"]) == len(qb["S"]) else None
        ra = spec.get("rotulo_a") or XA["json"]["nome"]
        rb = spec.get("rotulo_b") or XB["json"]["nome"]
        nome = (spec.get("nome") or "{a} × {b}").format(a=ra, b=rb, **{k: v for k, v in campos.items() if k not in ("a", "b")})
        sistema = (spec.get("sistema") or "{item}").format(**campos) if spec.get("sistema") or campos.get("item") else XA["json"]["nome"]
        for X in (XA, XB):
            self._atribuir_df(ident, X, E["eps"], f"{ra} × {rb}", usados, spec)
        return {"id": ident, "nome": nome, "sistema": sistema, "grupo": spec.get("grupo") or XA["json"].get("grupo"),
                "a": a, "b": b, "rotulo_a": ra, "rotulo_b": rb, "n": len(qa["simbolos"]), "origem": "forcas",
                "mae": E["mae"] * 1000, "max_comp": E["max_comp"] * 1000, "rmse": E["rmse"] * 1000,
                "media_atomo": E["media_atomo"] * 1000, "max_atomo": E["max_atomo"] * 1000, "mae_tipo": "componentes",
                "elementos": {k: dict(v, mae=v["mae"] * 1000, media_atomo=v["media_atomo"] * 1000) for k, v in elementos.items()},
                "componentes": None if not componentes else {k: dict(v, mae=v["mae"] * 1000, media_atomo=v["media_atomo"] * 1000) for k, v in componentes.items()},
                "moleculas": None if not moleculas else {k: dict(v, mae=v["mae"] * 1000, media_atomo=v["media_atomo"] * 1000) for k, v in moleculas.items()},
                "conc": concentracao(E["eps"], pcts), "tensao": tensao, "dev_geom": desvio,
                "selo_a": XA["selo"], "selo_b": XB["selo"], "ressalvas": self._ressalvas_inline(spec.get("ressalvas"), ident)}

    def _forcas_precalculadas(self, ident, spec, pcts, usados):
        X = self.est.get(spec.get("estrutura"))
        if X is None:
            self.aviso(self.T["av_forca_ausente"].format(ident, spec.get("estrutura")))
            return None
        d = json.loads(self.caminho(spec["json"]).read_text(encoding="utf-8"))
        for k in str(spec.get("caminho", "")).split("."):
            if k:
                d = d[int(k)] if isinstance(d, list) else d[k]
        f = 0.001 if str(spec.get("unidade", "eV/Å")).lower().startswith("mev") else 1.0
        eps = np.asarray(d, float).ravel() * f
        n = len(X["json"]["el"])
        if len(eps) != n:
            self.aviso(self.T["av_forca_json_n"].format(ident, len(eps), X["json"]["id"], n))
            return None
        por_el, por_comp, cores, por_mol = self._rotulos_atomo(X)
        elementos = agregar_grupos(eps, por_el)
        componentes = agregar_grupos(eps, por_comp) if por_comp and len(set(por_comp)) > 1 else None
        moleculas = agregar_grupos(eps, por_mol) if por_mol and not componentes else None
        if componentes:
            for k in componentes:
                componentes[k]["cor"] = cores.get(k)
        ra, rb = spec.get("rotulo_a") or "A", spec.get("rotulo_b") or "B"
        self._atribuir_df(ident, X, eps, f"{ra} × {rb}", usados, spec)
        selo = self.selo({"programa": None, "versao": None, "nivel": {}}, spec.get("nivel")) if spec.get("nivel") else self.T["declarado_cfg"]
        return {"id": ident, "nome": spec.get("nome") or f"{ra} × {rb}", "sistema": spec.get("sistema") or X["json"]["nome"],
                "grupo": spec.get("grupo") or X["json"].get("grupo"), "a": X["json"]["id"], "b": None, "rotulo_a": ra, "rotulo_b": rb,
                "n": n, "origem": "precalculado", "mae": float(eps.mean()) * 1000, "max_comp": None, "rmse": None,
                "media_atomo": float(eps.mean()) * 1000, "max_atomo": float(eps.max()) * 1000, "mae_tipo": "atomo",
                "elementos": {k: dict(v, mae=None, media_atomo=v["media_atomo"] * 1000) for k, v in elementos.items()},
                "componentes": None if not componentes else {k: dict(v, mae=None, media_atomo=v["media_atomo"] * 1000) for k, v in componentes.items()},
                "moleculas": None if not moleculas else {k: dict(v, mae=None, media_atomo=v["media_atomo"] * 1000) for k, v in moleculas.items()},
                "conc": concentracao(eps, pcts), "tensao": None, "dev_geom": None, "selo_a": selo, "selo_b": selo,
                "ressalvas": self._ressalvas_inline(spec.get("ressalvas"), ident)}

    def coletar_validacao(self, forc, rel):
        cfg = self.cfg.get("validacao") or {}
        cfg = cfg if isinstance(cfg, dict) else {}
        if not (forc or rel):
            return None
        padrao = {"forca_mae": {"limites": [30, 50, 100]}}
        rotulos_pad = self.T["faixas_padrao"]
        bandas = {}
        for k in ("forca_mae", "forca_max", "tensao_mae", "energia_max"):
            b = (cfg.get("bandas") or {}).get(k) or padrao.get(k)
            if not b:
                continue
            lim = [float(x) for x in b.get("limites") or []]
            if not lim or lim != sorted(lim):
                self.aviso(self.T["av_cfg_tipo"].format(f"validacao.bandas.{k}.limites"))
                continue
            rot = b.get("rotulos") or (rotulos_pad if len(lim) == 3 else [f"≤ {x:g}" for x in lim] + [f"> {lim[-1]:g}"])
            bandas[k] = {"limites": lim, "rotulos": [str(x) for x in rot][:len(lim) + 1], "unidade": b.get("unidade") or {
                "forca_mae": "meV/Å", "forca_max": "meV/Å", "tensao_mae": "GPa", "energia_max": "kJ/mol"}[k],
                "padrao": not (cfg.get("bandas") or {}).get(k)}
        def faixa_de(chave, v, fator=1.0):
            b = bandas.get(chave)
            return None if (b is None or v is None) else faixa(v * fator, b["limites"])
        sistemas = []
        for r in (forc or {"pares": []})["pares"]:
            t = r["tensao"]
            sistemas.append({"id": r["id"], "nome": r["nome"], "sistema": r["sistema"], "n": r["n"], "mae": r["mae"], "max_comp": r["max_comp"],
                             "mae_tipo": r["mae_tipo"], "media_atomo": r["media_atomo"], "faixa_mae": faixa_de("forca_mae", r["mae"]),
                             "faixa_max": faixa_de("forca_max", r["max_comp"]),
                             "tensao": None if not t else {"mae": t["mae"], "max": t["max"], "faixa": faixa_de("tensao_mae", t["mae"])},
                             "componentes": r["componentes"], "moleculas": r["moleculas"], "elementos": r["elementos"], "conc": r["conc"], "rotulo_a": r["rotulo_a"],
                             "rotulo_b": r["rotulo_b"], "ressalvas": r["ressalvas"], "grupo": r["grupo"]})
        energia = []
        for c in (rel or []):
            m = c["metricas"]
            if m.get("max_abs") is None:
                continue
            fk = UNID_EV.get(str(bandas.get("energia_max", {}).get("unidade", "kJ/mol")).lower(), 1 / EV_KJ)
            energia.append({"id": c["id"], "titulo": c["titulo"], "mae": m["mae"], "max_abs": m["max_abs"], "faixa": faixa_de("energia_max", m["max_abs"], 1 / fk),
                            "n": m["n"], "menor_difere": m["menor_difere"], "ressalvas": c["ressalvas"]})
        if not sistemas and not energia:
            return None
        return {"titulo": cfg.get("titulo"), "nota": cfg.get("nota"), "bandas": bandas, "sistemas": sistemas, "energia": energia,
                "ressalvas": self._ressalvas_inline(cfg.get("ressalvas"), "validacao")}

    # -------------------------------------------------------------- energia relativa entre dois métodos
    def coletar_relativa(self):
        out = []
        for k, cfg in enumerate(self._lista("comparacao_energia", self.cfg.get("comparacao_energia"))):
            ident = str(cfg.get("id") or f"cmp{k + 1}")
            itens = []
            fonte = []
            for it in self._lista("comparacao_energia.itens", cfg.get("itens")):
                fonte.append(it)
            for spec in self._lista("comparacao_energia.itens_de", cfg.get("itens_de")):
                for a, b, campos in self._expandir_pares(spec):
                    fonte.append({"rotulo": str(spec.get("rotulo") or "{id}").format(**campos), "a": a, "b": b, "est": a})
            if not fonte:
                self.aviso(self.T["av_cmp_def"].format(ident))
                continue
            aviso_n = []
            for it in fonte:
                rot = str(it.get("rotulo") or it.get("a") or "?")
                out_t = {"digitados": []}
                try:
                    Ea, sa = self._termo(rot, self._com_fu(it.get("a"), cfg), out_t)
                    Eb, sb = self._termo(rot, self._com_fu(it.get("b"), cfg), out_t)
                except Exception as ex:  # noqa: BLE001
                    self.aviso(self.T["av_cmp_item"].format(ident, rot, self.tr(ex)))
                    continue
                itens.append({"rotulo": rot, "a": Ea, "b": Eb, "sa": sa, "sb": sb, "est": it.get("est") or (it.get("a") if isinstance(it.get("a"), str) and it.get("a") in self.est else None)})
                aviso_n += out_t["digitados"]
            if len(itens) < 2:
                self.aviso(self.T["av_cmp_poucos"].format(ident))
                continue
            rots = [i["rotulo"] for i in itens]
            ref = cfg.get("referencia")
            if ref is None or str(ref) not in rots:
                if ref is not None:
                    self.aviso(self.T["av_cmp_ref"].format(ident, ref, rots[0]))
                ref = rots[0]
            ri = rots.index(str(ref))
            M = energia_relativa(rots, [i["a"] for i in itens], [i["b"] for i in itens], ri)
            for q, i in enumerate(itens):
                i["da"], i["db"] = M["da"][q], M["db"][q]
            m = {kk: vv for kk, vv in M.items() if kk not in ("da", "db")}
            m["menor_a"], m["menor_b"] = rots[M["menor_a"]], rots[M["menor_b"]]
            sela = sorted({i["sa"] for i in itens})
            selb = sorted({i["sb"] for i in itens})
            for lado, ss in (("A", sela), ("B", selb)):
                if len(ss) > 1:
                    self.aviso(self.T["av_mistura"].format(cfg.get("titulo") or ident, lado, " | ".join(ss)))
            out.append({"id": ident, "titulo": cfg.get("titulo") or ident, "rotulo_a": cfg.get("rotulo_a") or "A", "rotulo_b": cfg.get("rotulo_b") or "B",
                        "ref": str(ref), "itens": [{kk: vv for kk, vv in i.items() if kk not in ("sa", "sb")} for i in itens], "metricas": m,
                        "selos_a": sela, "selos_b": selb, "nota": cfg.get("nota"), "rotulo_por": cfg.get("por"),
                        "digitados": aviso_n, "ressalvas": self._ressalvas_inline(cfg.get("ressalvas"), ident)})
        return out

    @staticmethod
    def _com_fu(t, cfg):
        if isinstance(t, str):
            t = {"estrutura": t}
        if isinstance(t, dict) and cfg.get("por_fu") and "estrutura" in t:
            t = dict(t, por_fu=True)
        return t

    # -------------------------------------------------------------- regras de decisão
    def _grandeza(self, rid, nome, g, vals, forc, rel):
        """valor de uma grandeza da regra na sua unidade declarada: (valor, unidade, fonte, digitado)."""
        if isinstance(g, (int, float)):
            g = {"valor": g}
        un = g.get("unidade")
        fator = UNID_EV.get(str(un).lower()) if un else None
        if "expr" in g:
            return calc_expr(g["expr"], vals), un, g.get("fonte"), False
        if "valor" in g:
            return float(g["valor"]), un, g.get("fonte") or self.T["digitado"], True
        if "estrutura" in g:
            X = self.est.get(g["estrutura"])
            if X is None or X["E"] is None:
                raise ValueError(self.T["av_sem_energia"].format(g["estrutura"]))
            ev = X["E"] / (X["json"]["n_fu"] if g.get("por_fu") else 1)
            f = fator or 1.0
            return ev / f, un or "eV", g.get("fonte") or X["selo"], False
        if "json" in g:
            d = json.loads(self.caminho(g["json"]).read_text(encoding="utf-8"))
            for k in str(g.get("caminho", "")).split("."):
                if k:
                    d = d[int(k)] if isinstance(d, list) else d[k]
            return float(d), un, g.get("fonte") or Path(g["json"]).name, False
        if "comparacao" in g:
            cid, _, campo = str(g["comparacao"]).partition(".")
            c = next((x for x in (rel or []) if x["id"] == cid), None)
            v = None if c is None else c["metricas"].get(campo or "max_abs")
            if v is None:
                raise ValueError(f"comparacao {g['comparacao']}")
            if campo in ("mae", "max_abs", "rms", "vies", "mae_centrado", ""):
                return v / (fator or 1.0), un or "eV", g.get("fonte") or c["titulo"], False
            return float(v), un, g.get("fonte") or c["titulo"], False
        if "forcas" in g:
            fid, _, campo = str(g["forcas"]).partition(".")
            r = next((x for x in ((forc or {}).get("pares") or []) if x["id"] == fid), None)
            v = None if r is None else r.get(campo or "mae")
            if v is None:
                raise ValueError(f"forcas {g['forcas']}")
            return float(v), un or "meV/Å", g.get("fonte") or r["nome"], False
        raise ValueError(self.T["av_termo_tipo"])

    def _resolver_grandezas(self, rid, defs, forc, rel):
        """avalia as grandezas na ordem de dependência; devolve ({nome: dict}, {nome: valor}, [faltam])."""
        vals, info, erros = {}, {}, {}
        pend = dict(defs)
        while pend:
            prog = False
            for nome, g in list(pend.items()):
                gg = {"valor": g} if isinstance(g, (int, float)) else (g or {})
                if "expr" in gg:
                    try:
                        deps = nomes_expr(gg["expr"])
                    except Exception as ex:  # noqa: BLE001
                        erros[nome] = f"{type(ex).__name__}: {ex}"
                        pend.pop(nome)
                        prog = True
                        continue
                    if any(d in pend for d in deps) or any(d not in defs for d in deps):
                        if any(d not in defs for d in deps):
                            erros[nome] = ", ".join(d for d in deps if d not in defs)
                            pend.pop(nome)
                            prog = True
                        continue
                    if any(d in erros for d in deps):
                        erros[nome] = ", ".join(d for d in deps if d in erros)
                        pend.pop(nome)
                        prog = True
                        continue
                try:
                    v, un, fonte, dig = self._grandeza(rid, nome, gg, vals, forc, rel)
                    vals[nome] = v
                    info[nome] = {"id": nome, "nome": gg.get("nome") or nome, "valor": v, "unidade": un,
                                  "fator_ev": UNID_EV.get(str(un).lower()) if un else None, "fonte": fonte, "expr": gg.get("expr"),
                                  "explicacao": gg.get("explicacao"), "digitado": dig}
                except Exception as ex:  # noqa: BLE001
                    erros[nome] = str(self.tr(ex))[:160]
                pend.pop(nome)
                prog = True
            if not prog:
                for n in pend:
                    erros[n] = "?"
                break
        return info, vals, erros

    def _veredito(self, outs, T, vals):
        """primeiro resultado cuja condição vale (um resultado sem `quando` vale sempre); margem até o limiar mais próximo."""
        escolhido = None
        v2 = dict(vals, T=T)
        for k, o in enumerate(outs):
            q = o.get("quando")
            try:
                if q is None or avaliar(q, v2):
                    escolhido = k
                    break
            except Exception:  # noqa: BLE001
                continue
        marg = None
        for k, o in enumerate(outs):
            if not o.get("quando"):
                continue
            for op, L in limiares_condicao(o["quando"], "T", vals):
                d = abs(T - L)
                ok = {"<": T < L, "<=": T <= L, ">": T > L, ">=": T >= L, "==": T == L, "!=": T != L}[op]
                if marg is None or d < marg["valor"]:
                    marg = {"valor": d, "limiar": L, "op": op, "resultado": o["rotulo"], "satisfeito": bool(ok),
                            "relativa": (d / abs(L)) if L else None}
        return escolhido, marg

    def coletar_regras(self, forc, rel):
        out = []
        for k, cfg in enumerate(self._lista("regras", self.cfg.get("regras"))):
            rid = str(cfg.get("id") or f"regra{k + 1}")
            defs = cfg.get("grandezas") or {}
            info, vals, erros = self._resolver_grandezas(rid, defs, forc, rel)
            for n, e in erros.items():
                self.aviso(self.T["av_regra_gr"].format(rid, n, e))
            est = cfg.get("estatistica")
            est = {"expr": est} if isinstance(est, str) else (est or {})
            outs = []
            for q, o in enumerate(cfg.get("resultados") or []):
                sev = str(o.get("severidade") or "warn").lower()
                sev = {"ok": "ok", "bom": "ok", "good": "ok", "warn": "warn", "aviso": "warn", "bad": "bad", "ruim": "bad", "erro": "bad", "info": "info"}.get(sev, "warn")
                outs.append({"id": o.get("id") or f"r{q + 1}", "rotulo": o.get("rotulo") or o.get("id") or f"r{q + 1}", "quando": o.get("quando"),
                             "sev": sev, "texto": o.get("texto")})
            T = None
            faltam = sorted(erros)
            if est.get("expr"):
                try:
                    if all(n in vals for n in nomes_expr(est["expr"])):
                        T = calc_expr(est["expr"], vals)
                    else:
                        faltam = sorted(set(faltam) | {n for n in nomes_expr(est["expr"]) if n not in vals})
                except Exception as ex:  # noqa: BLE001
                    self.aviso(self.T["av_regra_expr"].format(rid, self.tr(ex)))
            un_t = est.get("unidade")
            res = marg = None
            if T is not None:
                esc, marg = self._veredito(outs, T, vals)
                res = None if esc is None else {kk: vv for kk, vv in outs[esc].items() if kk != "quando"}
            elif est.get("expr"):
                self.aviso(self.T["av_regra_sem"].format(rid, ", ".join(faltam) or "?"))
            sens = []
            for alt in self._lista("regras.sensibilidade", cfg.get("sensibilidade")):
                dd = dict(defs)
                dd.update(alt.get("grandezas") or {})
                i2, v2, e2 = self._resolver_grandezas(rid, dd, forc, rel)
                ex2 = (alt.get("estatistica") if isinstance(alt.get("estatistica"), str) else (alt.get("estatistica") or {}).get("expr")) or est.get("expr")
                T2 = r2 = m2 = None
                try:
                    if ex2 and all(n in v2 for n in nomes_expr(ex2)):
                        T2 = calc_expr(ex2, v2)
                        e_, m2 = self._veredito(outs, T2, v2)
                        r2 = None if e_ is None else {kk: vv for kk, vv in outs[e_].items() if kk != "quando"}
                except Exception as ex:  # noqa: BLE001
                    self.aviso(self.T["av_regra_expr"].format(rid, self.tr(ex)))
                sens.append({"rotulo": alt.get("rotulo") or "?", "explicacao": alt.get("explicacao"), "T": T2, "resultado": r2, "margem": m2,
                             "grandezas": {n: i2[n]["valor"] for n in (alt.get("grandezas") or {}) if n in i2}})
            pre = cfg.get("pre_registrada")
            if pre is False and not sens:
                self.aviso(self.T["av_regra_pos"].format(rid))
            muda = len({(s["resultado"] or {}).get("id") for s in sens if s["resultado"]} | ({res["id"]} if res else set())) > 1
            out.append({"id": rid, "titulo": cfg.get("titulo") or rid, "pergunta": cfg.get("pergunta"), "pre_registrada": pre,
                        "grandezas": [info[n] for n in defs if n in info], "faltam": faltam if T is None else [],
                        "estatistica": {"nome": est.get("nome") or "T", "expr": est.get("expr"), "valor": T, "unidade": un_t,
                                        "fator_ev": UNID_EV.get(str(un_t).lower()) if un_t else None, "casas": est.get("casas", 2)},
                        "resultado": res, "margem": marg, "resultados": [{kk: vv for kk, vv in o.items()} for o in outs],
                        "sensibilidade": sens, "veredito_muda": bool(muda and sens), "nota": cfg.get("nota"),
                        "ressalvas": self._ressalvas_inline(cfg.get("ressalvas"), rid)})
        return out

    # -------------------------------------------------------------- ressalvas globais (por seção ou estrutura)
    def coletar_ressalvas(self):
        out = []
        for r in self._lista("ressalvas", self.cfg.get("ressalvas")):
            n = self._ressalva(r)
            if not n:
                continue
            for alvo in n["estruturas"]:
                alvos = [k for k, X in self.est.items() if k == alvo or X["json"]["grupo"] == alvo]
                if not alvos:
                    self.aviso(self.T["av_ressalva_alvo"].format(n["id"] or n["texto"][:30], alvo))
                for k in alvos:
                    self.est[k]["json"].setdefault("rs", []).append({"texto": n["texto"], "sev": n["sev"]})
            out.append({"id": n["id"], "texto": n["texto"], "sev": n["sev"], "secoes": n["secoes"], "estruturas": n["estruturas"]})
        for k, X in self.est.items():                  # ressalvas escritas junto da estrutura
            rs = self._ressalvas_inline(X["cfg"].get("ressalvas"), k)
            if rs:
                X["json"].setdefault("rs", []).extend(rs)
        return out

    # -------------------------------------------------------------- métodos
    def coletar_metodos(self):
        grupos = {}
        for rot, R, dec in self.usados:
            niv = (R or {}).get("nivel") or {}
            chave = (R.get("programa"), R.get("versao"), niv.get("metodo"), niv.get("base"), str(dec))
            g = grupos.setdefault(chave, {"R": R, "dec": dec, "usos": []})
            if rot not in g["usos"]:
                g["usos"].append(rot)
        cards = []
        T = self.T
        for (prog, ver, met, base, _), g in grupos.items():
            R, niv = g["R"], g["R"].get("nivel") or {}
            dec = g["dec"] if isinstance(g["dec"], dict) else ({"nivel": g["dec"]} if g["dec"] else {})
            campos = [[T["m_nivel"], self.nz(met or dec.get("nivel")) + ("" if met else (f" ({T['declarado']})" if dec.get("nivel") else ""))]]
            for k, rot in (("funcional", T["m_funcional"]), ("base", T["m_base"]), ("dispersao", T["m_dispersao"]),
                           ("corte", T["m_corte"]), ("pseudo", T["m_pseudo"]), ("scf", T["m_scf"]), ("linha", T["m_linha"]),
                           ("hessiana", T["m_hessiana"]), ("tarefa", T["m_tarefa"]), ("modelo", T["m_modelo"])):
                if niv.get(k) and niv.get(k) != met:
                    campos.append([rot, str(niv[k])])
            campos.append([T["m_programa"], (f"{prog or dec.get('programa') or T['nao_registrado']} " + (ver or dec.get("versao") or f"({T['versao_nr']})")).strip()])
            c = R.get("scf_criterio")
            campos.append([T["m_crit_scf"], f"{c['nome']} = {c['valor']:g}" + (f" — {self.tr(c['nota'])}" if c.get("nota") else "") if c and c.get("valor") is not None else T["nao_registrado"]])
            oc = R.get("opt_criterio")
            if oc:
                campos.append([T["m_crit_opt"], f"{oc['nome']} ≤ {oc['valor_EhBohr']:g} Eh/bohr ({oc['valor_eVA']:.3f} eV/Å)"])
            if R.get("carga") is not None:
                campos.append([T["m_carga"], f"{R['carga']} / {R.get('mult')}"])
            campos.append([T["m_usado"], ", ".join(g["usos"][:12]) + (" …" if len(g["usos"]) > 12 else "")])
            titulo = f"{prog or dec.get('programa') or T['programa_nr']}" + (f" {ver}" if ver else "")
            cards.append({"titulo": titulo, "selo": self.selo(R, g["dec"]), "campos": campos, "classe": L.classe_programa(prog or dec.get("programa"))})
        for m in self.cfg.get("metodos") or []:
            campos = m.get("campos") or {}
            campos = [[k, v] for k, v in campos.items()] if isinstance(campos, dict) else campos
            cards.append({"titulo": m.get("titulo", ""), "selo": m.get("selo") or T["declarado_cfg"], "campos": campos, "classe": None, "declarado": True})
        maq = self.cfg.get("maquina")
        return {"cards": cards, "maquina": maq}

    # -------------------------------------------------------------- tudo
    def montar(self):
        t0 = time.time()
        self.coletar_estruturas()
        forc = self.coletar_forcas()
        rel = self.coletar_relativa()
        val = self.coletar_validacao(forc, rel)
        regras = self.coletar_regras(forc, rel)
        ressalvas = self.coletar_ressalvas()
        filmes, omit = self.coletar_filmes()
        fila, metas = self.coletar_fila()
        etapas = self.coletar_etapas(fila)
        reac = self.cfg.get("reacao") or {}
        if not reac:
            reac = {"reagentes": [k for k, X in self.est.items() if X["cfg"].get("papel") == "reagente"],
                    "produtos": [k for k, X in self.est.items() if X["cfg"].get("papel") == "produto"],
                    "ts": [k for k, X in self.est.items() if X["cfg"].get("papel") in ("ts", "estado_de_transicao")]}
        reac = {k: [x for x in as_list(reac.get(k)) if x in self.est] for k in ("reagentes", "produtos", "ts")}
        gl = [list(x) for x in (GLOSSARIO[self.lang if self.lang in GLOSSARIO else "pt"] if self.cfg.get("glossario_padrao", True) else [])]
        for t, d in (self.cfg.get("glossario") or {}).items() if isinstance(self.cfg.get("glossario"), dict) else [(x[0], x[1]) for x in self.cfg.get("glossario") or []]:
            gl = [g for g in gl if g[0] != t] + [[t, d]]
        D = {
            "meta": {"titulo": self.cfg.get("titulo") or self.T["titulo_padrao"], "subtitulo": self.cfg.get("subtitulo"),
                     "lang": self.lang, "gerado": time.strftime("%d/%m/%Y %H:%M:%S" if self.lang == "pt" else "%Y-%m-%d %H:%M:%S"),
                     "recarga_s": int(self.cfg.get("recarga_s", 120)), "unidade": unid_cod(self.cfg.get("unidade", "kJ/mol")),
                     "versao": __import__("painel_lib").__version__, "rotulo": self.cfg.get("rotulo"), "id": self.cfg.get("id") or slug(self.cfg.get("titulo") or "painel"),
                     "secoes": self.cfg.get("secoes"), "textos": self.cfg.get("textos") or {}},
            "etapas": etapas, "andamento": self.coletar_andamento(filmes),
            "est": [X["json"] for X in self.est.values()], "reacao": reac,
            "filmes": filmes, "filmes_omitidos": omit,
            "energia": self.coletar_energia(), "ranking": self.coletar_ranking(), "valid": val, "relativa": rel, "regras": regras,
            "ressalvas": ressalvas, "medidas": self.coletar_medidas(),
            "freq": self.coletar_freq(), "fila": fila, "fila_meta": metas,
            "glossario": gl,
        }
        D["metodos"] = self.coletar_metodos()
        D["avisos"] = self.avisos
        D["meta"]["tempo_s"] = round(time.time() - t0, 1)
        return D


# ----------------------------------------------------------------------------------------------------------
# funções auxiliares
# ----------------------------------------------------------------------------------------------------------
def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def ints(x, escala):
    return np.rint(np.asarray(x, float) * escala).astype(int).ravel().tolist()


def cel_list(c):
    return None if c is None else [round(float(v), 5) for v in np.asarray(c).ravel()]


def cellpar(c):
    if c is None:
        return None
    C = np.asarray(c, float)
    l = np.linalg.norm(C, axis=1)
    ang = lambda i, j: math.degrees(math.acos(max(-1, min(1, C[i] @ C[j] / l[i] / l[j]))))  # noqa: E731
    return [round(float(x), 5) for x in (l[0], l[1], l[2], ang(1, 2), ang(0, 2), ang(0, 1))]


def amostrar(n, maximo):
    if n <= maximo:
        return list(range(n))
    return sorted(set(int(round(k * (n - 1) / (maximo - 1))) for k in range(maximo)))


def quando(ts):
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(ts))


def rel(p, base):
    try:
        return os.path.relpath(str(p), str(base))
    except Exception:
        return str(p)


def slug(t):
    return re.sub(r"[^a-z0-9]+", "_", t.lower())[:40] or "painel"


def unid_cod(u):
    u = str(u).lower()
    return "kcal" if "kcal" in u else ("ev" if u == "ev" else "kj")


def estimar_eta_etapa(itens, total, feito, rodando, paralelo=1):
    """tempo restante: (cálculos que faltam) × (duração mediana medida) / paralelo; sem ritmo medido -> None."""
    if not total or feito >= total:
        return None
    durs = [x[3] for x in itens if x[0] == "concluido" and x[3]]
    base = "duracao"
    if not durs:
        fins = sorted(x[2] for x in itens if x[0] == "concluido" and x[2])
        if len(fins) >= 2:
            durs = [(fins[-1] - fins[0]) / (len(fins) - 1) * max(1, paralelo)]
            base = "intervalo"
    if not durs:
        return None
    med = statistics.median(durs)
    falta = total - feito
    agora = time.time()
    decorrido = [agora - x[1] for x in itens if x[0] == "rodando" and x[1]]
    resto = falta * med
    if decorrido:
        resto -= min(med, decorrido[0])
    resto = max(0.0, resto) / max(1, paralelo)
    return {"s": resto, "mediana_s": med, "n": len(durs) if base == "duracao" else None, "base": base}


def estimar_eta_scf(scf, crit, decorrido_s=None):
    """s/iteração (coluna de tempo ou decorrido/n) e iterações até o critério por ajuste log-linear da convergência."""
    if not scf:
        return None
    ts = [r[4] for r in scf if len(r) > 4 and r[4]]
    spi = statistics.mean(ts[-5:]) if ts else ((decorrido_s / len(scf)) if decorrido_s else None)
    alvo = (crit or {}).get("valor")
    conv = [(r[0], r[3]) for r in scf if len(r) > 3 and r[3] and r[3] > 0]
    out = {"spi": spi}
    if not conv or not alvo:
        return out
    if conv[-1][1] <= alvo:
        out["convergiu"] = True
        return out
    est = []
    for k in (4, 8):
        pts = conv[-k:]
        if len(pts) < 3:
            continue
        x = np.array([q[0] for q in pts], float)
        y = np.log10([q[1] for q in pts])
        m = np.polyfit(x, y, 1)[0]
        if m < -0.01:
            est.append((math.log10(alvo) - y[-1]) / m)
    if est:
        out.update({"iter_min": min(est), "iter_max": max(est)})
        if spi:
            out.update({"s_min": min(est) * spi, "s_max": max(est) * spi})
    return out


def validar_freq(freqs, ref):
    modos = ref.get("modos") if isinstance(ref, dict) else ref
    linhas = []
    pos = [f for f in freqs if f > 0]
    for r in modos or []:
        v = float(r.get("valor", r.get("exp")))
        if r.get("calc") is not None:                # pareamento dado pela própria tabela de referência
            c = float(r["calc"])
        elif not pos:
            break
        else:
            c = min(pos, key=lambda f: abs(f - v))
        linhas.append({"rotulo": r.get("rotulo"), "ref": v, "calc": c, "dif": c - v})
    if not linhas:
        return None
    d = [abs(x["dif"]) for x in linhas]
    return {"fonte": ref.get("fonte") if isinstance(ref, dict) else None, "linhas": linhas, "mae": float(np.mean(d)), "max": float(np.max(d)),
            "tol": ref.get("tolerancia", [30, 80]) if isinstance(ref, dict) else [30, 80]}


def comparar_freq(fa, fb, acima=300):
    a = [f for f in fa if f > acima]
    b = [f for f in fb if f > acima]
    if not a or not b:
        return {"mae": None, "n": 0}
    pares = [(f, min(b, key=lambda q: abs(q - f))) for f in a]
    d = [abs(x - y) for x, y in pares]
    return {"mae": float(np.mean(d)), "max": float(np.max(d)), "n": len(pares), "acima_de": acima,
            "pares": [[round(x, 1), round(y, 1)] for x, y in pares]}
