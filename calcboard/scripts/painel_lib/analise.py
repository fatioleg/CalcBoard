"""Análises numéricas genéricas do painel: erro de força por átomo, correlações de posto, energias relativas entre
métodos e avaliador seguro de expressões/condições. Funções puras (sem E/S), testáveis isoladamente.

Convenções: forças em eV/Å; energias em eV; nada é inventado — o que não pode ser calculado volta como None.
"""
import ast
import math
import operator

import numpy as np

from .textos import Msg

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}
FUNCS = {"max": max, "min": min, "abs": abs, "sqrt": math.sqrt}


# ----------------------------------------------------------------------------------------------------------
# expressões seguras: números, nomes, + − × ÷ **, max/min/abs/sqrt, comparações e and/or/not (nada além disso)
# ----------------------------------------------------------------------------------------------------------
def nomes_expr(expr):
    arv = ast.parse(str(expr), mode="eval")
    funcs = {id(n.func) for n in ast.walk(arv) if isinstance(n, ast.Call)}
    return sorted({n.id for n in ast.walk(arv) if isinstance(n, ast.Name) and id(n) not in funcs})


def avaliar(expr, vals):
    """avalia `expr` (str) com os nomes de `vals`; devolve float (aritmética) ou bool (comparações)."""
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.Name):
            return float(vals[n.id])
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            return not ev(n.operand)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords:
            return float(FUNCS[n.func.id](*[ev(a) for a in n.args]))
        if isinstance(n, ast.Compare) and all(type(o) in CMP for o in n.ops):
            esq = ev(n.left)
            for op, dire in zip(n.ops, n.comparators):
                d = ev(dire)
                if not CMP[type(op)](esq, d):
                    return False
                esq = d
            return True
        if isinstance(n, ast.BoolOp):
            vs = [ev(v) for v in n.values]
            return all(vs) if isinstance(n.op, ast.And) else any(vs)
        raise ValueError(Msg("r_e_expr", x=ast.dump(n)[:60]))
    return ev(ast.parse(str(expr), mode="eval"))


def calc_expr(expr, vals):
    """aritmética segura (compatível com as expressões de energia): devolve float."""
    r = avaliar(expr, vals)
    if isinstance(r, bool):
        raise ValueError(Msg("r_e_expr", x="comparison"))
    return r


def limiares_condicao(expr, nome, vals):
    """limiares simples `nome <op> valor` (ou `valor <op> nome`) de uma condição: [(op, valor)] com op em <,<=,>,>=,==,!=."""
    simb = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}
    inv = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}
    out = []
    for n in ast.walk(ast.parse(str(expr), mode="eval")):
        if not isinstance(n, ast.Compare):
            continue
        partes = [n.left] + list(n.comparators)
        for k, op in enumerate(n.ops):
            a, b = partes[k], partes[k + 1]
            s = simb.get(type(op))
            try:
                if isinstance(a, ast.Name) and a.id == nome and nome not in nomes_expr(ast.unparse(b)):
                    out.append((s, float(avaliar(ast.unparse(b), vals))))
                elif isinstance(b, ast.Name) and b.id == nome and nome not in nomes_expr(ast.unparse(a)):
                    out.append((inv[s], float(avaliar(ast.unparse(a), vals))))
            except Exception:  # noqa: BLE001  (limiar que depende de algo não calculável)
                continue
    return out


# ----------------------------------------------------------------------------------------------------------
# correlações de posto (sem scipy)
# ----------------------------------------------------------------------------------------------------------
def _postos(x):
    x = np.asarray(x, float)
    ordem = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[ordem[j + 1]] == x[ordem[i]]:
            j += 1
        r[ordem[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def spearman(x, y):
    if len(x) < 3:
        return None
    rx, ry = _postos(x), _postos(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def kendall(x, y):
    """tau-b de Kendall (corrige empates)."""
    n = len(x)
    if n < 3:
        return None
    x, y = np.asarray(x, float), np.asarray(y, float)
    c = d = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = np.sign(x[i] - x[j]), np.sign(y[i] - y[j])
            if a == 0 and b == 0:
                continue
            if a == 0:
                tx += 1
            elif b == 0:
                ty += 1
            elif a == b:
                c += 1
            else:
                d += 1
    den = math.sqrt((c + d + tx) * (c + d + ty))
    return None if den == 0 else float((c - d) / den)


# ----------------------------------------------------------------------------------------------------------
# erro de força por átomo
# ----------------------------------------------------------------------------------------------------------
def erro_forcas(Fa, Fb):
    """Fa, Fb: (N,3) eV/Å (mesma geometria, mesma ordem). Devolve o erro por átomo |ΔF| (norma) e as métricas globais.

    mae = média de |ΔF_ia| sobre as 3N componentes cartesianas (o "MAE de força" usual); max_comp = maior componente;
    media_atomo = média do |ΔF| por átomo (norma)."""
    A, B = np.asarray(Fa, float).reshape(-1, 3), np.asarray(Fb, float).reshape(-1, 3)
    if A.shape != B.shape:
        raise ValueError("forças com números de átomos diferentes")
    dF = A - B
    eps = np.linalg.norm(dF, axis=1)
    return {"eps": eps, "dF": dF, "mae": float(np.abs(dF).mean()), "max_comp": float(np.abs(dF).max()),
            "rmse": float(math.sqrt((dF ** 2).mean())), "media_atomo": float(eps.mean()), "max_atomo": float(eps.max())}


def agregar_grupos(dF, rotulos):
    """por rótulo (elemento, componente...): n, MAE por componente cartesiana e parcela do erro total (soma de |ΔF| dos átomos)."""
    dF = np.asarray(dF, float)
    solo = dF.ndim == 1                                  # só o erro por átomo (sem as componentes): MAE por componente indisponível
    eps = dF if solo else np.linalg.norm(dF.reshape(-1, 3), axis=1)
    tot = float(eps.sum())
    out = {}
    for r in dict.fromkeys(rotulos):
        m = np.array([x == r for x in rotulos])
        out[r] = {"n": int(m.sum()), "mae": None if solo else float(np.abs(dF[m]).mean()), "media_atomo": float(eps[m].mean()),
                  "parcela": float(eps[m].sum() / tot) if tot > 0 else None}
    return out


def concentracao(eps, pcts=(5, 10)):
    """fração do erro total (soma de |ΔF| por átomo) contida nos k% piores átomos."""
    e = np.sort(np.asarray(eps, float))[::-1]
    tot = float(e.sum())
    out = {}
    for p in pcts:
        k = max(1, int(math.ceil(len(e) * p / 100.0)))
        out[f"{p:g}"] = {"n": k, "fracao": float(e[:k].sum() / tot) if tot > 0 else None}
    return out


def erro_tensao(Sa, Sb):
    """tensores de tensão em Voigt (6, GPa): MAE das 6 componentes e maior componente."""
    d = np.abs(np.asarray(Sa, float).ravel() - np.asarray(Sb, float).ravel())
    return {"mae": float(d.mean()), "max": float(d.max())}


# ----------------------------------------------------------------------------------------------------------
# energia relativa entre dois métodos
# ----------------------------------------------------------------------------------------------------------
def energia_relativa(rotulos, Ea, Eb, ref):
    """Ea, Eb: energias absolutas (eV) de cada item pelos métodos A e B; ref: índice do item de referência.
    MAE/máx/RMS e MAE centrado sobre os itens exceto a referência; Spearman/Kendall sobre todos os itens."""
    Ea, Eb = np.asarray(Ea, float), np.asarray(Eb, float)
    da, db = Ea - Ea[ref], Eb - Eb[ref]
    resto = [i for i in range(len(rotulos)) if i != ref]
    e = (da - db)[resto]
    out = {"da": da.tolist(), "db": db.tolist(), "n": len(resto), "ref": ref}
    if len(resto):
        out.update({"mae": float(np.abs(e).mean()), "max_abs": float(np.abs(e).max()), "rms": float(math.sqrt((e ** 2).mean())),
                    "vies": float(e.mean()), "mae_centrado": float(np.abs(e - e.mean()).mean())})
    out["spearman"] = spearman(da, db)
    out["kendall"] = kendall(da, db)
    out["menor_a"] = int(np.argmin(Ea))
    out["menor_b"] = int(np.argmin(Eb))
    out["menor_difere"] = out["menor_a"] != out["menor_b"]
    return out


def faixa(valor, limites):
    """índice da faixa de qualidade (0 = melhor): valor ≤ limites[0] → 0; ≤ limites[1] → 1; ...; acima do último → len(limites)."""
    if valor is None:
        return None
    for k, lim in enumerate(limites):
        if valor <= lim:
            return k
    return len(limites)
