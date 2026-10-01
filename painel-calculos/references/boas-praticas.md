# Boas práticas científicas ao usar o painel

O painel foi desenhado para que o que aparece na tela possa ser rastreado até um arquivo e um nível de cálculo. Estas
orientações dizem como usá-lo sem enfraquecer essa garantia. Cada regra indica o que o código faz a respeito e o que continua
sendo responsabilidade de quem analisa.

## 0. O painel é somente leitura

O painel **nunca modifica arquivos de cálculo**: lê saídas, trajetórias e JSON, e escreve apenas o HTML (`saida`). Pode ser
apontado para pastas de cálculos em andamento (`painel.py gerar painel.yaml --vigiar 120` regenera a cada 120 s) sem risco para
elas. O HTML é um arquivo único e offline; ele reflete os arquivos **no instante da geração** (veja "Gerado em" no cabeçalho).

## 1. Compare métodos na MESMA geometria (regra C-073)

Uma diferença de energia entre dois métodos (por exemplo, um potencial de aprendizado de máquina e DFT) mistura dois erros: o
da **energia** (o método descreve mal a superfície) e o da **geometria** (cada método otimiza para uma geometria diferente). Para
separá-los:

1. Otimize a geometria com o método A (barato, exploratório).
2. Faça um cálculo de ponto único (*single point*) do método B (a referência) **na geometria do método A**.
3. Compare A e B nessa geometria: a diferença é o erro de energia de A. Compare também B na geometria de B com B na geometria
   de A: a diferença é quanto a geometria importa.

Como expressar no painel: uma variante de `energia` para cada situação, cada uma com seus próprios termos (as variantes não herdam
termos). O exemplo `examples/dimero_benzeno/painel.yaml` tem as variantes "B97-3c (geometria própria)" e "B97-3c na geometria UMA"
e a etapa E5 "DFT na geometria do UMA".

O código **avisa, mas não impede**, a mistura de níveis: se uma expressão (parcela, nível de diagrama ou ranking) combina termos de
selos diferentes, aparece o aviso `C-073 · '<expressão>' <variante> mistura resultados de níveis de cálculo diferentes: ...`
(chave interna `av_mistura`). Tome o aviso como erro de método até prova em contrário. Observe que "número digitado" conta como
um selo próprio, e que uma mudança de versão do programa também muda o selo.

## 2. Rotule o que é exploratório

Resultados de potenciais de aprendizado de máquina (MLIP), de geometrias não validadas ou de testes rápidos são **orientação,
não conclusão**.

- Em `frequencias.sistemas`, `rotulo: EXPLORATÓRIO` (ou um JSON de frequências com `"rotulo": "EXPLORATÓRIO"`) faz o painel exibir o
  banner "EXPLORATÓRIO — resultado preliminar, não é conclusão" e o rótulo ao lado do sistema. Qualquer rótulo contendo "explorat" ativa
  o banner.
- Para estruturas e energias não há banner automático: use `nome_principal` (ex.: "UMA (exploratório)"), `nota:` nas
  estruturas e nas etapas, e o `rotulo:` de topo (aparece no cabeçalho).
- Um MLIP deve ser conferido contra DFT **no seu sistema** (seção 1). Concordância em outros sistemas não vale para o seu.

## 3. Nunca digite números à mão; leia de arquivos

- Energias, geometrias e frequências devem vir dos arquivos de saída (`estrutura:` nos termos) ou de JSON gravado por script
  (`json:` + `caminho:`).
- Números digitados (`valor:` em termos de energia, `referencia: 3.9` em medidas) são aceitos, mas **marcados**: o selo diz "número digitado
  na configuração" e a seção de energia lista quais termos foram digitados e a fonte. Use-os só para valores de literatura e **sempre
  preencha `fonte:`** (sem fonte o painel escreve "sem fonte").
- Ao digitar um valor de literatura, anote a unidade correta (`unidade:`); a conversão para eV depende dela.
- Perfis ilustrativos feitos só com números digitados (como o do exemplo `amostras`) devem dizer isso no título.

## 4. Selo de nível de cálculo em todo resultado

Toda energia mostra "nível · programa versão", **lidos do arquivo de saída**. O que o arquivo não registra aparece como
"não registrado" — nunca um valor presumido.

- Se o selo diz "não registrado", investigue antes de comparar: pode faltar `programa`/`versao`/`modelo` nos metadados da
  estrutura ASE, ou a saída tem impressão reduzida.
- Você pode **declarar** o que falta com `nivel:` (`{nivel, programa, versao}`); o painel marca o selo "declarado na configuração:
  nível, programa, versão". Declare só o que você sabe, e só quando o arquivo realmente não registra.
- Não misture níveis em uma mesma diferença. Se for inevitável (por exemplo, correção de literatura somada a um valor calculado),
  deixe a mistura explícita no título e na `explicacao` da parcela.
- O cartão de métodos mostra, por nível, funcional, base, dispersão, corte, pseudopotenciais, critério de SCF e a linha de comando
  quando existem. Confira-os contra o que você pretendia calcular.
- Cuidado com o que o leitor **pode** deixar passar: por exemplo, o funcional do VASP é deduzido só de `GGA`/`METAGGA` (um híbrido
  seria rotulado "PBE"), e no Gaussian a energia é a do `SCF Done` (não inclui MP2/CC). Veja `leitores.md`.

## 5. Critério de convergência correto para cada programa

"Convergiu" significa coisas diferentes em cada programa, e o painel desenha o SCF contra o critério e a coluna apropriados. Ao
interpretar o gráfico de SCF:

| Programa | Critério | Compare com | Observação |
|---|---|---|---|
| CP2K (OT) | `EPS_SCF` | coluna **Convergence** da tabela de SCF | não compare o critério com o ΔE ("Change"); são grandezas diferentes |
| ORCA | `TolE`, `TolRMSP`, `TolMaxP` | \|ΔE\|, RMS-DP, Max-DP | o ORCA exige todos; o gráfico mostra \|ΔE\| contra `TolE` e informa `TolRMSP` na nota |
| VASP | `EDIFF` | \|dE\| entre iterações eletrônicas | `EDIFFG` (parada iônica) é outro critério e não é lido |
| Gaussian | RMS da matriz densidade solicitado | `RMSDP` | só existe por iteração com `#p` |
| Quantum ESPRESSO | `conv_thr` (Ry) | `estimated scf accuracy` | não é a diferença de energia entre iterações |

Outras regras:

- **SCF convergido ≠ otimização convergida.** A segunda é `convergiu` (e `fmax` final contra o critério de força, `opt_criterio`). O
  ranking descarta, por padrão, estruturas com `convergiu` falso (`so_convergidas: true`); as de convergência *desconhecida* entram.
- Em `fila`, declare `criterio:` ao acompanhar um programa pelo `json_vivo`; sem ele o painel presume o `EPS_SCF = 1e-6` do CP2K
  e avisa na nota.
- A comparação de `fmax` entre programas distintos exige cautela: ASE e VASP dão a maior norma de força por átomo; ORCA, CP2K e Gaussian
  imprimem a maior componente cartesiana.
- A estimativa de tempo restante (ETA) do SCF é um ajuste log-linear das últimas iterações; é uma tendência, não uma previsão.

## 6. BSSE e ZPE: o que as energias do painel não incluem

- As energias de interação e os perfis são **eletrônicos (0 K)**: sem energia de ponto zero, sem entropia e **sem correção do erro de
  superposição de base (BSSE)**, salvo se você produzir esses termos por fora. O texto da seção de energia e o glossário dizem isso.
  Escreva-o também na `explicacao` das parcelas (como no exemplo do dímero de benzeno: "Sem BSSE e sem ZPE").
- Para incluir BSSE (contrapeso, *counterpoise*), faça os cálculos adicionais (dímero e monômeros na base do dímero), leia-os de arquivos
  e monte a parcela por expressão; não digite a correção. Métodos "compostos" (por exemplo, B97-3c) embutem uma correção
  geométrica de BSSE/base, o que também deve constar do texto.
- A ZPE harmônica mostrada nas frequências (`zpe_kJmol`) é **informativa e não é somada automaticamente** às energias. Para ΔE com
  ZPE, defina termos a partir de arquivos de frequência e monte a expressão explicitamente.
- A ZPE estimada do painel soma ½ν das frequências positivas; ela só descarta modos de translação e rotação com |ν| < 0,001 cm⁻¹.
  Em frequências por diferenças finitas, modos residuais pequenos (alguns cm⁻¹) entram na soma: informe `zpe_kJmol` no JSON de
  frequências ou confira o valor.
- Frequências harmônicas e baixas frequências (< 100 cm⁻¹, modos de interação) são sensíveis à geometria, à malha de integração e à
  precisão numérica; trate a ZPE e a entropia delas com reserva.

## 7. Réplicas e partidas múltiplas

Uma otimização local encontra o mínimo mais próximo da partida. Para não confundir "mínimo" com "mínimo mais próximo":

- Rode **várias partidas** por arranjo (por exemplo, a geometria exata e versões perturbadas por ruído de poucos centésimos de Å) e
  nomeie-as com `item` (arranjo) e `replica` (partida), por `padrao:` com grupos nomeados.
- O `ranking` usa a **menor** energia de cada `item` e a barra de erro é `máx − mín` entre as réplicas. Isso é **dispersão entre
  partidas, não incerteza estatística**: com 3 partidas, ela só indica se o resultado depende da partida.
- Uma dispersão grande sugere superfície plana, mínimos diferentes ou critério de força frouxo (`fmax`); olhe os filmes e as
  geometrias de cada partida (seção "Explorador de estruturas") antes de aceitar o melhor.
- Confira que o `item` vencedor não é só a partida mais favorecida: compare as geometrias finais pelas medidas (`medidas`).

## 8. Validação de frequências

- **Geometria estacionária:** frequências imaginárias (abaixo de −20 cm⁻¹ contam em `n_imag`) indicam que a estrutura não é um mínimo
  (ou há ruído numérico). Em MLIPs por diferenças finitas, pequenas imaginárias de baixa frequência são comuns; reotimize com
  critério mais estrito antes de concluir.
- **Contra uma referência** (`referencia:` em `frequencias`): o painel pareia cada valor de referência com a frequência calculada
  positiva **mais próxima** e mostra erro médio absoluto (MAE), máximo e cores segundo `tolerancia` (padrão 30 / 80 cm⁻¹).
  Esse pareamento **não é um-a-um**: duas referências próximas podem cair na mesma frequência calculada. Para modos degenerados ou
  densos, forneça o pareamento explícito (`calc:` por modo, ou `campo_calc` na tabela JSON).
- **Fatores de escala:** o painel **não aplica** fator de escala. Frequências harmônicas costumam superestimar as fundamentais
  experimentais (anarmonicidade), com um desvio sistemático que depende de método e base. Compare com referências **harmônicas** do
  mesmo nível, ou aplique fatores de escala publicados *para o seu nível de teoria* antes de gravar a tabela de referência (e diga
  isso em `fonte:`). Sem isso, o erro mostrado mistura erro do método e anarmonicidade.
- **Fonte da referência:** sempre cite a fonte exata (`fonte:`). Valores de memória ou "aproximados" devem ser conferidos antes de publicar.
- Frequências de dois métodos (`comparar`) pareiam por proximidade acima de 300 cm⁻¹ (ajustável em `acima_de`); o MAE resultante é um
  resumo, não substitui olhar os modos.

## 9. Antes de confiar em um painel

1. Rode `painel.py ler` nos arquivos e compare programa, versão, nível, energia e critério com o que o próprio programa imprimiu.
2. Leia a faixa de **avisos** do painel: arquivos ilegíveis, termos sem energia, misturas de nível (C-073) e glob sem arquivos
   aparecem ali e não impedem a geração.
3. Lembre quais leitores foram validados em saídas reais (ORCA 6.1.1 e ASE/MLIP) e quais só em amostras sintéticas (CP2K, VASP, Gaussian,
   QE): veja `leitores.md`. Para os últimos, confira ao menos uma saída real sua antes de usar números em texto.
4. `id` de estrutura repetido: só o primeiro vale; os seguintes são ignorados com aviso. Mantenha ids únicos.
5. Guarde a configuração (`painel.yaml`) com o projeto: o HTML é reproduzível a partir dela e dos arquivos de saída; corrija a
   configuração, não o HTML.
6. Ao citar um resultado, cite também o selo (nível · programa versão) e a data de geração do painel.
