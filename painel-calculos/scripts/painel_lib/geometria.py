"""Geometria: moléculas inteiras em células periódicas, componentes, anéis, seleções e medidas definidas na configuração.

Seleções (texto), avaliadas sobre a estrutura:
  todos                       todos os átomos (um grupo)
  0-11,14  |  idx:0-11        índices (base 0), um grupo
  mol:2                       a 2ª molécula (base 1, na ordem do primeiro átomo de cada uma)
  mol:C6H6                    cada molécula com essa fórmula (vários grupos)
  mol:*                       cada molécula (vários grupos)
  anel:6 | anel:C6 | anel:C3N2 | anel:*   anéis (ciclos mínimos) por tamanho ou composição (vários grupos)
  comp:<nome>                 componente nomeado na configuração (vários grupos, um por molécula)
  el:C                        todos os átomos do elemento (um grupo)
  A & B                       filtro: cada grupo de A intersectado com os átomos de B (ex.: mol:C6H6&el:C)
"""
import re
from collections import deque

import numpy as np

RAIOS = {"H": 0.31, "He": 0.28, "Li": 1.28, "Be": 0.96, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "Ne": 0.58,
         "Na": 1.66, "Mg": 1.41, "Al": 1.21, "Si": 1.11, "P": 1.07, "S": 1.05, "Cl": 1.02, "Ar": 1.06, "K": 2.03, "Ca": 1.76,
         "Sc": 1.70, "Ti": 1.60, "V": 1.53, "Cr": 1.39, "Mn": 1.39, "Fe": 1.32, "Co": 1.26, "Ni": 1.24, "Cu": 1.32, "Zn": 1.22,
         "Ga": 1.22, "Ge": 1.20, "As": 1.19, "Se": 1.20, "Br": 1.20, "Kr": 1.16, "Rb": 2.20, "Sr": 1.95, "Y": 1.90, "Zr": 1.75,
         "Nb": 1.64, "Mo": 1.54, "Ru": 1.46, "Rh": 1.42, "Pd": 1.39, "Ag": 1.45, "Cd": 1.44, "In": 1.42, "Sn": 1.39, "Sb": 1.39,
         "Te": 1.38, "I": 1.39, "Xe": 1.40, "Cs": 2.44, "Ba": 2.15, "La": 2.07, "Hf": 1.75, "Ta": 1.70, "W": 1.62, "Re": 1.51,
         "Os": 1.44, "Ir": 1.41, "Pt": 1.36, "Au": 1.36, "Hg": 1.32, "Tl": 1.45, "Pb": 1.46, "Bi": 1.48}


def formula(simbolos):
    from collections import Counter
    c = Counter(simbolos)
    ordem = (["C", "H"] if "C" in c else []) + sorted(k for k in c if not ("C" in c and k in ("C", "H")))
    return "".join(f"{k}{c[k] if c[k] > 1 else ''}" for k in ordem)


def ligacoes(simbolos, pos, cel=None, mult=1.15, maximo_atomos=6000):
    """lista (i, j, deslocamento_cartesiano j-i) de pares ligados; periódico se `cel` for dado."""
    n = len(simbolos)
    if n == 0 or n > maximo_atomos:
        return []
    try:
        from ase import Atoms
        from ase.neighborlist import natural_cutoffs, neighbor_list
        a = Atoms(simbolos, positions=pos, cell=cel if cel is not None else None, pbc=cel is not None)
        i, j, D = neighbor_list("ijD", a, natural_cutoffs(a, mult=mult))
        return [(int(x), int(y), D[k]) for k, (x, y) in enumerate(zip(i, j)) if x != y or np.linalg.norm(D[k]) > 0.1]
    except Exception:
        r = np.array([RAIOS.get(s, 1.5) for s in simbolos]) * mult
        out = []
        P = np.asarray(pos, float)
        for x in range(n):
            d = np.linalg.norm(P - P[x], axis=1)
            for y in np.where((d < r + r[x]) & (d > 0.1))[0]:
                out.append((x, int(y), P[y] - P[x]))
        return out


def desembrulhar(simbolos, pos, cel=None):
    """(posições com moléculas inteiras, rótulo de molécula por átomo, lista de ligações i<j).
    Em sistemas periódicos, cada molécula é reconstruída pelas ligações e seu centroide é posto dentro da célula."""
    n = len(simbolos)
    pos = np.asarray(pos, float)
    L = ligacoes(simbolos, pos, cel)
    adj = [[] for _ in range(n)]
    for i, j, D in L:
        adj[i].append((j, D))
    u = pos.copy()
    lab = -np.ones(n, int)
    c = 0
    for raiz in range(n):
        if lab[raiz] >= 0:
            continue
        lab[raiz] = c
        u[raiz] = pos[raiz]
        fila = deque([raiz])
        membros = [raiz]
        while fila:
            x = fila.popleft()
            for y, D in adj[x]:
                if lab[y] < 0:
                    lab[y] = c
                    u[y] = u[x] + D
                    fila.append(y)
                    membros.append(y)
        if cel is not None:
            C = np.asarray(cel, float)
            fc = u[membros].mean(0) @ np.linalg.inv(C)
            u[membros] -= np.floor(fc) @ C
        c += 1
    pares = sorted({(min(i, j), max(i, j)) for i, j, _ in L})
    return u, lab, pares


def mapear(ref_u, ini_pos, ini_cel, fin_pos, fin_cel):
    """posições finais coerentes com a referência desembrulhada (mesma molécula inteira) e |Δr| interno por átomo.
    Usa a diferença fracionária mínima (descontada a deformação da célula), como no painel original."""
    fin_pos = np.asarray(fin_pos, float)
    if ini_cel is None or fin_cel is None:
        al = alinhar(fin_pos, np.asarray(ref_u, float))       # molécula: remove translação e rotação rígidas
        return al, np.linalg.norm(al - ref_u, axis=1)
    Ci, Cf = np.asarray(ini_cel, float), np.asarray(fin_cel, float)
    ref_frac = ref_u @ np.linalg.inv(Ci)
    fi = np.asarray(ini_pos, float) @ np.linalg.inv(Ci)
    ff = fin_pos @ np.linalg.inv(Cf)
    d = ff - fi
    d -= np.round(d)
    return (ref_frac + d) @ Cf, np.linalg.norm(d @ Cf, axis=1)


def alinhar(P, Q):
    """Kabsch: P (móvel) sobreposto a Q (referência), mesmos átomos na mesma ordem."""
    P, Q = np.asarray(P, float), np.asarray(Q, float)
    if len(P) < 3:
        return P - P.mean(0) + Q.mean(0)
    p0, q0 = P.mean(0), Q.mean(0)
    H = (P - p0).T @ (Q - q0)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1, 1, d]) @ U.T
    return (P - p0) @ R.T + q0


def aneis(n, pares, tam_max=8):
    """ciclos mínimos (um por ligação: menor caminho alternativo), sem repetição; bom para anéis aromáticos e afins."""
    adj = [[] for _ in range(n)]
    for i, j in pares:
        adj[i].append(j)
        adj[j].append(i)
    vistos, out = set(), []
    for i, j in pares:
        # menor caminho de j a i sem usar a aresta (i, j)
        prev = {j: None}
        fila = deque([j])
        achou = False
        while fila and not achou:
            x = fila.popleft()
            for y in adj[x]:
                if (x == j and y == i) or y in prev:
                    continue
                prev[y] = x
                if y == i:
                    achou = True
                    break
                fila.append(y)
        if not achou:
            continue
        cam = []
        x = i
        while x is not None:
            cam.append(x)
            x = prev[x]
        if len(cam) > tam_max:
            continue
        k = tuple(sorted(cam))
        if k not in vistos:
            vistos.add(k)
            out.append(cam)
    return out


def _indices(txt, n):
    out = []
    for parte in txt.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "-" in parte[1:]:
            a, b = parte.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(parte))
    return [i for i in out if 0 <= i < n]


class Contexto:
    """moléculas, fórmulas, anéis e componentes nomeados de uma estrutura (calculados uma vez)."""

    def __init__(self, simbolos, lab, pares, componentes=None):
        self.sim = list(simbolos)
        self.n = len(simbolos)
        self.lab = np.asarray(lab)
        ordem = []
        for x in self.lab:
            if x not in ordem:
                ordem.append(int(x))
        self.mols = [[i for i in range(self.n) if self.lab[i] == c] for c in ordem]
        self.formulas = [formula([self.sim[i] for i in m]) for m in self.mols]
        self.pares = pares
        self._aneis = None
        self.componentes = componentes or []      # [{nome, formula|contem|indices}]
        self.papel = self._papeis()

    @property
    def lista_aneis(self):
        if self._aneis is None:
            self._aneis = aneis(self.n, self.pares) if self.n <= 4000 else []
        return self._aneis

    def _casa(self, comp, k):
        m = self.mols[k]
        if comp.get("formula"):
            fs = comp["formula"] if isinstance(comp["formula"], list) else [comp["formula"]]
            if self.formulas[k] not in fs:
                return False
        if comp.get("contem"):
            els = comp["contem"] if isinstance(comp["contem"], list) else [comp["contem"]]
            if not any(self.sim[i] in els for i in m):
                return False
        if comp.get("indices") is not None:
            ix = set(_indices(str(comp["indices"]), self.n))
            if not set(m) <= ix:
                return False
        return bool(comp.get("formula") or comp.get("contem") or comp.get("indices") is not None)

    def _papeis(self):
        """índice de componente por átomo: componentes da configuração; senão, uma classe por fórmula distinta."""
        papel = -np.ones(self.n, int)
        if self.componentes:
            for k in range(len(self.mols)):
                for c, comp in enumerate(self.componentes):
                    if self._casa(comp, k):
                        papel[self.mols[k]] = c
                        break
            return papel
        return papel

    def selecionar(self, expr, grupos_nomeados=None):
        partes = [p.strip() for p in str(expr).split("&")]
        grupos = self._termo(partes[0], grupos_nomeados)
        for f in partes[1:]:
            filtro = set(i for g in self._termo(f, grupos_nomeados) for i in g)
            grupos = [[i for i in g if i in filtro] for g in grupos]
        return [g for g in grupos if g]

    def _termo(self, t, nomeados):
        t = t.strip()
        if t in ("todos", "all", "*"):
            return [list(range(self.n))]
        m = re.match(r"^(\w+):(.*)$", t)
        if not m:
            return [_indices(t, self.n)]
        tipo, arg = m.group(1).lower(), m.group(2).strip()
        if tipo == "idx":
            return [_indices(arg, self.n)]
        if tipo == "el":
            els = [x.strip() for x in arg.split(",")]
            return [[i for i in range(self.n) if self.sim[i] in els]]
        if tipo == "mol":
            if arg == "*":
                return [list(m) for m in self.mols]
            if arg.isdigit():
                k = int(arg) - 1
                return [list(self.mols[k])] if 0 <= k < len(self.mols) else []
            mm = re.match(r"^([A-Za-z0-9]+)#(\d+)$", arg)
            if mm:
                gs = [list(self.mols[k]) for k in range(len(self.mols)) if self.formulas[k] == mm.group(1)]
                k = int(mm.group(2)) - 1
                return [gs[k]] if 0 <= k < len(gs) else []
            return [list(self.mols[k]) for k in range(len(self.mols)) if self.formulas[k] == arg]
        if tipo == "anel":
            R = self.lista_aneis
            if arg == "*":
                return [list(r) for r in R]
            if arg.isdigit():
                return [list(r) for r in R if len(r) == int(arg)]
            return [list(r) for r in R if formula([self.sim[i] for i in r]) == arg]
        if tipo == "comp":
            for c, comp in enumerate(self.componentes):
                if comp.get("nome") == arg:
                    return [list(self.mols[k]) for k in range(len(self.mols)) if self._casa(comp, k)]
            return []
        if tipo == "grupo" and nomeados and arg in nomeados:
            return [_indices(str(nomeados[arg]), self.n)]
        raise ValueError(f"seleção desconhecida: {t}")


def plano(P):
    P = np.asarray(P, float)
    c = P.mean(0)
    if len(P) < 3:
        return c, None
    n = np.linalg.svd(P - c)[2][2]
    return c, n / np.linalg.norm(n)


def _translacoes(cel):
    if cel is None:
        return np.zeros((1, 3))
    C = np.asarray(cel, float)
    return np.array([[a, b, c] for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)], float) @ C


TIPOS_MEDIDA = {"distancia": "Å", "perpendicular": "Å", "deslizamento": "Å", "angulo_planos": "°", "angulo": "°", "diedro": "°",
                "distancia_minima": "Å"}


def _pares(def_, ctx, pos, cel, nomeados):
    """pares (A, B-imagem) para medidas entre dois grupos; cada par com centroide, normal e grandezas derivadas."""
    GA = ctx.selecionar(def_["a"], nomeados)
    GB = ctx.selecionar(def_["b"], nomeados)
    if not GA or not GB:
        return []
    T = _translacoes(cel)
    lados = bool(def_.get("lados"))
    mais_prox = def_.get("mais_proximo", len(GB) > 1)
    out = []
    for k, ga in enumerate(GA):
        cA, nA = plano(pos[ga])
        cands = []
        alvos = [gb for gb in GB if set(gb) != set(ga)] if mais_prox else [GB[min(k, len(GB) - 1)]]
        for gb in alvos:
            cB0, nB = plano(pos[gb])
            for t in (T if mais_prox else np.zeros((1, 3))):
                cB = cB0 + t
                v = cB - cA
                d = float(np.linalg.norm(v))
                if d < 1e-6:
                    continue
                perp = abs(float(v @ nA)) if nA is not None else None
                cands.append({"cA": cA, "cB": cB, "nA": nA, "nB": nB, "d": d, "t": t, "gb": gb,
                              "lado": float(np.sign(v @ nA)) if nA is not None else 0.0, "perp": perp})
        if not cands:
            continue
        cands.sort(key=lambda c: c["d"])
        if lados and cands[0]["nA"] is not None:
            esc = {}
            for c in cands:
                esc.setdefault(c["lado"], c)
            escolhidos = [esc[s] for s in sorted(esc)][:2]
        else:
            escolhidos = cands[:1]
        for c in escolhidos:
            ang = None
            if c["nA"] is not None and c["nB"] is not None:
                ang = float(np.degrees(np.arccos(min(1.0, abs(float(c["nA"] @ c["nB"]))))))
            slip = float(np.sqrt(max(c["d"] ** 2 - c["perp"] ** 2, 0))) if c["perp"] is not None else None
            c.update({"distancia": c["d"], "perpendicular": c["perp"], "deslizamento": slip, "angulo_planos": ang})
            out.append(c)
    return out


def _ang(a, b, c):
    u, w = a - b, c - b
    return float(np.degrees(np.arccos(np.clip(u @ w / np.linalg.norm(u) / np.linalg.norm(w), -1, 1))))


def _diedro(p0, p1, p2, p3):
    b1, b2, b3 = p1 - p0, p2 - p1, p3 - p2
    n1, n2 = np.cross(b1, b2), np.cross(b2, b3)
    m1 = np.cross(n1, b2 / np.linalg.norm(b2))
    return float(np.degrees(np.arctan2(m1 @ n2, n1 @ n2)))


def medir(def_, ctx, pos, cel, nomeados=None):
    """valor (agregado), lista de valores por par e primitivas de desenho (centroides, normais, linhas com rótulo)."""
    tipo = def_.get("tipo", "distancia")
    pos = np.asarray(pos, float)
    agr = def_.get("agregar", "media")
    des = {"pontos": [], "setas": [], "linhas": []}
    r3 = lambda v: [round(float(x), 3) for x in v]  # noqa: E731
    if tipo in ("distancia", "perpendicular", "deslizamento", "angulo_planos"):
        P = _pares(def_, ctx, pos, cel, nomeados)
        vals = [p[tipo] for p in P if p[tipo] is not None]
        for p in P:
            des["pontos"] += [[r3(p["cA"]), "A"], [r3(p["cB"]), "B"]]
            if p["nA"] is not None:
                des["setas"].append([r3(p["cA"]), r3(p["nA"]), "A"])
            if p["nB"] is not None and tipo in ("angulo_planos", "perpendicular", "deslizamento"):
                des["setas"].append([r3(p["cB"]), r3(p["nB"]), "B"])
            des["linhas"].append([r3(p["cA"]), r3(p["cB"]), round(float(p[tipo]), 3) if p[tipo] is not None else None])
    elif tipo == "distancia_minima":
        GA, GB = ctx.selecionar(def_["a"], nomeados), ctx.selecionar(def_["b"], nomeados)
        A = sorted(set(i for g in GA for i in g))
        B = sorted(set(i for g in GB for i in g) - set(A))
        vals = []
        if A and B:
            best = (1e9, None, None)
            for t in _translacoes(cel):
                D = np.linalg.norm(pos[A][:, None, :] - (pos[B] + t)[None, :, :], axis=2)
                k = np.unravel_index(np.argmin(D), D.shape)
                if D[k] < best[0]:
                    best = (float(D[k]), pos[A][k[0]], pos[B][k[1]] + t)
            vals = [best[0]]
            des["linhas"].append([r3(best[1]), r3(best[2]), round(best[0], 3)])
    elif tipo in ("angulo", "diedro"):
        chaves = ["a", "b", "c"] + (["d"] if tipo == "diedro" else [])
        pts = []
        for k in chaves:
            g = ctx.selecionar(def_[k], nomeados)
            if not g:
                return {"valor": None, "valores": [], "desenho": des}
            pts.append(pos[g[0]].mean(0))
        vals = [_ang(*pts) if tipo == "angulo" else _diedro(*pts)]
        for i in range(len(pts) - 1):
            des["linhas"].append([r3(pts[i]), r3(pts[i + 1]), None])
        des["pontos"] += [[r3(p), "A"] for p in pts]
    else:
        raise ValueError(f"tipo de medida desconhecido: {tipo}")
    if not vals:
        return {"valor": None, "valores": [], "desenho": des}
    v = {"media": float(np.mean(vals)), "min": float(np.min(vals)), "max": float(np.max(vals)), "primeiro": float(vals[0]),
         "ponto_medio": float((max(vals) + min(vals)) / 2)}.get(agr, float(np.mean(vals)))
    return {"valor": v, "valores": [round(float(x), 4) for x in vals], "desenho": des}
