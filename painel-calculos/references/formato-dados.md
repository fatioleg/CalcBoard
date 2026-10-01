# Formato dos dados

Este arquivo descreve (1) o dicionário comum `R` que todo leitor devolve e (2) os formatos JSON/JSONL que o painel aceita como
entrada: progresso por passo, frequências, resultado genérico, estado ao vivo da fila e registro por estrutura. Tudo foi
derivado de `scripts/painel_lib/leitores.py` e `montar.py`.

Princípio: **um campo que o arquivo não fornece fica `None` (ou vazio); nunca é inventado.** O painel o mostra como "não
registrado".

---

## 1. O dicionário `R` (resultado de um leitor)

`leitores.ler(caminho, formato=None)` detecta o formato, chama o leitor e **nunca levanta exceção**: arquivo inexistente vira
`estado: "ausente"`; leitura que falha vira `estado: "ilegivel"` com um aviso. Para ver o `R` de um arquivo:
`python painel.py ler ARQUIVO`.

| Chave | Tipo | Significado |
|---|---|---|
| `arquivo` | texto | caminho lido |
| `programa` | texto \| None | "ORCA", "CP2K", "VASP", "Gaussian", "Quantum ESPRESSO (pw.x)", ou o nome do calculador ASE / campo `programa` do arquivo |
| `versao` | texto \| None | versão registrada na saída |
| `nivel` | dict | nível de cálculo; chaves possíveis (todas opcionais): `metodo` (texto-resumo, base do selo), `funcional`, `dispersao`, `base`, `pseudo`, `corte`, `scf` (OT/diagonalização), `linha` (linha de comando ORCA/Gaussian), `hessiana`, `tarefa`, `modelo`, `fonte` (quando lido de um `.inp`) |
| `tipo` | texto \| None | `sp`, `opt`, `opt-celula`, `opt+freq`, `freq`, `md`, `estrutura` (arquivo só com geometria); outro valor do programa é repassado |
| `estado` | texto | `concluido`, `falhou`, `rodando?`, `desconhecido`, `ilegivel`, `ausente`. `rodando?` ("sem marca de fim") é convertido em `rodando` ou `parado` por `estado_final()` conforme a idade do arquivo contra `ativo_s` |
| `avisos` | lista de texto | problemas de leitura (aparecem na faixa de avisos do painel) |
| `energia_eV` | float \| None | energia total final, em **eV** |
| `quadros` | lista | geometrias (ver 1.1); a última é a final |
| `scf` | lista | iterações do **último** ciclo SCF (ver 1.2) |
| `scf_unidade_E` | texto | unidade de `E` em `scf`: `Ha`, `Eh`, `Ry` ou `eV` (existe quando há `scf`) |
| `scf_criterio` | dict \| None | `{nome, valor, coluna, nota}`: critério de convergência do SCF e **qual coluna comparar** com ele |
| `scf_convergiu` | bool \| None | o SCF terminou convergido? |
| `n_ciclos_scf` | int | quantos ciclos SCF a saída contém |
| `freq` | dict \| None | frequências (ver 1.3) |
| `inicio`, `fim` | float \| None | instantes (época, s). `fim` costuma ser o `mtime` do arquivo quando há marca de término normal |
| `duracao_s` | float \| None | duração do cálculo, em s |
| `mtime` | float \| None | data de modificação do arquivo |
| `carga`, `mult` | int \| None | carga e multiplicidade |
| `convergiu` | bool \| None | a **otimização de geometria** convergiu? `None` = o arquivo não diz |
| `opt_criterio` | dict \| None | `{nome, valor_EhBohr, valor_eVA}`: tolerância de força da otimização |
| `extra` | dict | `notas` (lista de avisos informativos, ex.: "quadros lidos de ..._trj.xyz"), `rotulo`, `validacao` (do JSON de frequências), `tolRMSP`, `n_ciclos_opt`, `parcial` (modos só de parte dos átomos) |

Só para arquivos `.jsonl`, `R` traz também `progresso` (ver 2.1).

### 1.1 Cada quadro de `quadros`

| Campo | Tipo | Significado |
|---|---|---|
| `simbolos` | lista de texto | símbolos químicos |
| `pos` | array (N, 3) | posições em Å |
| `celula` | array (3, 3) \| None | vetores da célula em Å, em linhas; `None` se ausente ou de determinante ~0 |
| `pbc` | bool | periódico? (padrão: há célula) |
| `E_eV` | float \| None | energia do quadro, em eV |
| `fmax` | float \| None | força máxima, em eV/Å (ver o aviso abaixo) |
| `sigma_GPa` | float \| None | tensão máxima (maior \|componente\| de Voigt), em GPa |
| `t` | | reservado (normalmente `None`) |

> Atenção: `fmax` **não é a mesma grandeza em todos os programas**. Para ASE e VASP é o maior módulo de força de um átomo; para
> ORCA ("MAX gradient"), Gaussian ("Maximum Force") e CP2K ("Max. gradient") é a maior componente cartesiana, convertida para
> eV/Å. Não compare `fmax` entre programas diferentes sem levar isso em conta.

### 1.2 Cada iteração de `scf`

`{it, E, dE, conv, t_s}` (ORCA acrescenta `rmsdp`). `E` está na unidade de `scf_unidade_E`. **O significado de `conv` depende
do programa** e é o que se compara com `scf_criterio.valor`:

| Programa | `conv` | `scf_criterio` |
|---|---|---|
| ORCA | \|ΔE\| (Eh) | `TolE` (o ORCA exige também `TolRMSP`/`TolMaxP`; guardado em `extra.tolRMSP`) |
| CP2K | coluna `Convergence` (com OT) | `EPS_SCF` |
| VASP | \|dE\| entre iterações (eV) | `EDIFF` |
| Gaussian | `RMSDP` (só há com `#p`) | `RMS density matrix` solicitado |
| Quantum ESPRESSO | `estimated scf accuracy` (Ry) | `conv_thr` |

### 1.3 `freq`

| Campo | Significado |
|---|---|
| `freqs_cm1` | frequências em cm⁻¹, em ordem crescente; imaginárias negativas |
| `modos` | `[modo][átomo][x,y,z]` normalizados a 1 sobre os átomos deslocados, ou `None` |
| `simbolos`, `pos` | átomos e posições (Å) para animar os modos |
| `idx` | índices dos átomos (na estrutura completa) a que os modos se referem; padrão `0..N-1` |
| `celula` | célula, se houver |
| `n_imag` | nº de frequências abaixo de −20 cm⁻¹ |
| `zpe_kJmol` | energia de ponto zero: ½ Σ ν (positivas, descontados os modos de translação/rotação) em kJ/mol, ou o valor dado pelo arquivo |

Nota: o desconto dos modos de translação/rotação conta frequências com \|ν\| < 0,001 cm⁻¹ (ou o número que o leitor informar).
Em frequências calculadas por diferenças finitas (valores pequenos, mas diferentes de zero), esses modos não são descontados:
informe `zpe_kJmol` no JSON de frequências quando tiver o valor correto.

---

## 2. Formatos JSON/JSONL aceitos como entrada

### 2.1 Progresso por passo (`.jsonl`, chave `progresso` de uma estrutura ou de um filme)

Um objeto JSON por linha, uma linha por passo da otimização. Linhas ilegíveis são ignoradas. Para cada campo, o primeiro nome
existente vale:

| Campo | Nomes aceitos |
|---|---|
| passo | `passo`, `step` |
| fase | `fase`, `phase` |
| energia (eV) | `E_eV`, `energy_eV`, `energia_eV`, `energy`, `E` |
| força máxima (eV/Å) | `fmax_eVA`, `fmax`, `fmax_eV_A` |
| tensão máxima (GPa) | `sigma_max_GPa`, `stress_GPa`, `sigma_GPa`, `stress` |
| instante | `quando`, `time`, `timestamp` |
| tempo decorrido (s) | `t_s`, `elapsed_s` |

Linha final (marca de término): um objeto com `fim`, `end` ou `done` verdadeiro. O painel também usa dessa linha, se existirem,
`convergiu`, `passos` e `tempo_s`. Sem a linha final, a otimização é considerada em andamento (`rodando` se o arquivo mudou há
menos de `ativo_s` segundos, senão `parado`).

```jsonl
{"passo": 0, "E_eV": -6319.2120, "fmax_eVA": 0.1999, "t_s": 95.1, "quando": "2026-10-01T12:24:41"}
{"passo": 1, "E_eV": -6319.2166, "fmax_eVA": 0.1812, "t_s": 95.5}
{"fim": true, "convergiu": true, "passos": 1, "tempo_s": 95.5}
```

### 2.2 Frequências (`.json`)

Reconhecido por conter a chave `freqs_cm1`. É o formato para frequências de MLIPs ou de qualquer cálculo que não tenha leitor
próprio.

| Chave | Tipo | Obrigatória | Significado |
|---|---|---|---|
| `freqs_cm1` | lista de número | sim | frequências em cm⁻¹ (imaginárias negativas) |
| `modos` | `[modo][átomo][3]` | não | deslocamentos (sem eles não há animação) |
| `simbolos` | lista | não | símbolos dos átomos |
| `posicoes` | `[átomo][3]` | não | posições em Å |
| `indices_deslocados` | lista de int | não | átomos a que `modos` se refere |
| `celula` | 3×3 | não | célula, em Å |
| `zpe_kJmol` | número | não | ZPE; se faltar, é estimada das frequências |
| `metodo` | dict | recomendado | `programa` (ou `software`), `versao` (ou `version`), `modelo`, `metodo`, `funcional`, `tarefa`, e quaisquer outras chaves de texto (viram campos do cartão de métodos). Alimenta o selo |
| `rotulo` | texto | não | etiqueta, ex.: `"EXPLORATÓRIO"` |
| `validacao` | | não | lida e guardada em `extra.validacao`; hoje não é exibida |
| `n_imaginarias` | int | não | **ignorada**: o painel recalcula (frequências < −20 cm⁻¹) |

Sem `metodo`, o selo mostra "não registrado". O estado é sempre `concluido`; tipo `freq`.

### 2.3 Resultado genérico (`.json`)

Reconhecido por conter `energia_eV`, `energia_Ha` ou `energy_eV`. Serve para registrar um cálculo de um programa sem leitor.

| Chave | Aliases | Significado |
|---|---|---|
| `energia_eV` | `energy_eV`; ou `energia_Ha` (convertida) | energia total |
| `programa`, `versao` | `program`, `version` | selo |
| `nivel` | `level` | texto (vira `metodo`) ou dict |
| `estado` | `status` | padrão `concluido` |
| `convergiu` | `converged` | |
| `estrutura` | `structure` | arquivo de geometria **ao lado do JSON** (lido pelo ASE; vale o último quadro) |

Um JSON sem nenhuma dessas chaves gera o aviso "JSON sem esquema reconhecido (freqs_cm1 / energia_eV / energia_Ha)".

### 2.4 Estado ao vivo da fila (`json_vivo`)

Arquivo escrito por um script externo (por exemplo, o que consulta um servidor remoto) e relido a cada geração.

| Chave | Significado |
|---|---|
| `quando` | `"AAAA-MM-DD HH:MM:SS"`, instante da consulta (hora local) |
| `fila_log` | lista de linhas de log; as 10 últimas são mostradas |
| `jobs` | lista de jobs (abaixo) |

Cada job:

| Chave | Significado |
|---|---|
| `job` (ou `nome`) | nome |
| `estado` (ou `status`) | `ok`/`done`/`concluido`, `rodando`/`running`, `falhou`/`failed`, `pendente`/`pending`; outro valor é repassado |
| `scf` | lista de linhas `[iteração, energia, dE, convergência, tempo_s]` (as três últimas colunas são opcionais) |
| `scf_convergiu` | 0/1 |
| `abortou` | bool |
| `energia_Ha` | energia total em hartree (texto ou número) |
| `walltime` | linhas de texto; uma `START <dia> <Mês> <dd> <hh:mm:ss> ...` permite calcular o tempo decorrido contra `quando` |

Exemplo mínimo:

```json
{"quando": "2026-10-01 09:30:00",
 "jobs": [{"job": "sp_01", "estado": "rodando", "scf": [[1, -120.10, -120.10, 0.081], [2, -120.31, -0.21, 0.023]],
           "scf_convergiu": 0, "energia_Ha": null}],
 "fila_log": ["09:10 sp_01 iniciado"]}
```

O critério de convergência vem de `criterio` na entrada `fila:` da configuração; sem ele, presume-se o `EPS_SCF = 1e-6` do CP2K,
e o painel diz isso explicitamente. O estimador de tempo restante ajusta uma reta a log₁₀(convergência) × iteração nas últimas
4 e 8 iterações e só produz estimativa se a convergência estiver decaindo.

### 2.5 Registro por estrutura (`registro:`)

JSON (dicionário) que complementa o que o arquivo de saída não diz. Chaves lidas (a primeira existente vale):

| Campo | Chaves aceitas |
|---|---|
| convergência da otimização | `convergiu`, `converged` |
| passos | `passos`, `steps`, `n_passos` |
| duração (s) | `tempo_s`, `duracao_s`, `elapsed_s` |

Só é usado quando o leitor (e a linha final do `.jsonl`) não trouxeram o dado.

### 2.6 Metadados em arquivos de estrutura ASE (extxyz / traj)

Em `atoms.info` (linha de comentário do extxyz), o leitor ASE procura:

| Papel | Chaves |
|---|---|
| programa | `programa`, `program`, `software`, `calculator`, `calculador` (na falta, o nome do calculador anexado) |
| versão | `versao`, `version` |
| nível | `nivel`, `level`, `metodo`, `method`, `modelo`, `model`, `funcional`, `functional`, `tarefa`, `task`, `base`, `basis` |
| otimização convergiu | `convergiu` (bool) |

Gravar essas chaves ao salvar a estrutura é a forma de o selo de nível sair completo para resultados de MLIPs, sem declarar nada
na configuração.
