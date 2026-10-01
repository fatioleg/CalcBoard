# Leitores: o que é extraído de cada programa

Os leitores ficam em `scripts/painel_lib/leitores.py`. Cada um recebe um arquivo e devolve o dicionário comum `R`
(`formato-dados.md`). Para ver o que um leitor extrai de um arquivo seu: `python painel.py ler ARQUIVO [ARQUIVO...]`
(`--formato` força o leitor).

## Regras que valem para todos

- **Somente leitura.** Os leitores abrem os arquivos para leitura; o painel nunca modifica arquivos de cálculo.
- **Falha não derruba a geração.** Se um leitor lança exceção, `ler()` a captura e devolve `estado: "ilegivel"` com o aviso
  "<arquivo>: não consegui ler (<tipo do erro>: ...)"; arquivo inexistente vira `estado: "ausente"`. O aviso aparece na faixa
  "Avisos da leitura" do painel e o resto é gerado normalmente. Um glob sem arquivos também só gera aviso.
- **Nada é inventado.** O que o arquivo não traz fica `None`, e o painel escreve "não registrado". Só a configuração (`nivel:`)
  pode preencher uma lacuna, e então o selo diz "declarado na configuração".
- **Estado pelo conteúdo e pela idade.** Marca de término normal do programa = `concluido`; marca de erro = `falhou`; sem
  nenhuma das duas = "rodando?", que vira `rodando` ou `parado` conforme a última modificação do arquivo contra `ativo_s`.
- **Energias em eV** em `energia_eV` e nos quadros; o SCF fica na unidade do programa (`scf_unidade_E`).
- **Dependências:** numpy sempre; o pacote `ase` é necessário para extxyz/traj/cif/POSCAR, `vasprun.xml` e para as geometrias do
  Quantum ESPRESSO (sem ele, esses casos viram aviso, não quebra); PyYAML para configurações `.yaml`.

## Quais leitores foram testados com saídas reais

| Leitor | Base de teste | Situação |
|---|---|---|
| ORCA 6.1.1 (`.out`, `_trj.xyz`, `.hess`) | saídas **reais** de B97-3c Opt Freq TightSCF (benzeno e dímero), em `examples/dimero_benzeno/calc/orca/`, e um trecho real truncado em `examples/amostras/orca/` | testado em saídas reais |
| ASE: extxyz e traj de MLIP (UMA, fairchem-core 2.22) | arquivos **reais** em `examples/dimero_benzeno/calc/uma/` | testado em saídas reais |
| JSON de frequências de MLIP e JSONL de progresso | arquivos **reais** do mesmo exemplo | testado em saídas reais |
| CP2K (`.out` + `-pos-1.xyz`) | `examples/amostras/cp2k/*/SINTETICO_*` | **sintético** |
| VASP (`OUTCAR` + `OSZICAR`) | `examples/amostras/vasp/si_relax/` (gerado por `gerar_amostras.py`; os nomes não levam o prefixo SINTETICO) | **sintético** |
| Gaussian 16 (`.log`) | `examples/amostras/gaussian/SINTETICO_agua.log` | **sintético** |
| Quantum ESPRESSO `pw.x` | `examples/amostras/qe/SINTETICO_si_relax.out` | **sintético** |
| CP2K Molden (`-VIBRATIONS-*.mol`), `vasprun.xml`, frequências do OUTCAR (IBRION 5-8), `OSZICAR` isolado, cif/POSCAR | nenhuma amostra | **sem teste** |
| JSON de resultado genérico | casos construídos nos testes automáticos | testado só com dados construídos |

As amostras sintéticas têm **números inventados** com o *leiaute* imitando a saída de cada programa nas partes que o leitor usa
(`examples/amostras/gerar_amostras.py`). Elas provam que o leitor lê aquele leiaute e que não quebra; **não** provam que ele
funciona em toda saída real, em outras versões do programa ou em opções de impressão diferentes. Antes de confiar num número
de CP2K, VASP, Gaussian ou QE, rode `painel.py ler` na sua saída e compare energia, nível e critério com o que o próprio programa
imprimiu. Nada nas amostras sintéticas é resultado científico.

## Detecção

Pelo nome e, para `.out`, `.log`, `.txt`, `.pwo`, `.stdout` e arquivos sem extensão, pelo conteúdo (primeiros ~300 kB):

| Critério | Leitor |
|---|---|
| `.jsonl` / `.json` | progresso / JSON (frequências ou resultado genérico) |
| `.hess` | ORCA `.hess` |
| `*-VIBRATIONS-N.mol` ou `.mol` com `[FREQ]` | CP2K Molden |
| nome `OUTCAR*` / `OSZICAR*` / `vasprun*.xml` | VASP |
| texto contém "O R C A" ou "Program Version ... RELEASE" | ORCA |
| texto contém `CP2K|` | CP2K |
| "Entering Gaussian System" ou "Gaussian, Inc." | Gaussian |
| "Program PWSCF" | Quantum ESPRESSO |
| linha `vasp.N...` | VASP OUTCAR com outro nome |
| `*_trj.xyz` / `*-pos-N.xyz` | quadros xyz de ORCA / CP2K |
| qualquer outro | ASE (que adivinha o formato pelo nome/extensão) |

Um `.out` que não casa com nenhum programa cai no ASE e, falhando, vira "não consegui ler".

---

## ORCA (testado em saídas reais, versão 6.1.1)

- **Detecção:** cabeçalho do ORCA. **Versão:** `Program Version`.
- **Nível:** lido das linhas `!` do *eco do input* na própria saída (`|  1> ! B97-3c Opt Freq TightSCF`). O que não é palavra de
  tarefa/controle conhecida (`Opt`, `Freq`, `TightSCF`, `PAL4`...) vira o "método" do selo (`B97-3c`); a linha inteira fica em
  `nivel.linha`. Carga e multiplicidade vêm do bloco de entrada.
- **Tipo:** `opt`, `freq`, `opt+freq` ou `sp`, pelas palavras-chave.
- **Geometrias e energias:** blocos `CARTESIAN COORDINATES (ANGSTROEM)`, uma por ciclo; `FINAL SINGLE POINT ENERGY` por ciclo
  (a última é `energia_eV`); `MAX gradient` convertido a eV/Å para `fmax`. Se existir `<nome>_trj.xyz` ao lado com **mais**
  quadros, ele substitui os quadros do `.out` (nota registrada em `extra.notas`).
- **SCF:** iterações do último bloco (E, ΔE, RMS-DP, tempo). Critério `TolE`, comparado com |ΔE|; `TolRMSP` fica em
  `extra.tolRMSP`.
- **Forças:** blocos `CARTESIAN GRADIENT` (Eh/bohr, impressos com `EnGrad`/`Opt`) viram forças em eV/Å (força = −gradiente) no
  quadro do ciclo correspondente; sem bloco, usa `<nome>.engrad` ao lado. Testado em saídas reais de B97-3c `EnGrad`
  (`examples/dimero_benzeno/calc/orca/sp_na_geometria_uma/`).
- **Convergência da otimização:** "THE OPTIMIZATION HAS CONVERGED" (sim) ou "did not converge but reached the maximum number"
  (não). **Duração:** `TOTAL RUN TIME`.
- **Término:** "ORCA TERMINATED NORMALLY" = concluído; "error termination", "ABORTING THE RUN" ou "ERROR !!!" = falhou.
- **Frequências:** se houver um `.hess` com o mesmo nome-base, ele tem prioridade (frequências e modos normais completos; se
  as do `.out` discordarem, há aviso). Sem `.hess`, lê `VIBRATIONAL FREQUENCIES` e `NORMAL MODES` do `.out`. O `.hess` isolado
  também é lido (sem programa, versão nem nível: o selo ficará "não registrado" a menos que se declare `nivel:`).
- **Limitações:** só as linhas `!` entram no nível (blocos `%` como `%scf`, `%method` e `%basis` não são lidos); palavras de
  base/solvente/auxiliares aparecem juntas no "método" e palavras novas do ORCA que não estejam na lista de tarefas também
  entram nele. Arquivos com vários *jobs* (`$new_job`), varreduras relaxadas, NEB e IRC não têm tratamento próprio
  e não foram testados (vale a última energia final encontrada). Outras versões (5.x, 4.x) não foram testadas. `fmax` é a maior componente do
  gradiente, não a norma da força por átomo.

## CP2K (testado só em amostra sintética)

- **Detecção:** linhas `CP2K|`. **Versão:** `CP2K| version string`. **Tipo:** `GLOBAL| Run type` (`GEO_OPT`, `CELL_OPT`, `MD`,
  `ENERGY`...).
- **Nível:** da saída (`FUNCTIONAL|`, `DFT-D3`, `Orbital Basis Set`, `Potential information`, corte de densidade convertido em Ry,
  OT ou diagonalização). Se a saída tem nível de impressão baixo e não traz o funcional, tenta o `<projeto>.inp` ao lado
  (funcional, dispersão, bases, `CUTOFF`, `EPS_SCF`); nesse caso registra a origem em `nivel.fonte` e em `extra.notas`.
- **Geometria:** a saída principal só traz a geometria **inicial** (bloco `ATOMIC COORDINATES IN ANGSTROM`) e a célula
  (`CELL| Vector a/b/c`). Para otimizações, o painel lê os quadros de `<projeto>-pos-*.xyz` na mesma pasta (energia em
  `E = ...` do comentário, em Ha). **Sem esse arquivo, a estrutura mostra só a geometria inicial**; guarde-o junto da saída.
- **Energia:** última linha `ENERGY| Total FORCE_EVAL`. **SCF:** tabelas `Step Update method Time Convergence Total energy Change`
  (último ciclo); critério `EPS_SCF` comparado com a coluna **Convergence**, não com a última coluna (ΔE).
- **Estado:** `PROGRAM ENDED AT` = concluído; porém "SCF run NOT converged" torna o estado `falhou` com aviso; `ABORT`/`ERROR`/
  `CPASSERT failed` = falhou; sem marca de fim = rodando?. **Duração:** `PROGRAM STARTED/ENDED AT`.
- **Frequências:** arquivo Molden `<projeto>-VIBRATIONS-*.mol` ao lado (sem amostra de teste).
- **Limitações:** o alinhamento entre `Max. gradient` e os quadros do `-pos-` (para `fmax` por quadro) não foi verificado em saída
  real. Só o primeiro `-pos-*.xyz` (ordem alfabética) é usado. MD, BAND e reinícios não têm tratamento específico. Funcionais
  híbridos e correções além de D2/D3 não são identificados como tal, só pelo que `FUNCTIONAL|` imprime.

## VASP (testado só em amostra sintética)

- **Detecção:** nome `OUTCAR*` (ou linha `vasp.N`), `OSZICAR*`, `vasprun*.xml`.
- **OUTCAR:** versão (`vasp.6.x`); parâmetros `GGA`/`METAGGA`, `ENCUT`, `EDIFF`, `IBRION`, `ISIF`, `IVDW` e títulos `POTCAR` formam o
  nível. Elementos por `VRHFIN` e `ions per type`. Por passo iônico: posições, forças (`fmax` = maior módulo de força), célula,
  tensão (`in kB`, máxima em GPa) e energia. **A energia usada é `energy(sigma->0)`** (a "sem entropia"); só na falta dela, `TOTEN`.
  Tipo por `IBRION` (-1 sp; 1-3 opt; 5-8 freq; 0 md; `ISIF` ≥ 3 = `opt-celula`).
- **SCF:** vem do `OSZICAR` ao lado (iterações do último passo iônico); critério `EDIFF`, comparado com |dE| entre iterações
  eletrônicas.
- **Término:** "General timing and accounting" = concluído; "VERY BAD NEWS", "internal error" ou "ZBRENT: fatal" = falhou.
  Convergência da otimização: "reached required accuracy". **Duração:** `Elapsed time (sec)`.
- **vasprun.xml:** lido via ASE (energia e quadros); só o funcional (`GGA`) entra no nível; sem SCF.
- **Frequências do OUTCAR** (IBRION 5-8): implementadas, sem amostra de teste.
- **Limitações importantes:** o funcional é deduzido só de `GGA`/`METAGGA` — um cálculo híbrido (HSE, PBE0) ou com `+U`
  **não é identificado**: um `GGA = PE` com `LHFCALC = .TRUE.` seria rotulado "PBE". Confira o `INCAR` e declare `nivel:` quando
  o OUTCAR não bastar. Magnetização, spin e `KPOINTS` não são lidos. O `OSZICAR` precisa ter o nome `OSZICAR` e estar ao lado.

## Gaussian (testado só em amostra sintética, Gaussian 16)

- **Detecção:** "Entering Gaussian System" / "Gaussian, Inc.". **Versão:** `Gaussian 16: ES64L-G16RevC.01`.
- **Nível:** da *rota* (linha `#...` entre tracejados): o primeiro item com `/` que não seja `opt`, `freq`, `scf` ou `int`
  (`B3LYP/6-31G(d)`); `EmpiricalDispersion=` vira dispersão; a rota inteira fica em `nivel.linha`. Carga e multiplicidade de
  `Charge = ... Multiplicity = ...`.
- **Geometrias:** `Standard orientation` (senão `Input orientation`), com energias `SCF Done` e `Maximum Force` por passo.
  Quadros finais sem energia (repetição da geometria em jobs de frequência) são descartados.
- **SCF por iteração:** só existe se a rota usa `#p` (linhas `E= ... Delta-E=` e `RMSDP=`); sem ele, o gráfico de SCF fica vazio.
  Critério: "Requested convergence on RMS density matrix", comparado com RMSDP.
- **Término:** "Normal termination" sem "Error termination" = concluído. **Otimização:** "Optimization completed" /
  "Stationary point found".
- **Frequências:** blocos `Frequencies --` (último conjunto "Harmonic frequencies"), com os modos; ZPE calculada das
  frequências, sem descontar nenhum modo (o Gaussian já exclui translações e rotações).
- **Limitações:** **a energia é a do último `SCF Done`**: para MP2, CCSD(T), composto (G4, CBS) ou DFT duplo-híbrido, a energia
  correlacionada final **não** é lida. Métodos escritos sem `/` (`# B3LYP 6-31G(d)`) ficam sem nível ("não registrado"). Energias de
  *scan*, IRC e ONIOM não têm tratamento próprio. A *standard orientation* pode girar a molécula entre passos (o painel
  sobrepõe os quadros ao desenhar o filme).

## Quantum ESPRESSO, pw.x (testado só em amostra sintética, v7.2)

- **Detecção:** "Program PWSCF". **Versão e início:** `Program PWSCF vX starts on ...`.
- **Nível:** `Exchange-correlation` (primeiro token), `kinetic-energy cutoff`, pseudopotenciais (`PseudoPot. # n ... read from
  file`), dispersão (D2/D3 se citada). **Tipo:** `calculation` (`scf`, `relax`, `vc-relax`, `md`).
- **Energia:** linhas `!    total energy` em Ry, convertidas para eV. **SCF:** `total energy` por iteração e
  `estimated scf accuracy`; critério `conv_thr` comparado com a `estimated scf accuracy`. O tempo por iteração sai de
  `total cpu time spent up to now`.
- **Geometrias: precisam do ASE** (`espresso-out`). Sem ASE (ou se o ASE falhar), a energia e o SCF são lidos e o painel avisa
  "geometrias não lidas pelo ASE"; a estrutura fica sem geometria e é pulada nas seções que a exigem.
- **Término:** "JOB DONE." = concluído; "Error in routine" ou `%%%%` = falhou. Otimização: "End of BFGS Geometry Optimization".
  **Duração:** `PWSCF : ... CPU ... WALL`.
- **Limitações:** só `pw.x` (não `ph.x`, `cp.x` etc.); `+U`, magnetização e funcionais híbridos não são tratados como tal;
  a dispersão é só detectada por texto.

## ASE: extxyz, traj, cif, POSCAR/CONTCAR, xyz... (testado em saídas reais de MLIP: UMA/fairchem-core)

Qualquer arquivo não reconhecido como saída de programa é lido com `ase.io.read(caminho, ":")` (todos os quadros).

- **Extraído:** posições, células, `pbc`; energia do calculador anexado (`SinglePointCalculator`) ou de `info["energy"]`; forças →
  `fmax` (maior módulo por átomo); tensão → `sigma_GPa` (eV/Å³ × 160,2177). Tipo `opt` se há mais de um quadro, senão
  `estrutura`. **Estado: sempre `concluido`** (um `.traj` ainda em gravação também parece concluído; use `progresso:` para
  acompanhar o andamento).
- **Programa e nível** vêm de `atoms.info` (campo de comentário do extxyz), ver `formato-dados.md` §2.6: `programa`/`software`/
  `calculator`, `versao`, `modelo`/`metodo`/`funcional`/..., `tarefa`/`task`, `convergiu`. Se faltarem, o selo mostra "não registrado".
  Um `.traj` sem esses metadados não recebe nível inventado (coberto pelo teste automático `test_traj_sem_nivel_nao_inventa`).
- **Sem energia:** cif, POSCAR e xyz simples não trazem energia; a estrutura aparece, mas nenhum termo de `energia` pode usá-la.
- **Não testados:** cif e POSCAR/CONTCAR (dependem só do ASE).
- **Limitação:** o leitor não conhece o calculador que gerou o arquivo; a qualidade do selo depende de você gravar `programa`,
  `versao`, `modelo` e `tarefa` na estrutura.

## xyz de trajetória (ORCA `_trj.xyz`, CP2K `-pos-N.xyz`)

Lidos por um leitor próprio e tolerante ao comentário; energia extraída de `E = <valor>` (em Ha → eV). Estado
`desconhecido`; só geometrias. Normalmente entram por `trajetoria:` ou automaticamente ao lado de uma saída ORCA/CP2K.

## JSON e JSONL genéricos

- `.jsonl`: progresso por passo (`formato-dados.md` §2.1). Não traz geometria; use-o em `progresso:`.
- `.json` com `freqs_cm1`: frequências (§2.2); com `energia_eV`/`energia_Ha`/`energy_eV`: resultado genérico (§2.3); qualquer outro
  esquema levanta "JSON sem esquema reconhecido ..." e vira aviso.
- São os caminhos para programas sem leitor próprio (por exemplo, calcular com outro código e gravar um JSON com a energia e o
  `nivel`).

## Convenções de unidade e comparabilidade

- `fmax` não é a mesma grandeza entre programas (norma da força por átomo no ASE/VASP; maior componente no ORCA, CP2K e
  Gaussian).
- O SCF é mostrado na unidade do programa: Eh (ORCA, Gaussian), Ha (CP2K), Ry (QE), eV (VASP).
- O critério de SCF de cada programa compara uma **coluna diferente** (tabela em `formato-dados.md` §1.2); o painel mostra a
  coluna correta junto do critério, e o nome e a nota do critério aparecem no cartão de métodos.

## Forças e tensão por programa (para `forcas`)

| Leitor | Forças (`F`, eV/Å) | Tensão (`S`, GPa) |
|---|---|---|
| ORCA | `CARTESIAN GRADIENT` (−gradiente) ou `.engrad` ao lado; testado em saídas reais | — |
| ASE (extxyz, traj, `espresso-out`, vasprun...) | `get_forces` (sem aplicar restrições), se houver calculador | `get_stress`, Voigt do ASE |
| VASP (`OUTCAR`) | `TOTAL-FORCE` de cada passo | `in kB` convertido ao sinal do ASE (como o próprio leitor do ASE) |
| CP2K | `ATOMIC FORCES in [a.u.]` (forças, Ha/bohr): um bloco por quadro, ou só o último quadro se os números não coincidem | — |
| Gaussian | `Forces (Hartrees/Bohr)` **somente com `NoSymm`** na rota (sem isso a orientação do bloco é incerta e as forças são recusadas) | — |

Forças só são comparadas entre dois cálculos se os átomos, a ordem e a geometria coincidem (`forcas.tol_geom`): outra orientação
(por exemplo, de um programa que reorienta a molécula) é recusada com aviso em vez de gerar um erro falso.
