"""Gera os dados REAIS do exemplo "dímero de benzeno" (sistema público, trivial).

Etapas (cada uma pode ser rodada sozinha):
  python gerar_dados.py geom        geometrias iniciais (ASE: benzeno g2 + dímeros S, PD e T)
  python gerar_dados.py uma         otimizações UMA (fairchem) com trajetória .traj + progresso .jsonl
  python gerar_dados.py freq        frequências UMA (ase.vibrations) do monômero e do dímero PD
  python gerar_dados.py orca        ORCA B97-3c Opt Freq (monômero e dímero PD) — precisa de `orca6` no PATH
  python gerar_dados.py orca_sp     ORCA B97-3c single point nas geometrias UMA (mesma geometria, C-073)
  python gerar_dados.py anonimizar  troca nome da máquina e diretório de trabalho impressos pelo ORCA por <anonimizado>

Variáveis: ORCA (caminho do executável, padrão `orca6`), NPROCS (padrão 4), UMA_MODELO (padrão uma-s-1p2p1).
Nada aqui é específico do painel: são cálculos comuns, gravados nos formatos nativos de cada programa.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
CALC = AQUI / "calc"
GEOM = CALC / "geometrias"
UMA = CALC / "uma"
ORCA_DIR = CALC / "orca"
MODELO = os.environ.get("UMA_MODELO", "uma-s-1p2p1")
NPROCS = int(os.environ.get("NPROCS", "4"))
ORCA = os.environ.get("ORCA", "orca6")


def monomero():
    from ase.build import molecule
    a = molecule("C6H6")
    a.center()
    a.positions -= a.positions.mean(0)
    return a


def dimero(tipo):
    """S: sanduíche (3,9 Å); PD: paralelo deslocado (3,6 Å na vertical, 1,6 Å de deslizamento); T: em T (5,0 Å)."""
    a = monomero()
    b = monomero()
    if tipo == "S":
        b.positions += [0, 0, 3.9]
    elif tipo == "PD":
        b.positions += [1.6, 0, 3.6]
    elif tipo == "T":
        b.rotate(90, "x", center=(0, 0, 0))     # anel B perpendicular ao A, um C–H apontando para o centro de A
        b.positions += [0, 0, 5.0]
    d = a + b
    d.positions -= d.positions.mean(0)
    return d


def perturbar(a, semente, sigma=0.02):
    a = a.copy()
    if semente:
        a.positions += np.random.default_rng(semente).normal(0, sigma, a.positions.shape)
    return a


def etapa_geom():
    from ase.io import write
    GEOM.mkdir(parents=True, exist_ok=True)
    write(GEOM / "benzeno.xyz", monomero())
    for t in ("S", "PD", "T"):
        for p in (0, 1, 2):
            write(GEOM / f"dimero_{t}__p{p}.xyz", perturbar(dimero(t), p))
    print("geometrias em", GEOM)


def calculador():
    from fairchem.core import FAIRChemCalculator, pretrained_mlip
    pu = pretrained_mlip.get_predict_unit(MODELO, device="cpu")
    return FAIRChemCalculator(pu, task_name="omol")


def versao(p):
    import importlib.metadata as im
    try:
        return im.version(p)
    except Exception:
        return None


def info_metodo():
    return {"programa": "fairchem-core", "versao": versao("fairchem-core"), "modelo": MODELO, "tarefa": "omol",
            "ase": versao("ase")}


def otimizar(calc, nome, atoms, fmax=0.01, passos=400):
    from ase.io import Trajectory, write
    from ase.optimize import BFGS
    for d in ("traj", "progresso", "estruturas"):
        (UMA / d).mkdir(parents=True, exist_ok=True)
    a = atoms.copy()
    a.info.update(charge=0, spin=1)
    a.calc = calc
    traj = Trajectory(UMA / "traj" / f"{nome}.traj", "w", a)
    prog = open(UMA / "progresso" / f"{nome}.jsonl", "w", encoding="utf-8")
    t0 = time.time()
    k = [0]

    def registro():
        f = a.get_forces()
        prog.write(json.dumps({"passo": k[0], "E_eV": float(a.get_potential_energy()),
                               "fmax_eVA": float(np.sqrt((f ** 2).sum(1)).max()), "t_s": round(time.time() - t0, 2),
                               "quando": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
        prog.flush()
        traj.write(a)
        k[0] += 1

    opt = BFGS(a, logfile=None)
    opt.attach(registro, interval=1)
    conv = bool(opt.run(fmax=fmax, steps=passos))
    prog.write(json.dumps({"fim": True, "convergiu": conv, "passos": k[0] - 1, "tempo_s": round(time.time() - t0, 2)}) + "\n")
    prog.close()
    traj.close()
    a.info.update(info_metodo())
    a.info["convergiu"] = conv
    a.info["fmax_criterio"] = fmax
    write(UMA / "estruturas" / f"{nome}.extxyz", a)
    print(f"{nome}: E = {a.get_potential_energy():.5f} eV, convergiu={conv}, {k[0] - 1} passos")
    return a


def etapa_uma():
    from ase.io import read
    calc = calculador()
    otimizar(calc, "benzeno", read(GEOM / "benzeno.xyz"))
    for t in ("PD", "S", "T"):
        for p in (0, 1, 2):
            otimizar(calc, f"dimero_{t}__p{p}", read(GEOM / f"dimero_{t}__p{p}.xyz"))


def etapa_freq():
    from ase import units
    from ase.io import read
    from ase.vibrations import Vibrations
    calc = calculador()
    pasta = UMA / "freq"
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in ("benzeno", "dimero_PD__p0"):
        a = read(UMA / "estruturas" / f"{nome}.extxyz")
        a.info.update(charge=0, spin=1)
        a.calc = calc
        vib = Vibrations(a, name=str(pasta / f"cache_{nome}"), delta=0.01, nfree=2)
        vib.run()
        H = vib.get_vibrations().get_hessian_2d()
        H = 0.5 * (H + H.T)
        m = np.repeat(a.get_masses(), 3)
        lam, V = np.linalg.eigh(H / np.sqrt(np.outer(m, m)))
        f = np.sign(lam) * np.sqrt(np.abs(lam) * units._e * 1e20 / units._amu) / (2 * np.pi * units._c) / 100.0
        U = (V / np.sqrt(m)[:, None]).T.reshape(len(f), len(a), 3)
        U /= np.linalg.norm(U.reshape(len(f), -1), axis=1)[:, None, None]
        ordem = np.argsort(f)
        f, U = f[ordem], U[ordem]
        resto = f[np.argsort(np.abs(f))][6:]
        zpe = float(0.5 * resto[resto > 0].sum() * 0.011962656)     # kJ/mol por cm-1
        d = {"rotulo": "EXPLORATÓRIO", "metodo": {**info_metodo(), "hessiana": "diferenças finitas centrais, δ = 0,01 Å"},
             "freqs_cm1": [round(float(x), 2) for x in f], "n_imaginarias": int((f < -20).sum()),
             "modos": np.round(U, 4).tolist(), "simbolos": a.get_chemical_symbols(),
             "posicoes": np.round(a.positions, 4).tolist(), "indices_deslocados": list(range(len(a))),
             "zpe_kJmol": round(zpe, 3)}
        (pasta / f"{nome}.json").write_text(json.dumps(d), encoding="utf-8")
        print(nome, "freqs:", d["freqs_cm1"][:8], "...")


def rodar_orca(pasta, nome, atoms, linha):
    from ase.io import write
    pasta.mkdir(parents=True, exist_ok=True)
    xyz = "\n".join(f"{s:2s} {p[0]:14.8f} {p[1]:14.8f} {p[2]:14.8f}" for s, p in zip(atoms.get_chemical_symbols(), atoms.positions))
    (pasta / f"{nome}.inp").write_text(f"{linha}\n%pal nprocs {NPROCS} end\n%maxcore 2500\n* xyz 0 1\n{xyz}\n*\n", encoding="utf-8")
    write(pasta / f"{nome}_inicial.xyz", atoms)
    with open(pasta / f"{nome}.out", "w") as fh:
        subprocess.run([ORCA, f"{nome}.inp"], cwd=pasta, stdout=fh, stderr=subprocess.STDOUT, check=False)
    for lixo in pasta.glob(f"{nome}*"):          # binários grandes não vão para o repositório
        if lixo.suffix in (".gbw", ".densities", ".densitiesinfo", ".tmp", ".ges", ".bibtex", ".engrad", ".opt", ".cpcm", ".hostnames", ".txt") or ".tmp" in lixo.name or lixo.suffix.startswith(".bas"):
            lixo.unlink()
    print(nome, "ORCA terminou")


def etapa_orca():
    from ase.io import read
    rodar_orca(ORCA_DIR / "benzeno", "benzeno", read(GEOM / "benzeno.xyz"), "! B97-3c Opt Freq TightSCF")
    rodar_orca(ORCA_DIR / "dimero_PD", "dimero_PD", read(GEOM / "dimero_PD__p0.xyz"), "! B97-3c Opt Freq TightSCF")


def etapa_orca_sp():
    from ase.io import read
    for nome in ("benzeno", "dimero_PD__p0"):
        rodar_orca(ORCA_DIR / "sp_na_geometria_uma", f"sp_{nome}", read(UMA / "estruturas" / f"{nome}.extxyz"), "! B97-3c TightSCF")


def etapa_anonimizar():
    import re
    for out in ORCA_DIR.rglob("*.out"):
        t = out.read_text(errors="replace")
        t2 = re.sub(r"(\* Host name:\s+).*", r"\1<anonimizado>", t)
        t2 = re.sub(r"(\* Working dir\.:\s+).*", r"\1<anonimizado>", t2)
        if t2 != t:
            out.write_text(t2)
    for lixo in ORCA_DIR.rglob("*.property.txt"):
        lixo.unlink()
    print("anonimizado")


if __name__ == "__main__":
    {"anonimizar": etapa_anonimizar, "geom": etapa_geom, "uma": etapa_uma, "freq": etapa_freq, "orca": etapa_orca, "orca_sp": etapa_orca_sp}[sys.argv[1]]()
