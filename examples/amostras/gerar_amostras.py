"""Gera amostras SINTÉTICAS e curtas de saídas de CP2K, VASP, Gaussian e Quantum ESPRESSO para testar os leitores.

Os números são inventados (plausíveis, mas sem valor científico); o LEIAUTE imita as saídas reais de cada programa
nas partes que os leitores usam. Cada arquivo traz a marca SINTETICO no nome do projeto/título.
Também cria `orca/benzeno_em_andamento.out`: o início de uma saída ORCA real do exemplo dimero_benzeno, cortado no
meio de um SCF, para simular um cálculo ainda rodando.

  python gerar_amostras.py
"""
import math
from pathlib import Path

AQUI = Path(__file__).resolve().parent
BOHR = 0.529177210903


def escrever(rel, txt):
    p = AQUI / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return p


AGUA = [("O", 0.000, 0.000, 0.119), ("H", 0.000, 0.763, -0.477), ("H", 0.000, -0.763, -0.477)]


def agua_passo(k):
    """geometria da água relaxando aos poucos (O–H 0,97 -> 0,975 Å)."""
    f = 1 + 0.004 * (1 - math.exp(-k))
    return [(s, x, y * f, z * f if s == "H" else z) for s, x, y, z in AGUA]


# ----------------------------------------------------------------------------------------------------------
def cp2k_scf(energia, n, t0=0.8, conv0=0.08, taxa=0.35, ls=True):
    linhas = ["", "  Step     Update method      Time    Convergence         Total energy    Change", "  " + "-" * 78]
    E = energia + 0.5
    for i in range(1, n + 1):
        conv = conv0 * math.exp(-taxa * (i - 1) * 2.3)
        Enew = energia + 0.5 * math.exp(-0.9 * i)
        linhas.append(f"  {i:5d} OT DIIS     0.15E+00 {t0 + 0.01 * i:7.1f} {conv:14.8f} {Enew:20.10f} {Enew - E:9.2E}")
        E = Enew
        if ls and i == 2:
            linhas.append(f"  {i + 100:5d} OT LS       0.30E+00 {t0:7.1f}                {Enew:20.10f}".replace(f"{i + 100:5d}", f"{i:5d}"))
    return linhas


def gerar_cp2k():
    base = ["", "  **** **** ******  **  PROGRAM STARTED AT               2026-10-01 09:00:00.000",
            " ***** ** ***  *** **   PROGRAM STARTED ON                   maquina-exemplo",
            " CP2K| version string:                                          CP2K version 2024.1",
            " GLOBAL| Project name                                                 SINTETICO_agua",
            " GLOBAL| Run type                                                            GEO_OPT",
            " CELL| Vector a [angstrom]:      10.000     0.000     0.000    |a| =      10.000000",
            " CELL| Vector b [angstrom]:       0.000    10.000     0.000    |b| =      10.000000",
            " CELL| Vector c [angstrom]:       0.000     0.000    10.000    |c| =      10.000000",
            " DFT| Charge                                                                       0",
            " DFT| Multiplicity                                                                 1",
            " FUNCTIONAL| PBE:", " FUNCTIONAL| J.P.Perdew, K.Burke, M.Ernzerhof, Phys. Rev. Letter, vol. 77, n 18, pp. 3865-3868, (1996)",
            " vdW POTENTIAL|                                                       Pair Potential",
            " vdW POTENTIAL|                                              DFT-D3 (Version 3.1)",
            " QS| Density cutoff [a.u.]:                                                  200.0",
            "  Atomic kind: O                                    Number of atoms:       1",
            "     Orbital Basis Set                                       DZVP-MOLOPT-SR-GTH",
            "     GTH Potential information for                                GTH-PBE-q6",
            "  Atomic kind: H                                    Number of atoms:       2",
            "     Orbital Basis Set                                       DZVP-MOLOPT-SR-GTH",
            "     GTH Potential information for                                GTH-PBE-q1",
            " SCF PARAMETERS         Density guess:                                     ATOMIC",
            "                        max_scf:                                               50",
            "                        eps_scf:                                         1.00E-06",
            "", " MODULE QUICKSTEP: ATOMIC COORDINATES IN ANGSTROM", "",
            "  Atom  Kind  Element       X           Y           Z          Z(eff)       Mass", ""]
    for k, (s, x, y, z) in enumerate(AGUA):
        base.append(f"       {k + 1}     {1 if s == 'O' else 2} {s:2s}  {8 if s == 'O' else 1:3d} {x + 5:11.6f} {y + 5:11.6f} {z + 5:11.6f}      {6.0 if s == 'O' else 1.0:6.4f}      {15.999 if s == 'O' else 1.008:7.4f}")
    base.append("")
    energias = [-17.2210, -17.2236, -17.2241]
    xyz = []
    for k, E in enumerate(energias):
        if k:
            base += ["", " --------  Informations at step =     %d ------------" % k,
                     f"  Max. gradient              =         {0.0123 / (3 ** k):.10f}",
                     f"  Conv. limit for gradients  =         0.0004500000", ""]
            base.append(f" OPTIMIZATION STEP:      {k + 1}")
        base += cp2k_scf(E, 9 if k else 14)
        base += ["", "  *** SCF run converged in    %d steps ***" % (9 if k else 14), "",
                 f" ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]:             {E:.12f}", ""]
        g = agua_passo(k)
        xyz.append(f"{len(g)}\n i =        {k}, E =     {E:.10f}\n" + "\n".join(f"{s:2s} {x + 5:16.10f} {y + 5:16.10f} {z + 5:16.10f}" for s, x, y, z in g))
    # passo atual (em andamento): SCF pela metade, sem fim de programa
    base += ["", " OPTIMIZATION STEP:      4"] + cp2k_scf(-17.2242, 5, conv0=0.002, taxa=0.25, ls=False)
    escrever("cp2k/agua_geo/SINTETICO_agua.out", "\n".join(base) + "\n")
    escrever("cp2k/agua_geo/SINTETICO_agua-pos-1.xyz", "\n".join(xyz) + "\n")
    # job que falhou: SCF não convergiu
    f = base[:28] + ["", " MODULE QUICKSTEP: ATOMIC COORDINATES IN ANGSTROM"] + cp2k_scf(-17.20, 50, conv0=0.3, taxa=0.01, ls=False) + [
        "", " *** WARNING in qs_scf.F:542 :: SCF run NOT converged ***", "",
        "  **** **** ******  **  PROGRAM ENDED AT                 2026-10-01 09:20:00.000"]
    escrever("cp2k/falhou/SINTETICO_falhou.out", "\n".join(f).replace("SINTETICO_agua", "SINTETICO_falhou") + "\n")


# ----------------------------------------------------------------------------------------------------------
def gerar_vasp():
    a = 5.43
    pos = [[(0, 0, 0), (1.3575, 1.3575, 1.3575)], [(0.002, -0.001, 0.0), (1.3570, 1.3580, 1.3575)]]
    ens = [-10.8251, -10.8263]
    L = [" vasp.6.4.2 20Jul23 (build Oct 01 2026) complex", " executed on             LinuxIFC date 2026.10.01  09:00:00",
         " POTCAR:    PAW_PBE Si 05Jan2001", " POTCAR:    PAW_PBE Si 05Jan2001",
         "   VRHFIN =Si: s2p2", "   ions per type =               2",
         "   ENCUT  =  520.0 eV  38.22 Ry    6.18 a.u.", "   EDIFF  = 0.1E-05   stopping-criterion for ELM",
         "   IBRION =      2    ionic relax: 0-MD 1-quasi-New 2-CG", "   ISIF   =      3    stress and relaxation",
         "   GGA     = PE    GGA type", "   IVDW   =     12", ""]
    cel = [[0, a / 2, a / 2], [a / 2, 0, a / 2], [a / 2, a / 2, 0]]
    def lat(c):
        return [" direct lattice vectors                 reciprocal lattice vectors"] + [f"   {v[0]:12.9f} {v[1]:12.9f} {v[2]:12.9f}     0.0 0.0 0.0" for v in c]
    L += lat(cel)
    for k in range(2):
        c2 = [[x * (1 + 0.002 * k) for x in v] for v in cel]
        L += [""] + lat(c2) + ["", "  FORCE on cell =-STRESS in cart. coord.  units (eV):",
                               f"  in kB      {-3.2 + 2.9 * k:9.5f}  {-3.2 + 2.9 * k:9.5f}  {-3.2 + 2.9 * k:9.5f}     0.00000     0.00000     0.00000", "",
                               " POSITION                                       TOTAL-FORCE (eV/Angst)",
                               " -----------------------------------------------------------------------------------"]
        for p in pos[k]:
            f = 0.02 / (k + 1)
            L.append(f"      {p[0]:9.5f}      {p[1]:9.5f}      {p[2]:9.5f}        {f:9.6f}     {-f:9.6f}      0.000000")
        L += [" -----------------------------------------------------------------------------------", "",
              f"  free  energy   TOTEN  =       {ens[k] - 0.0004:.8f} eV", "",
              f"  energy  without entropy=      {ens[k]:.8f}  energy(sigma->0) =      {ens[k] - 0.0002:.8f}", ""]
    L += [" reached required accuracy - stopping structural energy minimisation",
          " General timing and accounting informations for this job:", "                  Elapsed time (sec):       42.317"]
    escrever("vasp/si_relax/OUTCAR", "\n".join(L) + "\n")
    O = []
    for k in range(2):
        E = ens[k]
        for i in range(1, 9 if k == 0 else 6):
            dE = (0.9 if i == 1 else 1) * (-10 ** (1 - i)) * (1.5 if k == 0 else 0.4)
            O.append(f"DAV:  {i:3d}    {E + abs(dE):.9E}   {dE:.5E}   {dE * 0.3:.5E}  1024   {abs(dE) ** 0.5:.3E}")
        O.append(f"   {k + 1} F= {ens[k] - 0.0004:.8E} E0= {ens[k] - 0.0002:.8E}  d E ={-0.0012 * k:.6E}  mag=     0.0000")
    escrever("vasp/si_relax/OSZICAR", "\n".join(O) + "\n")


# ----------------------------------------------------------------------------------------------------------
def gerar_gaussian():
    L = [" Entering Gaussian System, Link 0=g16", " Copyright (c) 1988-2019, Gaussian, Inc.  All Rights Reserved.",
         " ******************************************", " Gaussian 16:  ES64L-G16RevC.01  3-Jul-2019", "                 1-Oct-2026",
         " ******************************************", " -------------------------------------------",
         " #p B3LYP/6-31G(d) opt freq EmpiricalDispersion=GD3BJ", " -------------------------------------------",
         " SINTETICO agua", " Charge =  0 Multiplicity = 1"]
    ens = [-76.40851, -76.40889, -76.40890]
    for k, E in enumerate(ens):
        g = agua_passo(k)
        L += ["                         Standard orientation:", " ---------------------------------------------------------------------",
              " Center     Atomic      Atomic             Coordinates (Angstroms)", " Number     Number       Type             X           Y           Z",
              " ---------------------------------------------------------------------"]
        for i, (s, x, y, z) in enumerate(g):
            L.append(f"      {i + 1:2d}          {8 if s == 'O' else 1:2d}           0       {x:10.6f}  {y:10.6f}  {z:10.6f}")
        L.append(" ---------------------------------------------------------------------")
        L.append(" Requested convergence on RMS density matrix=1.00D-08 within 128 cycles.")
        for c in range(1, 7):
            L += [f" Cycle   {c}  Pass 1  IDiag  1:", f" E= {E + 0.01 * 10 ** (-c):.12f}     Delta-E=       {-0.01 * 10 ** (-c):.12f} Rises=F Damp=F",
                  f" RMSDP={3 * 10 ** (-c - 2):.2E} MaxDP={1 * 10 ** (-c - 1):.2E}              OVMax= 0.0".replace("E", "D")]
        L.append(f" SCF Done:  E(RB3LYP) =  {E:.9f}     A.U. after    6 cycles")
        if k < 2:
            L += ["         Item               Value     Threshold  Converged?",
                  f" Maximum Force            {0.012 / 4 ** k:.6f}     0.000450     {'YES' if k else 'NO'}"]
    L += ["    -- Stationary point found.", " Optimization completed."]
    # frequências (3 modos da água)
    modos = [(1625.3, [(0.00, 0.00, 0.07), (0.00, -0.43, -0.56), (0.00, 0.43, -0.56)]),
             (3712.8, [(0.00, 0.00, -0.05), (0.00, 0.58, 0.40), (0.00, -0.58, 0.40)]),
             (3818.4, [(0.00, 0.07, 0.00), (0.00, -0.56, 0.43), (0.00, -0.56, -0.43)])]
    L += [" Harmonic frequencies (cm**-1), IR intensities (KM/Mole), Raman scattering", " activities (A**4/AMU), depolarization ratios for plane and unpolarized",
          " incident light, reduced masses (AMU), force constants (mDyne/A),", " and normal coordinates:",
          "                      1                      2                      3", "                     A1                     A1                     B2",
          " Frequencies --  " + "".join(f"{f:10.4f}             " for f, _ in modos).rstrip(),
          " Red. masses --      1.0828                 1.0451                 1.0817",
          "  Atom  AN      X      Y      Z        X      Y      Z        X      Y      Z"]
    for i in range(3):
        an = 8 if i == 0 else 1
        L.append(f"     {i + 1}   {an}  " + "  ".join(f"{m[i][0]:6.2f} {m[i][1]:6.2f} {m[i][2]:6.2f}" for _, m in modos))
    L += ["", " Zero-point correction=                           0.021134 (Hartree/Particle)",
          " Elapsed time:       0 days  0 hours  0 minutes 12.3 seconds.",
          " Normal termination of Gaussian 16 at Thu Oct  1 09:00:12 2026."]
    escrever("gaussian/SINTETICO_agua.log", "\n".join(L) + "\n")


# ----------------------------------------------------------------------------------------------------------
def gerar_qe():
    alat = 10.2631    # bohr (Si, a = 5.431 Å)
    L = ["", "     Program PWSCF v.7.2 starts on  1Oct2026 at  9: 0: 0 ", "", "     SINTETICO: silício (2 átomos), relax",
         "     bravais-lattice index     =            2", f"     lattice parameter (alat)  =      {alat:.4f}  a.u.",
         "     unit-cell volume          =     270.2508 (a.u.)^3", "     number of atoms/cell      =            2",
         "     number of atomic types    =            1", "     kinetic-energy cutoff     =      30.0000  Ry",
         "     convergence threshold     =      1.0E-08", "     Exchange-correlation= PBE", "",
         "     celldm(1)=  10.263100  celldm(2)=   0.000000  celldm(3)=   0.000000", "",
         "     crystal axes: (cart. coord. in units of alat)",
         "               a(1) = (  -0.500000   0.000000   0.500000 )  ",
         "               a(2) = (   0.000000   0.500000   0.500000 )  ",
         "               a(3) = (  -0.500000   0.500000   0.000000 )  ", "",
         "     PseudoPot. # 1 for Si read from file:", "     ./Si.pbe-n-rrkjus_psl.1.0.0.UPF", "",
         "     atomic species   valence    mass     pseudopotential", "        Si             4.00    28.08550     Si( 1.00)", "",
         "     Cartesian axes", "", "     site n.     atom                  positions (alat units)",
         "         1           Si  tau(   1) = (   0.0000000   0.0000000   0.0000000  )",
         "         2           Si  tau(   2) = (   0.2600000   0.2500000   0.2500000  )", "",
         "     number of k points=     2", "                       cart. coord. in units 2pi/alat",
         "        k(    1) = (  -0.2500000   0.2500000   0.2500000), wk =   0.5000000",
         "        k(    2) = (   0.2500000  -0.2500000   0.7500000), wk =   1.5000000", ""]
    ens = [-15.8401, -15.8416]
    tcpu = 0.5
    for k, E in enumerate(ens):
        n = 7 if k == 0 else 4
        for i in range(1, n + 1):
            tcpu += 0.4
            L += [f"     iteration #{i:3d}     ecut=    30.00 Ry     beta= 0.70", f"     total cpu time spent up to now is        {tcpu:.1f} secs", "",
                  f"     total energy              =     {E + 0.02 * 10 ** (1 - i):.8f} Ry", f"     estimated scf accuracy    <       {0.05 * 10 ** (1 - i):.8f} Ry", ""]
        L += [f"!    total energy              =     {E:.8f} Ry",
              f"     estimated scf accuracy    <          {0.05 * 10 ** (1 - n):.8f} Ry", "", f"     convergence has been achieved in {n:4d} iterations", "",
              "     Forces acting on atoms (cartesian axes, Ry/au):", "",
              f"     atom    1 type  1   force =     {-0.0120 / (k + 1):.8f}    0.00000000    0.00000000",
              f"     atom    2 type  1   force =     {0.0120 / (k + 1):.8f}    0.00000000    0.00000000", "",
              f"     Total force =     {0.0170 / (k + 1):.6f}     Total SCF correction =     0.000010", ""]
        if k == 0:
            L += ["     BFGS Geometry Optimization", "", "ATOMIC_POSITIONS (alat)", "Si            0.0000000000        0.0000000000        0.0000000000",
                  "Si            0.2520000000        0.2500000000        0.2500000000", ""]
    L += ["     bfgs converged in   2 scf cycles and   1 bfgs steps", "     End of BFGS Geometry Optimization", "",
          f"     Final energy   =     {ens[-1]:.10f} Ry", "Begin final coordinates", "", "ATOMIC_POSITIONS (alat)",
          "Si            0.0000000000        0.0000000000        0.0000000000", "Si            0.2520000000        0.2500000000        0.2500000000",
          "End final coordinates", "", "     PWSCF        :      4.52s CPU      5.10s WALL", "", "   This run was terminated on:   9: 0: 5   1Oct2026", "",
          "=------------------------------------------------------------------------------=", "   JOB DONE.",
          "=------------------------------------------------------------------------------="]
    escrever("qe/SINTETICO_si_relax.out", "\n".join(L) + "\n")


def gerar_orca_andamento():
    real = AQUI.parent / "dimero_benzeno" / "calc" / "orca" / "dimero_PD" / "dimero_PD.out"
    if not real.exists():
        print("aviso: rode antes examples/dimero_benzeno/gerar_dados.py (orca)")
        return
    linhas = real.read_text(errors="replace").splitlines()
    corte = [i for i, l in enumerate(linhas) if "GEOMETRY OPTIMIZATION CYCLE   2" in l]
    fim = corte[0] if corte else len(linhas) // 3
    seg = linhas[:fim]
    # avança até o meio do SCF do ciclo 2
    for j, l in enumerate(linhas[fim:fim + 2000]):
        seg.append(l)
        if l.strip().startswith("5 ") and "e-" in l:
            break
    escrever("orca/dimero_PD_em_andamento.out", "\n".join(seg) + "\n")


if __name__ == "__main__":
    gerar_cp2k()
    gerar_vasp()
    gerar_gaussian()
    gerar_qe()
    gerar_orca_andamento()
    print("amostras em", AQUI)
