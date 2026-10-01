"""Leitores de saídas de programas de estrutura eletrônica / simulação atomística.

Todo leitor devolve um dicionário `Resultado` com as MESMAS chaves (ver references/formato-dados.md):

  arquivo, programa, versao, nivel (dict), tipo, estado, avisos, energia_eV, quadros, scf, scf_criterio,
  scf_convergiu, n_ciclos_scf, freq, inicio, fim, duracao_s, mtime, carga, mult, convergiu, opt_criterio

Um campo que o arquivo não fornece fica None (nunca é inventado). Um leitor que falha levanta exceção; quem chama
(`ler`) a converte num Resultado com estado "ilegivel" e um aviso — a geração do painel nunca quebra por isso.
"""
import json
import re
import time
from pathlib import Path

import numpy as np

HA_EV = 27.211386245988
RY_EV = HA_EV / 2
BOHR_A = 0.529177210903
HA_BOHR_EVA = HA_EV / BOHR_A
KJMOL_POR_CM1 = 0.011962656
EV_POR_KJMOL = 1 / 96.48533212

PROGRAMAS_MLIP = ("fairchem", "uma", "mace", "chgnet", "m3gnet", "matgl", "sevenn", "orb", "nequip", "allegro", "mattersim",
                  "ani", "aimnet", "grace", "petmad", "pet-mad")


# ----------------------------------------------------------------------------------------------------------
# estrutura comum
# ----------------------------------------------------------------------------------------------------------
def novo(arquivo, programa=None):
    p = Path(arquivo)
    try:
        mt = p.stat().st_mtime
    except OSError:
        mt = None
    return {"arquivo": str(arquivo), "programa": programa, "versao": None, "nivel": {}, "tipo": None,
            "estado": "desconhecido", "avisos": [], "energia_eV": None, "quadros": [], "scf": [], "scf_criterio": None,
            "scf_convergiu": None, "n_ciclos_scf": 0, "freq": None, "inicio": None, "fim": None, "duracao_s": None,
            "mtime": mt, "carga": None, "mult": None, "convergiu": None, "opt_criterio": None, "extra": {}}


def quadro(simbolos, pos, celula=None, E_eV=None, fmax=None, sigma_GPa=None, t=None, pbc=None):
    pos = np.asarray(pos, float).reshape(-1, 3)
    cel = None if celula is None else np.asarray(celula, float).reshape(3, 3)
    if cel is not None and abs(np.linalg.det(cel)) < 1e-6:
        cel = None
    return {"simbolos": list(simbolos), "pos": pos, "celula": cel, "pbc": bool(cel is not None) if pbc is None else bool(pbc),
            "E_eV": None if E_eV is None else float(E_eV), "fmax": None if fmax is None else float(fmax),
            "sigma_GPa": None if sigma_GPa is None else float(sigma_GPa), "t": t}


def classe_programa(prog):
    p = (prog or "").lower()
    if any(k in p for k in PROGRAMAS_MLIP):
        return "MLIP"
    if any(k in p for k in ("orca", "cp2k", "vasp", "gaussian", "quantum espresso", "pwscf", "psi4", "pyscf", "turbomole",
                            "nwchem", "q-chem", "molpro", "fhi-aims", "siesta", "gpaw", "abinit", "castep", "crystal")):
        return "QM"
    if any(k in p for k in ("xtb", "dftb", "mopac")):
        return "semiempírico"
    if any(k in p for k in ("emt", "lennard", "lj", "lammps", "gulp", "uff")):
        return "clássico"
    return None


def _zpe(freqs, excluir):
    f = np.asarray(freqs, float)
    resto = f[np.argsort(np.abs(f))][excluir:]
    return float(0.5 * resto[resto > 0].sum() * KJMOL_POR_CM1)


def montar_freq(freqs, modos=None, simbolos=None, pos=None, idx=None, celula=None, excluir=None, limiar_imag=-20.0):
    """frequências em ordem crescente (imaginárias negativas); modos normalizados a 1 sobre os átomos deslocados."""
    f = np.asarray(freqs, float)
    ordem = np.argsort(f)
    f = f[ordem]
    M = None
    if modos is not None:
        M = np.asarray(modos, float)[ordem]
        n = np.linalg.norm(M.reshape(len(M), -1), axis=1)
        M = M / np.where(n > 0, n, 1.0)[:, None, None]
    nat = len(simbolos) if simbolos else (M.shape[1] if M is not None else 0)
    if excluir is None:
        excluir = int(sum(1 for x in f if abs(x) < 1e-3))
    return {"freqs_cm1": [round(float(x), 2) for x in f], "modos": None if M is None else np.round(M, 4).tolist(),
            "simbolos": list(simbolos or []), "pos": None if pos is None else np.round(np.asarray(pos, float), 4).tolist(),
            "idx": list(range(nat)) if idx is None else [int(i) for i in idx],
            "celula": None if celula is None else np.round(np.asarray(celula, float), 4).tolist(),
            "n_imag": int((f < limiar_imag).sum()), "zpe_kJmol": round(_zpe(f, excluir), 3) if len(f) else None}


def texto(p, limite=None):
    with open(p, "rb") as fh:
        b = fh.read() if limite is None else fh.read(limite)
    return b.decode("utf-8", "replace")


def _f(x):
    try:
        return float(str(x).replace("D", "E").replace("d", "e"))
    except Exception:
        return None


def _dur(d=0, h=0, m=0, s=0.0):
    return int(d) * 86400 + int(h) * 3600 + int(m) * 60 + float(s)


def _max_forca(forcas):
    if forcas is None:
        return None
    F = np.asarray(forcas, float).reshape(-1, 3)
    return float(np.sqrt((F ** 2).sum(1)).max()) if len(F) else None


# ----------------------------------------------------------------------------------------------------------
# xyz multiquadro (ORCA _trj.xyz, CP2K -pos-1.xyz, xyz simples) — leitura própria, tolerante ao comentário
# ----------------------------------------------------------------------------------------------------------
def ler_xyz_quadros(p, unidade_E="Ha"):
    linhas = texto(p).splitlines()
    i, out = 0, []
    fat = {"Ha": HA_EV, "eV": 1.0, "Ry": RY_EV}.get(unidade_E, 1.0)
    while i < len(linhas):
        t = linhas[i].strip()
        if not t:
            i += 1
            continue
        n = int(t)
        com = linhas[i + 1] if i + 1 < len(linhas) else ""
        sim, pos = [], []
        for ln in linhas[i + 2:i + 2 + n]:
            q = ln.split()
            sim.append(re.sub(r"\d+$", "", q[0]))
            pos.append([float(x) for x in q[1:4]])
        if len(sim) < n:
            break
        m = re.search(r"\bE\s*=?\s*(-?\d+\.\d+)", com)
        out.append(quadro(sim, pos, E_eV=float(m.group(1)) * fat if m else None))
        i += 2 + n
    return out


# ----------------------------------------------------------------------------------------------------------
# ORCA
# ----------------------------------------------------------------------------------------------------------
PALAVRAS_TAREFA_ORCA = {"opt", "freq", "numfreq", "anfreq", "tightscf", "verytightscf", "normalscf", "loosescf", "sp",
                        "tightopt", "verytightopt", "looseopt", "optts", "scanTS".lower(), "irc", "neb", "neb-ts", "md",
                        "printbasis", "miniprint", "smallprint", "normalprint", "largeprint", "slowconv", "veryslowconv",
                        "kdiis", "soscf", "nososcf", "defgrid1", "defgrid2", "defgrid3", "rijcosx", "rij", "nofrozencore",
                        "frozencore", "pal2", "pal4", "pal6", "pal8", "pal16", "uks", "rks", "uhf", "rhf", "engrad",
                        "moread", "noautostart", "autoaux", "nmr", "keepdens", "xyzfile", "pdbfile"}


def ler_orca(p):
    R = novo(p, "ORCA")
    t = texto(p)
    m = re.search(r"Program Version (\d[\w.]*)", t)
    R["versao"] = m.group(1) if m else None
    linhas_bang = [x.strip() for x in re.findall(r"^\|\s*\d+>\s*(!.*)$", t, re.M)]
    palavras = " ".join(l.lstrip("!").strip() for l in linhas_bang).split()
    nivel = [w for w in palavras if w.lower() not in PALAVRAS_TAREFA_ORCA and not re.match(r"pal\d+", w.lower())]
    tarefas = [w for w in palavras if w.lower() in PALAVRAS_TAREFA_ORCA]
    if linhas_bang:
        R["nivel"] = {"metodo": " ".join(nivel) or None, "linha": " ".join(linhas_bang)}
    lw = [w.lower() for w in tarefas]
    R["tipo"] = "opt" if any(w.startswith("opt") or w.endswith("opt") for w in lw) else ("freq" if any("freq" in w for w in lw) else "sp")
    if any("freq" in w for w in lw) and R["tipo"] == "opt":
        R["tipo"] = "opt+freq"
    m = re.search(r"Total Charge\s+Charge\s+\.+\s+(-?\d+)", t)
    R["carga"] = int(m.group(1)) if m else None
    m = re.search(r"Multiplicity\s+Mult\s+\.+\s+(\d+)", t)
    R["mult"] = int(m.group(1)) if m else None
    # tolerâncias do SCF (último bloco)
    tolE = re.findall(r"Energy Change\s+TolE\s+\.+\s+([\d.eE+-]+)", t)
    tolP = re.findall(r"RMS Density Change\s+TolRMSP\s+\.+\s+([\d.eE+-]+)", t)
    if tolE:
        R["scf_criterio"] = {"nome": "TolE", "valor": _f(tolE[-1]), "coluna": "|ΔE| (Eh)",
                             "nota": "o ORCA exige também TolRMSP/TolMaxP; o gráfico mostra |ΔE| contra TolE"
                             + (f" e RMS-DP contra TolRMSP = {tolP[-1]}" if tolP else "")}
        if tolP:
            R["extra"]["tolRMSP"] = _f(tolP[-1])
    # geometrias e energias por ciclo
    blocos = re.split(r"GEOMETRY OPTIMIZATION CYCLE\s+\d+", t)
    geos = []
    for m in re.finditer(r"CARTESIAN COORDINATES \(ANGSTROEM\)\n-+\n(.*?)\n\s*\n", t, re.S):
        sim, pos = [], []
        for ln in m.group(1).splitlines():
            q = ln.split()
            if len(q) >= 4:
                sim.append(q[0])
                pos.append([float(x) for x in q[1:4]])
        geos.append((m.start(), sim, pos))
    ens = [(m.start(), float(m.group(1))) for m in re.finditer(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", t)]
    grads = [(m.start(), float(m.group(1))) for m in re.finditer(r"^\s*MAX gradient\s+(\d+\.\d+)\s+\d", t, re.M)]
    tols = re.findall(r"^\s*MAX gradient\s+\d+\.\d+\s+(\d+\.\d+)", t, re.M)
    if tols:
        R["opt_criterio"] = {"nome": "MAX gradient", "valor_EhBohr": float(tols[-1]), "valor_eVA": float(tols[-1]) * HA_BOHR_EVA}
    for k, (pos0, sim, pos) in enumerate(geos):
        fim = geos[k + 1][0] if k + 1 < len(geos) else len(t)
        E = next((e for (q, e) in ens if pos0 < q < fim), None)
        g = next((g for (q, g) in grads if pos0 < q < fim), None)
        R["quadros"].append(quadro(sim, pos, E_eV=None if E is None else E * HA_EV, fmax=None if g is None else g * HA_BOHR_EVA))
    # o último bloco de coordenadas costuma repetir a geometria final (após "HAS CONVERGED"): remove duplicata sem energia
    if len(R["quadros"]) >= 2 and R["quadros"][-1]["E_eV"] is None and np.allclose(R["quadros"][-1]["pos"], R["quadros"][-2]["pos"], atol=1e-6):
        R["quadros"].pop()
    if ens:
        R["energia_eV"] = ens[-1][1] * HA_EV
    R["extra"]["n_ciclos_opt"] = len(blocos) - 1
    # SCF: último bloco de iterações
    scf_blocos = re.split(r"\n(?=-+D-I-I-S-+|\s*SCF ITERATIONS)", t)
    ultimo = None
    for b in scf_blocos[1:]:
        it = []
        for m in re.finditer(r"^\s{0,6}(\d+)\s+(-?\d+\.\d+)\s+(-?[\d.]+[eE][+-]?\d+)\s+([\d.]+[eE][+-]?\d+)\s+([\d.]+[eE][+-]?\d+)(.*)$", b, re.M):
            resto = m.group(6).split()
            tt = _f(resto[-1]) if resto else None
            it.append({"it": int(m.group(1)), "E": float(m.group(2)), "dE": float(m.group(3)), "conv": abs(float(m.group(3))),
                       "rmsdp": float(m.group(4)), "t_s": tt})
            if "SCF CONVERGED" in b[m.end():m.end() + 400] or "SUCCESS" in b[m.end():m.end() + 300]:
                pass
        if it:
            ultimo = it
            R["n_ciclos_scf"] += 1
    if ultimo:
        R["scf"] = ultimo
        R["scf_unidade_E"] = "Eh"
    nconv = len(re.findall(r"SCF CONVERGED AFTER", t))
    R["scf_convergiu"] = bool(nconv) and nconv >= R["n_ciclos_scf"] if R["n_ciclos_scf"] else (True if nconv else None)
    if re.search(r"SCF NOT CONVERGED", t):
        R["scf_convergiu"] = False
    # otimização
    if "opt" in (R["tipo"] or ""):
        if re.search(r"THE OPTIMIZATION HAS CONVERGED", t):
            R["convergiu"] = True
        elif re.search(r"did not converge but reached the maximum number", t):
            R["convergiu"] = False
    # tempo e término
    m = re.search(r"TOTAL RUN TIME:\s+(\d+) days (\d+) hours (\d+) minutes (\d+) seconds (\d+) msec", t)
    if m:
        R["duracao_s"] = _dur(m.group(1), m.group(2), m.group(3), int(m.group(4)) + int(m.group(5)) / 1000)
    if "ORCA TERMINATED NORMALLY" in t:
        R["estado"] = "concluido"
        R["fim"] = R["mtime"]
        if R["duracao_s"] and R["mtime"]:
            R["inicio"] = R["mtime"] - R["duracao_s"]
    elif re.search(r"ORCA finished by error termination|aborting the run|ABORTING THE RUN|ERROR !!!", t):
        R["estado"] = "falhou"
    else:
        R["estado"] = "rodando?"
    # frequências (.hess ao lado tem prioridade para os modos)
    if "VIBRATIONAL FREQUENCIES" in t:
        R["freq"] = _orca_freq(p, t, R)
    # trajetória _trj.xyz (quadros mais leves; usa se existir e tiver mais quadros que o .out)
    trj = Path(p).with_name(Path(p).stem + "_trj.xyz")
    if trj.exists():
        try:
            q = ler_xyz_quadros(trj, "Ha")
            if len(q) > len(R["quadros"]):
                R["extra"]["notas"] = [f"quadros lidos de {trj.name}"]
                R["quadros"] = q
        except Exception as e:  # noqa: BLE001
            R["avisos"].append(f"{trj.name} ilegível: {e}")
    return R


def _bloco_hess(t, nome):
    m = re.search(r"^\$" + re.escape(nome) + r"[ \t]*\n(.*?)(?=^\$|\Z)", t, re.S | re.M)
    return None if m is None else m.group(1).strip("\n").split("\n")


def _matriz_hess(linhas):
    n, m = (int(x) for x in linhas[0].split()[:2])
    M = np.zeros((n, m))
    cols = None
    for ln in linhas[1:]:
        q = ln.split()
        if not q or q[0].startswith("#"):
            continue
        if "." not in ln:
            cols = [int(x) for x in q]
            continue
        r = int(q[0])
        for c, v in zip(cols, q[1:]):
            M[r, c] = float(v)
    return M


def ler_orca_hess(p):
    """`.hess` do ORCA: átomos (bohr), frequências e modos normais."""
    R = novo(p, "ORCA")
    t = texto(p)
    at = _bloco_hess(t, "atoms")
    n = int(at[0])
    sim, pos = [], []
    for ln in at[1:1 + n]:
        q = ln.split()
        sim.append(q[0])
        pos.append([float(x) * BOHR_A for x in q[2:5]])
    fh = _bloco_hess(t, "vibrational_frequencies")
    freqs = [float(ln.split()[1]) for ln in fh[1:1 + int(fh[0])]] if fh else []
    V = _matriz_hess(_bloco_hess(t, "normal_modes"))
    modos = V.T.reshape(V.shape[1], n, 3)
    R["freq"] = montar_freq(freqs, modos, sim, pos)
    R["quadros"].append(quadro(sim, pos))
    R["tipo"] = "freq"
    R["estado"] = "concluido"
    m = re.search(r"\$actual_temperature", t)
    R["extra"]["hess"] = bool(m) or True
    return R


def _orca_freq(p, t, R):
    hess = Path(p).with_suffix(".hess")
    if hess.exists():
        try:
            H = ler_orca_hess(hess)
            fr = H["freq"]
            m = re.search(r"VIBRATIONAL FREQUENCIES\n-+\n(.*?)(?:\n\s*\n\s*-+\n|NORMAL MODES)", t, re.S)
            if m:
                f_out = [float(x) for x in re.findall(r"^\s*\d+:\s+(-?\d+\.\d+)\s+cm", m.group(1), re.M)]
                if len(f_out) == len(fr["freqs_cm1"]) and not np.allclose(sorted(f_out), fr["freqs_cm1"], atol=0.05):
                    R["avisos"].append("frequências do .out e do .hess discordam; usando as do .hess")
            return fr
        except Exception as e:  # noqa: BLE001
            R["avisos"].append(f"{hess.name} ilegível ({e}); só as frequências do .out")
    m = list(re.finditer(r"VIBRATIONAL FREQUENCIES\n-+\n(.*?)(?:\n\s*\n\s*-+\n|NORMAL MODES)", t, re.S))[-1]
    f_out = [float(x) for x in re.findall(r"^\s*\d+:\s+(-?\d+\.\d+)\s+cm", m.group(1), re.M)]
    q = R["quadros"][-1] if R["quadros"] else None
    modos = None
    mm = re.search(r"NORMAL MODES\n-+\n.*?\n\s*\n(.*?)\n\s*\n\s*-{5,}", t, re.S)
    if mm and q is not None:
        try:
            n3 = 3 * len(q["simbolos"])
            M = np.zeros((n3, n3))
            cols = None
            for ln in mm.group(1).splitlines():
                parts = ln.split()
                if not parts:
                    continue
                if all(re.fullmatch(r"\d+", x) for x in parts):
                    cols = [int(x) for x in parts]
                    continue
                r = int(parts[0])
                for c, v in zip(cols, parts[1:]):
                    M[r, c] = float(v)
            modos = M.T.reshape(n3, len(q["simbolos"]), 3)
        except Exception:
            modos = None
    return montar_freq(f_out, modos, q["simbolos"] if q else None, q["pos"] if q else None)


# ----------------------------------------------------------------------------------------------------------
# CP2K
# ----------------------------------------------------------------------------------------------------------
def _cp2k_data(s):
    try:
        return time.mktime(time.strptime(s.split(".")[0], "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return None


def ler_cp2k(p):
    R = novo(p, "CP2K")
    t = texto(p)
    m = re.search(r"CP2K\|\s+version string:\s+(.+)", t)
    R["versao"] = re.sub(r"^CP2K version\s*", "", m.group(1).strip()) if m else None
    m = re.search(r"GLOBAL\|\s+Run type\s+(\S+)", t)
    rt = m.group(1) if m else None
    R["tipo"] = {"ENERGY": "sp", "ENERGY_FORCE": "sp", "GEO_OPT": "opt", "CELL_OPT": "opt-celula", "MD": "md",
                 "VIBRATIONAL_ANALYSIS": "freq"}.get(rt, (rt or "").lower() or None)
    m = re.search(r"GLOBAL\|\s+Project name\s+(\S+)", t)
    proj = m.group(1) if m else None
    func = []
    for x in re.findall(r"FUNCTIONAL\|\s+([\w\-+()]+):", t):
        if x not in func:
            func.append(x)
    disp = "DFT-D3(BJ)" if re.search(r"DFT-D3\(BJ\)", t) else ("DFT-D3" if re.search(r"DFT-D3", t) else ("DFT-D2" if "DFT-D2" in t else None))
    bases = []
    for x in re.findall(r"Orbital Basis Set\s+(\S+)", t):
        if x not in bases:
            bases.append(x)
    pots = []
    for v in re.findall(r"Potential information for\s+(\S+)", t):
        if v and v not in pots:
            pots.append(v)
    m = re.search(r"QS\|\s+Density cutoff \[a\.u\.\]:\s+([\d.]+)", t)
    corte = f"{float(m.group(1)) * 2:.0f} Ry" if m else None
    m = re.search(r"eps_scf:\s+([\d.E+-]+)", t)
    eps = _f(m.group(1)) if m else None
    ot = bool(re.search(r"\bOT\b", t) and re.search(r"OT DIIS|OT CG|OT LS|OT SD", t))
    R["nivel"] = {"funcional": "+".join(func) or None, "dispersao": disp, "base": ", ".join(bases) or None,
                  "pseudo": ", ".join(pots[:3]) or None, "corte": corte, "scf": "OT" if ot else ("diagonalização" if "Diag." in t else None)}
    if not func:                                   # nível de impressão baixo: tenta o .inp ao lado (marcado)
        inp = next((x for x in (Path(p).with_suffix(".inp"), Path(p).with_name(f"{proj}.inp") if proj else None) if x and x.exists()), None)
        if inp is not None:
            ti = texto(inp)
            g = lambda pat: (re.search(pat, ti, re.I | re.M).group(1) if re.search(pat, ti, re.I | re.M) else None)  # noqa: E731
            f_inp = g(r"&XC_FUNCTIONAL\s+(\w+)") or g(r"^\s*&(PBE|BLYP|B3LYP|PBE0|SCAN|R2SCAN|TPSS|HSE06)\b")
            v_inp = g(r"^\s*TYPE\s+(DFTD3(?:\(BJ\))?|DFTD2|DFTD4)") or (g(r"^\s*POTENTIAL_TYPE\s+(\w+)") if "VDW_POTENTIAL" in ti.upper() else None)
            b_inp = sorted(set(re.findall(r"^\s*BASIS_SET\s+(?:ORB\s+)?(\S+)", ti, re.I | re.M)))
            c_inp = g(r"^\s*CUTOFF\s+([\d.]+)")
            R["nivel"].update({"funcional": f_inp, "dispersao": v_inp, "base": ", ".join(b_inp) or None,
                               "corte": f"{float(c_inp):.0f} Ry" if c_inp else R["nivel"]["corte"], "fonte": f"lido de {inp.name}"})
            R["extra"]["notas"] = R["extra"].get("notas", []) + [f"nível lido de {inp.name} (a saída não o imprime)"]
            if eps is None and g(r"^\s*EPS_SCF\s+([\d.Ee+-]+)"):
                eps = _f(g(r"^\s*EPS_SCF\s+([\d.Ee+-]+)"))
    R["nivel"]["metodo"] = " ".join(x for x in (R["nivel"]["funcional"], R["nivel"]["dispersao"]) if x) or None
    if eps is not None:
        R["scf_criterio"] = {"nome": "EPS_SCF", "valor": eps, "coluna": "Convergence",
                             "nota": "compare a coluna Convergence do CP2K com EPS_SCF (não o ΔE da última coluna)"}
    m = re.search(r"PROGRAM STARTED AT\s+(\S+ \S+)", t)
    R["inicio"] = _cp2k_data(m.group(1)) if m else None
    m = re.search(r"PROGRAM ENDED AT\s+(\S+ \S+)", t)
    R["fim"] = _cp2k_data(m.group(1)) if m else None
    if R["inicio"] and R["fim"]:
        R["duracao_s"] = R["fim"] - R["inicio"]
    m = re.search(r"DFT\|\s+Charge\s+(-?\d+)", t)
    R["carga"] = int(m.group(1)) if m else None
    m = re.search(r"DFT\|\s+Multiplicity\s+(\d+)", t)
    R["mult"] = int(m.group(1)) if m else None
    # SCF: blocos "Step Update method Time Convergence Total energy Change"
    partes = re.split(r"\n\s*Step\s+Update method\s+Time\s+Convergence\s+Total energy\s+Change\s*\n\s*-+\s*\n", t)
    ultimo = None
    for b in partes[1:]:
        it = []
        for ln in b.splitlines():
            q = ln.split()
            if not q or not q[0].isdigit():
                if it and (ln.strip().startswith("***") or "outer SCF" in ln or ln.strip().startswith("Leaving") or not ln.strip()):
                    break
                continue
            nums = []
            for x in q[1:]:
                v = _f(x)
                if v is not None and re.match(r"^-?[\d.]+(E[+-]\d+)?$", x):
                    nums.append(v)
            if len(nums) >= 5:
                it.append({"it": int(q[0]), "t_s": nums[-4], "conv": nums[-3], "E": nums[-2], "dE": nums[-1]})
            elif len(nums) >= 3:
                it.append({"it": int(q[0]), "t_s": nums[1], "conv": None, "E": nums[-1], "dE": None})
        if it:
            ultimo = it
            R["n_ciclos_scf"] += 1
    if ultimo:
        R["scf"] = ultimo
        R["scf_unidade_E"] = "Ha"
    conv_n = len(re.findall(r"SCF run converged in", t))
    if re.search(r"SCF run NOT converged", t):
        R["scf_convergiu"] = False
    elif conv_n:
        R["scf_convergiu"] = conv_n >= R["n_ciclos_scf"]
    ens = [float(x) for x in re.findall(r"ENERGY\|\s+Total FORCE_EVAL \( \w+ \) energy \[[^\]]+\]:\s+(-?\d+\.\d+)", t)]
    if ens:
        R["energia_eV"] = ens[-1] * HA_EV
    # geometria inicial
    sim, pos = [], []
    k0 = t.find("ATOMIC COORDINATES IN ANGSTROM")
    if k0 < 0:
        k0 = t.find("ATOMIC COORDINATES IN angstrom")
    if k0 >= 0:
        for ln in t[k0:k0 + 200 * 4000].splitlines()[1:]:
            q = ln.split()
            if len(q) >= 7 and q[0].isdigit() and q[1].isdigit():
                sim.append(re.sub(r"\d+$", "", q[2]))
                pos.append([float(x) for x in q[4:7]])
            elif sim and not ln.strip():
                break
    cel = []
    for ax in "abc":
        mm = re.search(rf"CELL\|\s+Vector {ax} \[angstrom\]:\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)", t)
        if mm:
            cel.append([float(mm.group(i)) for i in (1, 2, 3)])
    celula = np.array(cel) if len(cel) == 3 else None
    grads = [float(x) * HA_BOHR_EVA for x in re.findall(r"Max\. gradient\s+=\s+([\d.E+-]+)", t)]
    m = re.search(r"Conv\. limit for gradients\s+=\s+([\d.E+-]+)", t)
    if m:
        R["opt_criterio"] = {"nome": "MAX_FORCE", "valor_EhBohr": _f(m.group(1)), "valor_eVA": _f(m.group(1)) * HA_BOHR_EVA}
    pos_xyz = None
    if proj:
        cands = sorted(Path(p).parent.glob(f"{proj}-pos-*.xyz"))
        pos_xyz = cands[0] if cands else None
    if pos_xyz is not None:
        try:
            q = ler_xyz_quadros(pos_xyz, "Ha")
            for k, x in enumerate(q):
                x["celula"] = celula
                x["pbc"] = celula is not None
                if k < len(grads):
                    x["fmax"] = grads[k] if k else None
            R["quadros"] = q
            R["extra"]["notas"] = R["extra"].get("notas", []) + [f"quadros lidos de {pos_xyz.name}"]
        except Exception as e:  # noqa: BLE001
            R["avisos"].append(f"{pos_xyz.name} ilegível: {e}")
    if not R["quadros"] and sim:
        R["quadros"].append(quadro(sim, pos, celula, E_eV=ens[0] * HA_EV if ens else None))
        if len(ens) == 1 and R["tipo"] == "sp":
            R["quadros"][-1]["E_eV"] = ens[0] * HA_EV
    if re.search(r"GEOMETRY OPTIMIZATION COMPLETED", t):
        R["convergiu"] = True
    elif re.search(r"MAXIMUM NUMBER OF OPTIMIZATION STEPS REACHED", t):
        R["convergiu"] = False
    if "PROGRAM ENDED AT" in t:
        R["estado"] = "concluido"
        if R["scf_convergiu"] is False:
            R["estado"] = "falhou"
            R["avisos"].append("SCF não convergiu (SCF run NOT converged)")
    elif re.search(r"\bABORT\b|\*\*\* ERROR|CPASSERT failed", t):
        R["estado"] = "falhou"
    else:
        R["estado"] = "rodando?"
    # VIBRATIONS .mol ao lado
    if proj:
        mol = sorted(Path(p).parent.glob(f"{proj}-VIBRATIONS-*.mol"))
        if mol:
            try:
                R["freq"] = ler_cp2k_molden(mol[0])["freq"]
            except Exception as e:  # noqa: BLE001
                R["avisos"].append(f"{mol[0].name} ilegível: {e}")
    return R


def ler_cp2k_molden(p):
    """`<proj>-VIBRATIONS-1.mol` (Molden): [FREQ], [FR-COORD] (bohr), [FR-NORM-COORD]."""
    R = novo(p, "CP2K")
    sec, freqs, sim, pos, modos, atual = None, [], [], [], [], None
    for ln in texto(p).splitlines():
        t = ln.strip()
        if t.startswith("["):
            sec = t.split("]")[0].upper() + "]"
            continue
        if not t:
            continue
        if sec == "[FREQ]":
            freqs.append(float(t.split()[0]))
        elif sec == "[FR-COORD]":
            q = t.split()
            sim.append(q[0])
            pos.append([float(x) * BOHR_A for x in q[1:4]])
        elif sec == "[FR-NORM-COORD]":
            if t.lower().startswith("vibration"):
                atual = []
                modos.append(atual)
            else:
                atual.append([float(x) for x in t.split()[:3]])
    if not freqs or len(freqs) != len(modos):
        raise ValueError("Molden sem [FREQ]/[FR-NORM-COORD] consistentes")
    M = np.array(modos)
    idx = [i for i in range(M.shape[1]) if np.abs(M[:, i, :]).max() > 1e-8]
    R["freq"] = montar_freq(freqs, M[:, idx, :], sim, pos, idx)
    R["quadros"].append(quadro(sim, pos))
    R["tipo"] = "freq"
    R["estado"] = "concluido"
    R["extra"]["parcial"] = len(idx) < M.shape[1]
    return R


# ----------------------------------------------------------------------------------------------------------
# VASP (OUTCAR, OSZICAR, vasprun.xml)
# ----------------------------------------------------------------------------------------------------------
def ler_vasp_outcar(p):
    R = novo(p, "VASP")
    t = texto(p)
    m = re.search(r"^\s*vasp\.(\S+)", t, re.M)
    R["versao"] = m.group(1) if m else None
    def par(nome):
        mm = re.search(rf"^\s*{nome}\s*=\s*([^\s;]+)", t, re.M)
        return mm.group(1) if mm else None
    gga, mgga, encut, ediff, ibrion, isif, ivdw = (par(x) for x in ("GGA", "METAGGA", "ENCUT", "EDIFF", "IBRION", "ISIF", "IVDW"))
    potcar = []
    for x in re.findall(r"POTCAR:\s+(\S+\s+\S+)", t):
        if x not in potcar:
            potcar.append(x)
    gmap = {"PE": "PBE", "PS": "PBEsol", "RP": "RPBE", "91": "PW91", "--": None, "CA": "LDA", "MK": "optB86b?", "BO": "optB86b", "OR": "optPBE"}
    func = (mgga if mgga and mgga not in ("--", "F") else None) or gmap.get(gga, gga)
    dmap = {"10": "DFT-D2", "11": "DFT-D3(0)", "12": "DFT-D3(BJ)", "2": "TS", "20": "TS", "21": "TS/HI", "4": "dDsC", "202": "MBD"}
    R["nivel"] = {"funcional": func, "dispersao": dmap.get(ivdw) if ivdw and ivdw != "0" else None,
                  "corte": f"{_f(encut):.0f} eV" if encut and _f(encut) else None, "pseudo": ", ".join(potcar[:4]) or None}
    R["nivel"]["metodo"] = " ".join(x for x in (R["nivel"]["funcional"], R["nivel"]["dispersao"]) if x) or None
    ib = int(_f(ibrion)) if ibrion and _f(ibrion) is not None else None
    R["tipo"] = {-1: "sp", 0: "md", 1: "opt", 2: "opt", 3: "opt", 5: "freq", 6: "freq", 7: "freq", 8: "freq"}.get(ib)
    if R["tipo"] == "opt" and isif and isif in ("3", "4", "5", "6", "7"):
        R["tipo"] = "opt-celula"
    if ediff:
        R["scf_criterio"] = {"nome": "EDIFF", "valor": _f(ediff), "coluna": "|dE| (eV)", "nota": "o VASP compara a variação de energia entre iterações eletrônicas com EDIFF"}
    # elementos
    el = re.findall(r"VRHFIN\s*=\s*([A-Za-z]+)\s*:", t)
    m = re.search(r"ions per type\s*=\s*([\d\s]+)", t)
    nper = [int(x) for x in m.group(1).split()] if m else []
    if not el:
        el = [x.split()[1].split("_")[0] for x in potcar[:len(nper)]]
    sim = [e for e, n in zip(el, nper) for _ in range(n)]
    cels = [np.array([[float(x) for x in ln.split()[:3]] for ln in m.group(1).strip().splitlines()[:3]])
            for m in re.finditer(r"direct lattice vectors.*?\n((?:.*\n){3})", t)]
    ens = [float(x) for x in re.findall(r"energy\(sigma->0\)\s*=\s*(-?\d+\.\d+)", t)] or \
          [float(x) for x in re.findall(r"free\s+energy\s+TOTEN\s*=\s*(-?\d+\.\d+)", t)]
    stresses = [[float(x) for x in m.group(1).split()[:6]] for m in re.finditer(r"^\s*in kB\s+(.*)$", t, re.M)]
    for k, m in enumerate(re.finditer(r"POSITION\s+TOTAL-FORCE \(eV/Angst\)\s*\n\s*-+\n(.*?)\n\s*-+", t, re.S)):
        rows = [[float(x) for x in ln.split()[:6]] for ln in m.group(1).strip().splitlines()]
        A = np.array(rows)
        cel = cels[min(k + 1, len(cels) - 1)] if cels else None
        sg = None
        if k < len(stresses):
            sg = float(np.abs(np.array(stresses[k])).max() * 0.1)
        R["quadros"].append(quadro(sim, A[:, :3], cel, E_eV=ens[k] if k < len(ens) else None, fmax=_max_forca(A[:, 3:6]), sigma_GPa=sg))
    if ens:
        R["energia_eV"] = ens[-1]
    m = re.search(r"Elapsed time \(sec\):\s+([\d.]+)", t)
    if m:
        R["duracao_s"] = float(m.group(1))
    if "General timing and accounting" in t:
        R["estado"] = "concluido"
        R["fim"] = R["mtime"]
    elif re.search(r"VERY BAD NEWS|internal error|ZBRENT: fatal", t):
        R["estado"] = "falhou"
    else:
        R["estado"] = "rodando?"
    if R["tipo"] and R["tipo"].startswith("opt"):
        R["convergiu"] = bool(re.search(r"reached required accuracy - stopping structural energy minimisation", t)) or None
    osz = Path(p).with_name("OSZICAR")
    if osz.exists():
        try:
            O = ler_vasp_oszicar(osz)
            R["scf"], R["n_ciclos_scf"], R["scf_unidade_E"] = O["scf"], O["n_ciclos_scf"], "eV"
        except Exception as e:  # noqa: BLE001
            R["avisos"].append(f"OSZICAR ilegível: {e}")
    # frequências (IBRION 5-8)
    if "Eigenvectors and eigenvalues of the dynamical matrix" in t:
        try:
            R["freq"] = _vasp_freq(t, R["quadros"][0] if R["quadros"] else None)
        except Exception as e:  # noqa: BLE001
            R["avisos"].append(f"frequências do OUTCAR ilegíveis: {e}")
    return R


def _vasp_freq(t, q0):
    bloco = t.split("Eigenvectors and eigenvalues of the dynamical matrix")[1]
    bloco = bloco.split("Eigenvectors after division by SQRT(mass)")[0]
    freqs, modos = [], []
    for m in re.finditer(r"^\s*\d+\s+(f|f/i)\s*=.*?(-?[\d.]+)\s+cm-1.*?\n\s*X\s+Y\s+Z\s+dx\s+dy\s+dz\s*\n(.*?)(?:\n\s*\n)", bloco, re.S | re.M):
        f = float(m.group(2)) * (-1 if m.group(1) == "f/i" else 1)
        rows = [[float(x) for x in ln.split()[:6]] for ln in m.group(3).strip().splitlines()]
        freqs.append(f)
        modos.append([r[3:6] for r in rows])
    sim = q0["simbolos"] if q0 else None
    pos = q0["pos"] if q0 else None
    return montar_freq(freqs, modos, sim, pos)


def ler_vasp_oszicar(p):
    R = novo(p, "VASP")
    blocos, atual = [], []
    for ln in texto(p).splitlines():
        m = re.match(r"^\s*(DAV|RMM|CG|SDA|DIA|N):\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)", ln)
        if m and m.group(1) != "N":
            atual.append({"it": int(m.group(2)), "E": _f(m.group(3)), "dE": _f(m.group(4)), "conv": abs(_f(m.group(4)) or 0), "t_s": None})
            continue
        m = re.match(r"^\s*(\d+)\s+F=\s*(\S+)\s+E0=\s*(\S+)", ln)
        if m:
            if atual:
                blocos.append(atual)
            atual = []
            R["quadros"].append(quadro([], np.zeros((0, 3)), E_eV=_f(m.group(3))))
    if atual:
        blocos.append(atual)
    R["scf"] = blocos[-1] if blocos else []
    R["n_ciclos_scf"] = len(blocos)
    R["scf_unidade_E"] = "eV"
    if R["quadros"]:
        R["energia_eV"] = R["quadros"][-1]["E_eV"]
    R["quadros"] = []
    R["estado"] = "rodando?"
    return R


def ler_vasprun(p):
    from ase.io import read
    R = novo(p, "VASP")
    t = texto(p, 200000)
    m = re.search(r'<i name="version"[^>]*>\s*([^<]+)</i>', t)
    R["versao"] = m.group(1).strip() if m else None
    m = re.search(r'<i type="string" name="GGA">\s*([^<]+)</i>', t)
    R["nivel"] = {"funcional": m.group(1).strip() if m else None}
    R["nivel"]["metodo"] = R["nivel"]["funcional"]
    fr = read(p, ":", format="vasp-xml")
    for a in fr:
        _quadro_ase(R, a)
    if R["quadros"]:
        R["energia_eV"] = R["quadros"][-1]["E_eV"]
    full = texto(p)
    R["estado"] = "concluido" if "</modeling>" in full else "rodando?"
    return R


# ----------------------------------------------------------------------------------------------------------
# Gaussian (.log/.out)
# ----------------------------------------------------------------------------------------------------------
NUM_EL = ["X", "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
          "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
          "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd",
          "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
          "Tl", "Pb", "Bi", "Po", "At", "Rn"]


def ler_gaussian(p):
    R = novo(p, "Gaussian")
    t = texto(p)
    m = re.search(r"Gaussian (\d+):\s+(\S+)", t)
    R["versao"] = f"{m.group(1)} ({m.group(2)})" if m else None
    m = re.search(r"\n\s*-+\n\s*(#.*?)\n\s*-+\n", t, re.S)
    rota = " ".join(x.strip() for x in m.group(1).splitlines()) if m else None
    if rota:
        toks = rota.lstrip("#").split()
        lv = [x for x in toks if "/" in x and not x.lower().startswith(("opt", "freq", "scf", "int"))]
        R["nivel"] = {"metodo": lv[0] if lv else None, "linha": rota}
        disp = re.search(r"empiricaldispersion=(\w+)", rota, re.I)
        if disp:
            R["nivel"]["dispersao"] = disp.group(1)
        rl = rota.lower()
        R["tipo"] = ("opt+freq" if "freq" in rl else "opt") if re.search(r"\bopt\b|opt=|opt\(", rl) else ("freq" if "freq" in rl else "sp")
    m = re.search(r"Charge =\s*(-?\d+) Multiplicity =\s*(\d+)", t)
    if m:
        R["carga"], R["mult"] = int(m.group(1)), int(m.group(2))
    # geometrias (Standard orientation, senão Input orientation)
    nome = "Standard orientation:" if "Standard orientation:" in t else "Input orientation:"
    geos = []
    for m in re.finditer(re.escape(nome) + r"\s*\n\s*-+\n.*?\n.*?\n\s*-+\n(.*?)\n\s*-+", t, re.S):
        sim, pos = [], []
        for ln in m.group(1).splitlines():
            q = ln.split()
            sim.append(NUM_EL[int(q[1])] if int(q[1]) < len(NUM_EL) else "X")
            pos.append([float(x) for x in q[3:6]])
        geos.append((m.start(), sim, pos))
    ens = [(m.start(), float(m.group(1))) for m in re.finditer(r"SCF Done:\s+E\(\S+\)\s+=\s+(-?\d+\.\d+)", t)]
    fmx = [(m.start(), float(m.group(1))) for m in re.finditer(r"Maximum Force\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(YES|NO)", t)]
    tf = re.findall(r"Maximum Force\s+\d+\.\d+\s+(\d+\.\d+)", t)
    if tf:
        R["opt_criterio"] = {"nome": "Maximum Force", "valor_EhBohr": float(tf[-1]), "valor_eVA": float(tf[-1]) * HA_BOHR_EVA}
    for k, (q0, sim, pos) in enumerate(geos):
        fim = geos[k + 1][0] if k + 1 < len(geos) else len(t)
        E = next((e for (q, e) in ens if q0 < q < fim), None)
        g = next((g for (q, g) in fmx if q0 < q < fim), None)
        R["quadros"].append(quadro(sim, pos, E_eV=None if E is None else E * HA_EV, fmax=None if g is None else g * HA_BOHR_EVA))
    # freq jobs repetem a geometria final: remove quadros finais sem energia idênticos ao anterior
    while len(R["quadros"]) >= 2 and R["quadros"][-1]["E_eV"] is None:
        R["quadros"].pop()
    if ens:
        R["energia_eV"] = ens[-1][1] * HA_EV
    # SCF (só com #p): linhas " E= -232.1 Delta-E= ..." e "RMSDP=..."
    blocos, atual = [], []
    for ln in t.splitlines():
        if ln.startswith(" Cycle   1 "):
            if atual:
                blocos.append(atual)
            atual = []
        m = re.match(r"^\s*E=\s*(-?\d+\.\d+)\s+Delta-E=\s*(-?\d+\.\d+)", ln)
        if m:
            atual.append({"it": len(atual) + 1, "E": float(m.group(1)), "dE": float(m.group(2)), "conv": None, "t_s": None})
        m = re.match(r"^\s*RMSDP=\s*([\d.D+-]+)", ln)
        if m and atual:
            atual[-1]["conv"] = _f(m.group(1))
    if atual:
        blocos.append(atual)
    if blocos:
        R["scf"], R["n_ciclos_scf"], R["scf_unidade_E"] = blocos[-1], len(blocos), "Eh"
    m = re.search(r"Requested convergence on RMS density matrix=\s*([\d.D+-]+)", t)
    if m:
        R["scf_criterio"] = {"nome": "RMS densidade", "valor": _f(m.group(1)), "coluna": "RMSDP",
                             "nota": "o Gaussian compara a variação RMS da matriz densidade (RMSDP) com o critério pedido"}
    if "Optimization completed" in t or "Stationary point found" in t:
        R["convergiu"] = True
    elif re.search(r"Optimization stopped|Number of steps exceeded", t):
        R["convergiu"] = False
    ds = [_dur(*m.groups()) for m in re.finditer(r"Elapsed time:\s+(\d+) days\s+(\d+) hours\s+(\d+) minutes\s+([\d.]+) seconds", t)]
    if ds:
        R["duracao_s"] = sum(ds)
    if re.search(r"Normal termination of Gaussian", t) and not re.search(r"Error termination", t):
        R["estado"] = "concluido"
        R["fim"] = R["mtime"]
    elif "Error termination" in t:
        R["estado"] = "falhou"
    else:
        R["estado"] = "rodando?"
    if "Frequencies --" in t:
        R["freq"] = _gaussian_freq(t, R["quadros"][-1] if R["quadros"] else None)
    return R


def _gaussian_freq(t, q):
    # usa o último bloco de frequências (se houver HPModes, o bloco padrão de 3 colunas vem depois)
    freqs, modos = [], []
    secoes = re.split(r"\n\s+Harmonic frequencies \(cm\*\*-1\)", t)
    s = secoes[-1]
    for m in re.finditer(r"Frequencies --\s+(.*?)\n(.*?)\n\s+Atom\s+AN\s+X\s+Y\s+Z.*?\n(.*?)(?=\n\s+\d+\s+\d+\s+\d+\s*\n|\n\s*\n|\n\s+\d+\s*\n|\Z)", s, re.S):
        fs = [float(x) for x in m.group(1).split()]
        rows = []
        for ln in m.group(3).splitlines():
            parts = ln.split()
            if len(parts) < 2 + 3 * len(fs) or not parts[0].isdigit():
                break
            rows.append([float(x) for x in parts[2:2 + 3 * len(fs)]])
        if not rows:
            continue
        A = np.array(rows)
        for k, f in enumerate(fs):
            freqs.append(f)
            modos.append(A[:, 3 * k:3 * k + 3])
    if not freqs:
        raise ValueError("bloco de frequências do Gaussian sem modos legíveis")
    return montar_freq(freqs, modos, q["simbolos"] if q else None, q["pos"] if q else None, excluir=0)


# ----------------------------------------------------------------------------------------------------------
# Quantum ESPRESSO (pw.x)
# ----------------------------------------------------------------------------------------------------------
def ler_qe(p):
    R = novo(p, "Quantum ESPRESSO (pw.x)")
    t = texto(p)
    m = re.search(r"Program PWSCF v\.?(\S+) starts on\s+(\S+) at\s+([\d: ]+)", t)
    if m:
        R["versao"] = m.group(1)
        try:
            R["inicio"] = time.mktime(time.strptime(m.group(2) + " " + m.group(3).replace(" ", ""), "%d%b%Y %H:%M:%S"))
        except Exception:
            pass
    m = re.search(r"Exchange-correlation\s*=\s*(\S+)", t)
    func = m.group(1) if m else None
    m = re.search(r"kinetic-energy cutoff\s*=\s*([\d.]+)\s*Ry", t)
    corte = f"{float(m.group(1)):.0f} Ry" if m else None
    m = re.search(r"convergence threshold\s*=\s*([\d.E+-]+)", t)
    thr = _f(m.group(1)) if m else None
    pseudo = []
    for x in re.findall(r"PseudoPot\. #\s*\d+ for\s+\S+\s+read from file:\s*\n?\s*(\S+)", t):
        x = Path(x).name
        if x not in pseudo:
            pseudo.append(x)
    disp = "DFT-D3" if re.search(r"DFT-D3|Grimme-D3", t) else ("DFT-D2" if "DFT-D" in t else None)
    R["nivel"] = {"funcional": func, "dispersao": disp, "corte": corte, "pseudo": ", ".join(pseudo[:4]) or None}
    R["nivel"]["metodo"] = " ".join(x for x in (func, disp) if x) or None
    m = re.search(r"calculation\s*=\s*'?(\w[\w-]*)", t)
    calc = m.group(1) if m else ("relax" if "BFGS Geometry Optimization" in t else ("vc-relax" if "vc-relax" in t else "scf"))
    R["tipo"] = {"scf": "sp", "relax": "opt", "vc-relax": "opt-celula", "md": "md", "vc-md": "md"}.get(calc, calc)
    if thr is not None:
        R["scf_criterio"] = {"nome": "conv_thr", "valor": thr, "coluna": "estimated scf accuracy (Ry)",
                             "nota": "o pw.x compara a 'estimated scf accuracy' com conv_thr"}
    blocos, atual = [], []
    tcpu_ant = pend = None
    for ln in t.splitlines():
        if re.match(r"^\s*iteration #\s*1\s", ln):
            if atual:
                blocos.append(atual)
            atual = []
        m = re.match(r"^\s*total cpu time spent up to now is\s+([\d.]+)", ln)
        if m:
            tc = float(m.group(1))
            pend = None if tcpu_ant is None else round(tc - tcpu_ant, 2)
            tcpu_ant = tc
        m = re.match(r"^\s*total energy\s+=\s+(-?\d+\.\d+)\s+Ry", ln)
        if m:
            atual.append({"it": len(atual) + 1, "E": float(m.group(1)), "dE": None, "conv": None, "t_s": pend})
            pend = None
        m = re.match(r"^\s*estimated scf accuracy\s+<\s+([\d.E+-]+)\s+Ry", ln)
        if m and atual:
            atual[-1]["conv"] = _f(m.group(1))
    if atual:
        blocos.append(atual)
    if blocos:
        R["scf"], R["n_ciclos_scf"], R["scf_unidade_E"] = blocos[-1], len(blocos), "Ry"
        for k in range(1, len(R["scf"])):
            R["scf"][k]["dE"] = R["scf"][k]["E"] - R["scf"][k - 1]["E"]
    ens = [float(x) for x in re.findall(r"^!\s+total energy\s+=\s+(-?\d+\.\d+)\s+Ry", t, re.M)]
    if ens:
        R["energia_eV"] = ens[-1] * RY_EV
    R["scf_convergiu"] = False if "convergence NOT achieved" in t else (True if "convergence has been achieved" in t else None)
    try:
        from ase.io import read
        for a in read(p, ":", format="espresso-out"):
            _quadro_ase(R, a)
    except Exception as e:  # noqa: BLE001
        R["avisos"].append(f"geometrias não lidas pelo ASE (espresso-out): {str(e)[:120]}")
    if R["tipo"] and R["tipo"].startswith("opt"):
        R["convergiu"] = True if re.search(r"End of BFGS Geometry Optimization|bfgs converged", t) else (False if "The maximum number of steps has been reached" in t else None)
    m = re.search(r"PWSCF\s+:\s+(.*?)CPU\s+(.*?)WALL", t)
    if m:
        w = m.group(2)
        hh = re.search(r"(\d+)h", w)
        mm = re.search(r"(\d+)m", w)
        ss = re.search(r"([\d.]+)s", w)
        R["duracao_s"] = _dur(0, hh.group(1) if hh else 0, mm.group(1) if mm else 0, ss.group(1) if ss else 0)
    if "JOB DONE." in t:
        R["estado"] = "concluido"
        R["fim"] = (R["inicio"] + R["duracao_s"]) if R["inicio"] and R["duracao_s"] else R["mtime"]
    elif re.search(r"%%%%%%%%%%%%%|Error in routine", t):
        R["estado"] = "falhou"
    else:
        R["estado"] = "rodando?"
    return R


# ----------------------------------------------------------------------------------------------------------
# ASE (extxyz, traj, cif, POSCAR/CONTCAR, xyz, ...)
# ----------------------------------------------------------------------------------------------------------
CHAVES_INFO_PROG = ("programa", "program", "software", "calculator", "calculador")
CHAVES_INFO_NIVEL = ("nivel", "level", "metodo", "method", "modelo", "model", "funcional", "functional", "tarefa", "task", "base", "basis")


def _quadro_ase(R, a):
    E = fm = sg = None
    try:
        E = float(a.get_potential_energy())
    except Exception:
        E = a.info.get("energy") if isinstance(a.info.get("energy"), (int, float)) else None
    try:
        fm = _max_forca(a.get_forces())
    except Exception:
        fm = None
    try:
        s = a.get_stress(voigt=True)
        sg = float(np.abs(s).max() * 160.21766208)          # eV/Å³ -> GPa
    except Exception:
        sg = None
    cel = np.array(a.cell) if a.cell.rank == 3 else None
    R["quadros"].append(quadro(a.get_chemical_symbols(), a.positions, cel, E_eV=E, fmax=fm, sigma_GPa=sg, pbc=bool(a.pbc.any())))


def ler_ase(p, formato=None):
    from ase.io import read
    R = novo(p, None)
    fr = read(p, ":", format=formato) if formato else read(p, ":")
    if not isinstance(fr, list):
        fr = [fr]
    if not fr:                                     # o ASE adivinhou um formato e não achou nenhuma estrutura: não é "concluído"
        raise ValueError("nenhuma estrutura reconhecida no arquivo")
    for a in fr:
        _quadro_ase(R, a)
    info = dict(fr[-1].info) if fr else {}
    prog = next((str(info[k]) for k in CHAVES_INFO_PROG if k in info), None)
    if prog is None and fr and fr[-1].calc is not None:
        nm = getattr(fr[-1].calc, "name", None)
        if nm and nm.lower() not in ("unknown", "singlepointcalculator", "singlepoint"):
            prog = nm
    R["programa"] = prog
    R["versao"] = next((str(info[k]) for k in ("versao", "version") if k in info), None)
    niv = {k: str(info[k]) for k in CHAVES_INFO_NIVEL if k in info}
    if niv:
        R["nivel"] = niv
        R["nivel"]["metodo"] = " ".join(niv[k] for k in ("modelo", "model", "metodo", "method", "funcional", "functional", "nivel", "level") if k in niv) or None
        if "tarefa" in niv or "task" in niv:
            R["nivel"]["metodo"] = (R["nivel"]["metodo"] or "") + f" (tarefa {niv.get('tarefa') or niv.get('task')})"
    if "convergiu" in info:
        R["convergiu"] = bool(info["convergiu"])
    R["tipo"] = "opt" if len(fr) > 1 else "estrutura"
    R["estado"] = "concluido"
    if R["quadros"]:
        R["energia_eV"] = R["quadros"][-1]["E_eV"]
    return R


# ----------------------------------------------------------------------------------------------------------
# JSON / JSONL genéricos
# ----------------------------------------------------------------------------------------------------------
def ler_jsonl_progresso(p):
    """uma linha por passo: {passo|step, E_eV|energy, fmax_eVA|fmax, sigma_max_GPa|stress, quando|time}; linha final {"fim": true}."""
    recs, fim = [], None
    for ln in texto(p).splitlines():
        try:
            d = json.loads(ln)
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        if d.get("fim") or d.get("end") or d.get("done"):
            fim = d
            continue
        recs.append(d)
    pega = lambda d, *ks: next((d[k] for k in ks if k in d and d[k] is not None), None)  # noqa: E731
    serie = {"passo": [pega(d, "passo", "step") for d in recs], "fase": [pega(d, "fase", "phase") for d in recs],
             "E": [pega(d, "E_eV", "energy_eV", "energia_eV", "energy", "E") for d in recs],
             "fmax": [pega(d, "fmax_eVA", "fmax", "fmax_eV_A") for d in recs],
             "sig": [pega(d, "sigma_max_GPa", "stress_GPa", "sigma_GPa", "stress") for d in recs],
             "quando": [pega(d, "quando", "time", "timestamp") for d in recs], "t_s": [pega(d, "t_s", "elapsed_s") for d in recs]}
    return {"serie": serie, "fim": fim, "n": len(recs)}


def ler_json(p):
    d = json.loads(texto(p))
    R = novo(p, None)
    if isinstance(d, dict) and "freqs_cm1" in d:            # esquema de frequências (references/formato-dados.md)
        m = d.get("metodo") or {}
        R["programa"] = m.get("programa") or m.get("software")
        R["versao"] = m.get("versao") or m.get("version")
        R["nivel"] = {k: v for k, v in m.items() if k not in ("programa", "software", "versao", "version") and v not in (None, "")}
        mod = " ".join(str(m[k]) for k in ("modelo", "metodo", "funcional") if m.get(k))
        if m.get("tarefa"):
            mod += f" (tarefa {m['tarefa']})"
        R["nivel"]["metodo"] = mod or None
        modos = d.get("modos")
        R["freq"] = montar_freq(d["freqs_cm1"], modos, d.get("simbolos"), d.get("posicoes"), d.get("indices_deslocados"), d.get("celula"))
        if d.get("zpe_kJmol") is not None:
            R["freq"]["zpe_kJmol"] = d["zpe_kJmol"]
        R["extra"]["rotulo"] = d.get("rotulo")
        R["extra"]["validacao"] = d.get("validacao")
        if d.get("simbolos") and d.get("posicoes"):
            R["quadros"].append(quadro(d["simbolos"], d["posicoes"], d.get("celula")))
        R["tipo"] = "freq"
        R["estado"] = "concluido"
        return R
    if isinstance(d, dict) and ("energia_eV" in d or "energia_Ha" in d or "energy_eV" in d):    # resultado genérico
        R["programa"] = d.get("programa") or d.get("program")
        R["versao"] = d.get("versao") or d.get("version")
        niv = d.get("nivel") or d.get("level")
        R["nivel"] = niv if isinstance(niv, dict) else ({"metodo": niv} if niv else {})
        R["energia_eV"] = d.get("energia_eV", d.get("energy_eV"))
        if R["energia_eV"] is None and d.get("energia_Ha") is not None:
            R["energia_eV"] = float(d["energia_Ha"]) * HA_EV
        R["estado"] = d.get("estado") or d.get("status") or "concluido"
        R["convergiu"] = d.get("convergiu", d.get("converged"))
        est = d.get("estrutura") or d.get("structure")
        if est:
            alvo = (Path(p).parent / est)
            try:
                A = ler_ase(alvo)
                R["quadros"] = A["quadros"][-1:]
            except Exception as e:  # noqa: BLE001
                R["avisos"].append(f"estrutura {est} ilegível: {e}")
        return R
    raise ValueError("JSON sem esquema reconhecido (freqs_cm1 / energia_eV / energia_Ha)")


# ----------------------------------------------------------------------------------------------------------
# detecção e despacho
# ----------------------------------------------------------------------------------------------------------
def detectar(p):
    p = Path(p)
    nome, suf = p.name, p.suffix.lower()
    if nome.endswith(".jsonl"):
        return "jsonl"
    if suf == ".json":
        return "json"
    if suf == ".hess":
        return "orca_hess"
    if re.search(r"-VIBRATIONS-\d+\.mol$", nome) or suf == ".mol" and "[FREQ]" in texto(p, 20000):
        return "cp2k_molden"
    if nome.startswith("OUTCAR"):
        return "vasp_outcar"
    if nome.startswith("OSZICAR"):
        return "vasp_oszicar"
    if nome.startswith("vasprun") and suf == ".xml":
        return "vasprun"
    if suf in (".out", ".log", ".txt", ".pwo", ".stdout", "") or nome.endswith(".out.txt"):
        cab = texto(p, 300000)
        if "O   R   C   A" in cab or "* O   R   C   A *" in cab or re.search(r"Program Version \d.*RELEASE", cab):
            return "orca"
        if "CP2K|" in cab or "PROGRAM STARTED AT" in cab and "CP2K" in cab:
            return "cp2k"
        if "Entering Gaussian System" in cab or "Gaussian, Inc." in cab:
            return "gaussian"
        if "Program PWSCF" in cab:
            return "qe"
        if re.search(r"^\s*vasp\.\d", cab, re.M):
            return "vasp_outcar"
    if nome.endswith("_trj.xyz"):
        return "xyz_orca"
    if re.search(r"-pos-\d+\.xyz$", nome):
        return "xyz_cp2k"
    return "ase"


LEITORES = {"orca": ler_orca, "orca_hess": ler_orca_hess, "cp2k": ler_cp2k, "cp2k_molden": ler_cp2k_molden,
            "vasp_outcar": ler_vasp_outcar, "vasp_oszicar": ler_vasp_oszicar, "vasprun": ler_vasprun, "gaussian": ler_gaussian,
            "qe": ler_qe, "ase": ler_ase, "json": ler_json}


def _ler_xyz_prog(p, prog):
    R = novo(p, prog)
    R["quadros"] = ler_xyz_quadros(p, "Ha")
    R["tipo"] = "opt"
    R["estado"] = "desconhecido"
    if R["quadros"]:
        R["energia_eV"] = R["quadros"][-1]["E_eV"]
    return R


def ler(p, formato=None):
    """Lê qualquer arquivo suportado. Nunca levanta exceção: falha vira estado 'ilegivel' + aviso."""
    p = Path(p)
    if not p.exists():
        R = novo(p)
        R["estado"] = "ausente"
        R["avisos"].append(f"arquivo não encontrado: {p}")
        return R
    try:
        tipo = formato or detectar(p)
        if tipo == "xyz_orca":
            return _ler_xyz_prog(p, "ORCA")
        if tipo == "xyz_cp2k":
            return _ler_xyz_prog(p, "CP2K")
        if tipo == "jsonl":
            R = novo(p)
            pr = ler_jsonl_progresso(p)
            R["progresso"] = pr
            R["estado"] = "concluido" if pr["fim"] else "rodando?"
            return R
        if tipo in LEITORES:
            return LEITORES[tipo](p)
        return ler_ase(p, tipo)
    except Exception as e:  # noqa: BLE001
        R = novo(p)
        R["estado"] = "ilegivel"
        R["avisos"].append(f"{p.name}: não consegui ler ({type(e).__name__}: {str(e)[:200]})")
        return R


def estado_final(R, ativo_s=1800, agora=None):
    """concluido | rodando | parado | falhou | ausente | ilegivel | desconhecido ('rodando?' vira rodando ou parado pela idade)."""
    agora = agora or time.time()
    e = R.get("estado")
    if e == "rodando?":
        idade = agora - (R.get("mtime") or 0)
        return "rodando" if idade <= ativo_s else "parado"
    return e
