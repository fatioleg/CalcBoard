# Formato da configuração (`painel.yaml`)

A configuração é um arquivo YAML (ou JSON com as mesmas chaves; YAML exige PyYAML). Tudo é opcional: cada seção do painel só
aparece se houver dado para ela. Um modelo comentado está em `assets/painel_modelo.yaml` (`painel.py init`); exemplos completos
em `examples/dimero_benzeno/painel.yaml` (dados reais) e `examples/amostras/painel.yaml` (amostras sintéticas, em inglês).

Convenções gerais

- **Caminhos** são relativos à pasta da configuração (ou a `raiz`), aceitam `~` e, onde indicado, *glob* (`*`, `?`, `[...]`,
  `**`). Um glob sem resultado gera aviso; nunca erro.
- **Somente leitura:** nenhuma chave faz o painel escrever em arquivos de cálculo. A única saída é o HTML (`saida`).
- **Energias** são lidas dos arquivos em eV (ou convertidas para eV) e só então convertidas para a unidade de exibição.
- **Selo do nível de cálculo:** toda energia carrega "nível · programa versão", lido do arquivo. O que o arquivo não registra
  aparece como "não registrado" ou, se você o declarou (`nivel:`), como "declarado na configuração". Nada é inventado.
- **Números digitados** (`valor:`, `referencia: 3.9`) são marcados como "número digitado na configuração" no painel.
- Uma chave desconhecida é ignorada em silêncio (não há validação de esquema): confira a grafia.

Sumário das chaves de topo

| Chave | Tipo | Padrão | Resumo |
|---|---|---|---|
| `titulo`, `subtitulo` | texto | "Painel dos cálculos" / nenhum | cabeçalho |
| `lang` | `pt` \| `en` | `pt` | idioma da interface e dos avisos |
| `unidade` | texto | `kJ/mol` | unidade inicial de energia |
| `recarga_s` | int | `120` | recarga automática da página (0 desliga) |
| `ativo_s` | número | `1800` | limiar "rodando" × "parado" |
| `saida` | caminho | `painel.html` | HTML gerado |
| `raiz` | caminho | `.` | base dos caminhos |
| `id`, `rotulo` | texto | slug do título / nenhum | chave de memória do navegador; etiqueta no cabeçalho |
| `componentes` | lista | automático | colorir/agrupar moléculas |
| `estruturas` | lista | `[]` | cálculos com geometria |
| `reacao` | dict | pelos `papel` | reagentes / produtos / TS |
| `filmes` | lista | `[]` | trajetórias extras |
| `etapas` | lista | `[]` | "você está aqui" |
| `energia` | dict | nenhum | diagramas e parcelas |
| `ranking` | lista | `[]` | energias relativas |
| `forcas` | dict/lista | nenhum | erro de força por átomo entre dois métodos (seção 13) |
| `validacao` | dict | padrão | faixas de qualidade e textos da validação (seção 14) |
| `comparacao_energia` | lista | `[]` | energia relativa entre dois métodos (seção 15) |
| `regras` | lista | `[]` | cartões de regra de decisão (seção 16) |
| `ressalvas` | lista | `[]` | avisos de limitação por seção, estrutura ou resultado (seção 17) |
| `medidas` | lista | `[]` | medidas geométricas |
| `grupos` | dict | `{}` | seleções de átomos nomeadas |
| `frequencias` | dict/lista | nenhum | vibrações |
| `comparar_frequencias` | lista | `[]` | alternativa a `frequencias.comparar` |
| `fila` | lista | `[]` | cálculos externos / ao vivo |
| `metodos`, `maquina` | lista / texto | nenhum | cartões declarados |
| `glossario`, `glossario_padrao` | dict / bool | `true` | glossário |
| `secoes`, `textos` | lista / dict | todas | ordem das seções; introduções |

---

## 1. Chaves de topo

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `titulo` | texto | "Painel dos cálculos" (en: "Calculation dashboard") | título da página |
| `subtitulo` | texto | — | frase com a pergunta que os cálculos respondem |
| `lang` | texto | `pt` | só as duas primeiras letras contam; `pt` ou `en` (outro valor cai em `pt`) |
| `unidade` | texto | `kJ/mol` | `kJ/mol`, `kcal/mol` ou `eV`; qualquer texto com "kcal" vale kcal/mol, e tudo que não for `eV` exato vira kJ/mol. O leitor troca no topo da página; a escolha fica salva no navegador |
| `recarga_s` | int | `120` | recarga automática da página, em segundos; `0` desliga |
| `ativo_s` | número | `1800` | uma saída sem marca de fim e modificada há menos de `ativo_s` segundos é "rodando"; há mais, "parado" |
| `saida` | caminho | `painel.html` | relativo à pasta da configuração; `-o` na linha de comando tem prioridade |
| `raiz` | caminho | `.` | pasta-base de todos os caminhos (relativa à configuração, ou absoluta) |
| `id` | texto | slug do título | chave usada para guardar preferências no navegador |
| `rotulo` | texto | — | etiqueta curta no cabeçalho (ex.: "versão para revisão") |
| `secoes` | lista | todas | ids e ordem das seções: `aqui`, `reac`, `expl`, `filme`, `energia`, `ranking`, `valid`, `relativa`, `regra`, `medidas`, `freq`, `fila`, `metodos`, `gloss`. Seção sem dado não aparece de qualquer modo |
| `textos` | dict | — | substitui o texto de introdução de cada seção: `{energia: "..."}` (mesmos ids de `secoes`) |
| `maquina` | texto | — | linha "Máquina: ..." na seção de métodos (texto livre, declarado) |
| `glossario` | dict ou lista | — | `{"Termo": "Definição"}` ou `[[termo, definição], ...]`; um termo igual a um do glossário padrão o substitui |
| `glossario_padrao` | bool | `true` | `false` remove o glossário embutido |
| `grupos` | dict | `{}` | seleções nomeadas de átomos, usadas em medidas como `grupo:nome` (ex.: `{sitio: "0-11,14"}`; índices base 0) |
| `comparar_frequencias` | lista | `[]` | usado só se `frequencias` não trouxer `comparar` (ver seção 8) |

```yaml
titulo: "Dímero de benzeno: quanto dois anéis se atraem?"
lang: pt
unidade: kJ/mol
recarga_s: 300
ativo_s: 1800
saida: painel.html
```

## 2. `componentes`

Como agrupar e colorir moléculas no 3D. Sem isto, é criada uma classe por fórmula distinta (se houver de 2 a 10). Pode ser
dado também dentro de uma estrutura (`componentes:` na estrutura tem prioridade sobre o de topo).

Cada item (a molécula entra no **primeiro** componente que casar):

| Chave | Tipo | Significado |
|---|---|---|
| `nome` | texto | rótulo (também usado em `comp:<nome>`) |
| `formula` | texto ou lista | fórmula da molécula (C e H primeiro, depois ordem alfabética: `C6H6`, `H2O`, `NaCl`) |
| `contem` | elemento ou lista | casa se a molécula tiver algum desses elementos |
| `indices` | texto | `"0-11,14"` (base 0); casa se a molécula estiver inteira nesses índices |
| `cor` | `#rrggbb` | padrão: paleta embutida |

Se várias chaves de casamento forem dadas, **todas** precisam valer. Um item sem `formula`, `contem` nem `indices` nunca casa.

```yaml
componentes:
  - {nome: "hospedeiro", contem: [Zn]}
  - {nome: "solvente", formula: H2O, cor: "#17becf"}
```

## 3. `estruturas`

Lista de cálculos com geometria. Cada item pode ser um texto (só o caminho do arquivo) ou um dicionário. Um arquivo que falha ao
ser lido vira aviso e a estrutura é pulada.

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `arquivo` | caminho/glob | **obrigatório** | saída do programa, estrutura (extxyz, traj, cif, POSCAR...) ou JSON; ver `leitores.md` |
| `formato` | texto | detectado | força o leitor: `orca`, `orca_hess`, `cp2k`, `cp2k_molden`, `vasp_outcar`, `vasp_oszicar`, `vasprun`, `gaussian`, `qe`, `ase`, `json`, `jsonl`, `xyz_orca`, `xyz_cp2k`; qualquer outro valor é repassado ao ASE como nome de formato (`extxyz`, `traj`, `cif`, `vasp`...) |
| `id` | texto | nome do arquivo sem extensão | identificador único (usado em `reacao`, `energia`, `etapas`, `medidas`...). Com glob e sem `{` no id, o `stem` é acrescentado (`id_stem`) |
| `nome` | texto | `id` | nome mostrado |
| `padrao` | regex | — | aplicado (`re.search`) ao **nome** do arquivo; os grupos nomeados `(?P<item>...)` viram campos de modelo |
| `item` | texto | grupo `item` do padrão | identifica o arranjo/confôrmero (é a chave do `ranking`) |
| `replica` | texto | grupo `replica` do padrão | partida/réplica (barras de erro do ranking) |
| `grupo` | texto | — | agrupa estruturas (filtros de `ranking`, `medidas.estruturas`, `reacao` etc.) |
| `papel` | texto | — | `reagente`, `produto`, `ts` (ou `estado_de_transicao`); só é usado quando `reacao` não é dada |
| `inicial` | caminho | 1º quadro do arquivo | geometria inicial (lê o **último** quadro; `inicial_primeiro: true` usa o primeiro) |
| `trajetoria` | caminho/glob | — | quadros do filme quando o arquivo principal não os tem; se a energia do arquivo principal faltar, usa a do último quadro |
| `progresso` | caminho/glob | — | JSONL por passo (E, fmax, σ) para os gráficos do filme e o acompanhamento ao vivo (formato em `formato-dados.md`) |
| `registro` | caminho | — | JSON por estrutura que completa o que o arquivo não registra (`convergiu`/`converged`, `passos`/`steps`/`n_passos`, `tempo_s`/`duracao_s`/`elapsed_s`) |
| `nivel` | texto ou dict | — | declara o que o arquivo não registra: `{nivel: "...", programa: "...", versao: "..."}`; texto simples = só o nível. Só preenche lacunas e é marcado "declarado na configuração" |
| `componentes` | lista | o de topo | ver seção 2 |
| `molecula_em_caixa` | bool | `false` | trata como molécula isolada mesmo havendo célula (também é assumido se não há célula ou `pbc` é falso) |
| `n_fu` | número | `1` | unidades de fórmula na célula; divide a energia nos termos com `por_fu: true` e no `ranking` |
| `rotulo_fu` | texto | `FU` | nome da unidade ("FU", "mol"...) |
| `nota` | texto | — | explicação curta mostrada na ficha |

**Modelos de texto.** Em `id`, `nome`, `item`, `replica`, `grupo`, `inicial`, `trajetoria`, `progresso`, `registro` e `nota`
(somente se forem texto), use `{stem}` (nome do arquivo sem extensão), `{pasta}` (nome da pasta-mãe) e os grupos nomeados de
`padrao` (`{item}`, `{replica}`, ...). Se algum campo citar um nome inexistente, **nenhum** modelo é aplicado e o `id` fica
literal (com chaves). `item` e `replica` são preenchidos pelos grupos do padrão mesmo sem aparecerem na configuração.

```yaml
estruturas:
  - id: benzeno_uma
    nome: "Benzeno isolado · UMA"
    arquivo: calc/uma/estruturas/benzeno.extxyz
    inicial: calc/geometrias/benzeno.xyz
    trajetoria: calc/uma/traj/benzeno.traj
    progresso: calc/uma/progresso/benzeno.jsonl
    papel: reagente
  - id: "dimero_{item}_p{replica}"
    nome: "Dímero {item} · partida {replica} · UMA"
    arquivo: "calc/uma/estruturas/dimero_*__p*.extxyz"
    padrao: "dimero_(?P<item>[A-Z]+)__p(?P<replica>\\d+)"
    inicial: "calc/geometrias/{stem}.xyz"
    trajetoria: "calc/uma/traj/{stem}.traj"
    progresso: "calc/uma/progresso/{stem}.jsonl"
    grupo: dimeros
```

**Estado.** Vem do leitor ("concluido", "falhou", "rodando?"...). "rodando?" vira `rodando` ou `parado` conforme a idade do
arquivo (`ativo_s`). Se há `progresso` sem linha final `{"fim": true}`, o estado passa a `rodando`/`parado` pela idade desse
arquivo. A energia da estrutura é `energia_eV` do leitor ou, na falta, a do último quadro.

Evite `id` repetido: vale o primeiro; os seguintes são ignorados e geram aviso no painel.

## 4. `reacao`

Reagentes, produtos e estados de transição para os visualizadores lado a lado.

| Chave | Tipo | Significado |
|---|---|---|
| `reagentes`, `produtos`, `ts` | lista de ids | ids de `estruturas` (ids inexistentes são descartados em silêncio) |

Sem `reacao`, as listas saem do `papel` das estruturas.

```yaml
reacao:
  reagentes: [benzeno_uma]
  produtos: [dimero_PD_p0, dimero_T_p0]
```

## 5. `filmes`

Os filmes de otimização são criados automaticamente para toda estrutura com 2 ou mais quadros. Esta chave acrescenta filmes de
arquivos que não são estruturas do painel.

| Chave | Tipo | Significado |
|---|---|---|
| `arquivo` | caminho/glob | arquivo multi-quadro |
| `nome` | texto | aceita `{stem}` |
| `progresso` | caminho | aceita `{stem}` |
| `nivel` | texto/dict | declarado (como em `estruturas`) |

Limites: no máximo 60 quadros por filme (amostrados) e cerca de 12 MB no total; filmes além do orçamento são omitidos e o
painel informa quantos. Filmes cujos quadros mudam de número de átomos são ignorados.

## 6. `etapas` ("você está aqui")

Cartões de progresso do trabalho, da esquerda para a direita.

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `id` | texto | `E1`, `E2`... | referenciado em `depende_de` |
| `nome` | texto | `id` | título |
| `arquivos` | lista de glob | — | cada arquivo achado é um item; o estado vem do leitor (arquivo ausente = pendente; ilegível/desconhecido = concluído, pois o artefato existe) |
| `estruturas` | lista de ids | — | itens tirados de `estruturas` (id não lido = pendente) |
| `fila` | lista de nomes | — | itens tirados da `fila` |
| `total` | int | nº de itens | quantos itens a etapa terá; faltando itens, o cartão mostra "feitos/total" |
| `estado` | texto | calculado | força o estado: `concluido`, `rodando`, `pendente`, `falhou` (aceita também `concluído`, `done`, `running`, `pending`, `failed`) |
| `paralelo` | int | `1` | cálculos simultâneos, para a estimativa de tempo restante |
| `depende_de` | lista de ids | — | etapas anteriores (só visual) |
| `nota` | texto | — | explicação em linguagem simples |

Estado calculado: sem itens ou nenhum feito/rodando/falho/parado = `pendente`; feitos ≥ total = `concluido`; algum rodando =
`rodando`; algum falho = `falhou`; algum parado = `parado`; senão `parcial`. A estimativa de tempo restante usa a **mediana**
das durações medidas (ou o intervalo entre términos) e só aparece se houver ritmo medido.

```yaml
etapas:
  - {id: E1, nome: "Otimizações", estruturas: [reagente], nota: "Explicação curta."}
  - {id: E2, nome: "Confôrmeros", arquivos: ["calc/conformeros/*.out"], total: 12, depende_de: [E1]}
```

## 7. `energia`

Diagramas e parcelas montados por **expressões** sobre termos de energia.

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `nome_principal` | texto | "principal" | nome da primeira variante (a que usa `termos`) |
| `por` | texto | — | legenda da normalização ("por molécula", "por dímero") |
| `termos` | dict | `{}` | nome → definição (abaixo) |
| `variantes` | dict | `{}` | nome da variante → termos próprios (abaixo) |
| `diagramas` (ou `diagrama`) | lista (dict) | `[]` | diagramas |
| `parcelas` | lista | `[]` | diferenças comentadas |

### 7.1 Termos

Nomes de termo precisam ser identificadores simples (`E_mon`, `E_PD`; sem pontos nem espaços).

| Forma | Efeito |
|---|---|
| `E_R: reagente` | energia da estrutura de id `reagente` (eV, do arquivo; selo do arquivo) |
| `E_R: {estrutura: reagente, por_fu: true}` | idem, dividida por `n_fu` |
| `E_x: {json: res.json, caminho: "ciclo.dE", unidade: eV, nivel: ...}` | número num JSON; `caminho` com pontos (chaves; índices numéricos para listas); `nivel` opcional dá o selo, senão "não registrado (res.json)" |
| `E_lit: {valor: -3.1, unidade: kcal/mol, fonte: "Autor 2020"}` | número digitado; marcado como tal, com a fonte |
| `E_c: -3.1` | número puro: digitado, em eV, sem fonte |

`unidade` aceita (sem distinguir maiúsculas): `eV` (padrão), `Ha`/`hartree`/`Eh`, `Ry`, `kJ/mol`, `kcal/mol`, `meV`.
Para `estrutura`, `unidade` não se aplica (a energia já vem em eV). Um termo que falha vira aviso e fica ausente.

### 7.2 Variantes

A primeira variante (de nome `nome_principal`) usa `termos`. Cada entrada de `variantes` define **seus próprios termos** e **não
herda** os principais (evita misturar níveis sem querer), a menos que traga `herdar: true`. Uma expressão que cite um termo
ausente numa variante fica sem valor naquela variante (sem aviso).

```yaml
variantes:
  "B97-3c (geometria própria)": {E_mon: benzeno_dft, E_PD: dimero_dft}
  "B97-3c na geometria UMA":    {E_mon: sp_benzeno,  E_PD: sp_dimero}
```

### 7.3 Expressões

Aritmética segura: números, nomes de termos, `+ - * /`, sinal unário e parênteses. Nada mais (sem `**`, atributos ou código). Nas `regras`
(seção 16) valem também `max`, `min`, `abs`, `sqrt` e comparações.
Expressão inválida gera aviso. **Mistura de níveis:** se uma expressão usa termos de selos diferentes (inclusive "número
digitado" com valor lido de arquivo), o painel avisa `... mistura resultados de níveis de cálculo diferentes`.

### 7.4 Diagramas

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `titulo` | texto | — | título |
| `tipo` | texto | `niveis` | `niveis` (barras horizontais) ou `perfil` (R→TS→P, com curva ligando os níveis) |
| `referencia` | expressão | — | subtraída de todos os níveis (zero do diagrama) |
| `niveis` | lista | `[]` | `{rotulo, expr, cor, x}`; `x` fixa a posição horizontal; `rotulo` aceita `<br>` |
| `passos` | lista | `[]` | setas rotuladas entre níveis: `{de: 0, para: 3, rotulo: "..."}` (índices base 0 em `niveis`) |
| `ligar` | bool | `true` em `perfil`, `false` em `niveis` | liga os níveis por linha |
| `nota` | texto | — | legenda |

### 7.5 Parcelas

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `nome` | texto | a expressão | nome da parcela |
| `expr` | expressão | **obrigatório** | ex.: `"E_PD - 2*E_mon"` |
| `explicacao` | texto | — | o que a diferença significa (em linguagem simples) |
| `classe` | texto | `auto` | `auto` colore por sinal (negativo/positivo); ou `pos` / `neg` para forçar |

```yaml
energia:
  nome_principal: "UMA"
  por: "por dímero"
  termos: {E_mon: benzeno_uma, E_PD: dimero_PD_p0}
  diagramas:
    - titulo: "Formação do dímero"
      tipo: niveis
      referencia: "2*E_mon"
      niveis:
        - {rotulo: "2 benzenos<br>isolados", expr: "2*E_mon"}
        - {rotulo: "dímero PD", expr: "E_PD"}
      passos: [{de: 0, para: 1, rotulo: "interação PD"}]
  parcelas:
    - {nome: "Energia de interação (PD)", expr: "E_PD - 2*E_mon", explicacao: "Negativa: os anéis se atraem."}
```

## 8. `ranking`

Energias relativas ao arranjo mais estável (zero), com barra de erro. Duas fontes:

**A partir das estruturas** (padrão):

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `titulo` | texto | "Ranking" | |
| `grupo` | texto | todas | só estruturas desse `grupo` |
| `por_fu` | bool | `true` | divide a energia por `n_fu` (note: nos termos de `energia` o padrão é `false`) |
| `so_convergidas` | bool | `true` | descarta estruturas com `convergiu` falso (as de convergência desconhecida entram) |
| `rotulos` | dict | — | `{item: "texto"}` para renomear itens |
| `nota`, `por`, `erro_rotulo` | texto | — | legendas |

As estruturas são agrupadas por `item` (na falta, o `id`); vale a **menor** energia de cada item, e a barra de erro é
`máx − mín` entre as réplicas (só existe com mais de uma). Mistura de selos gera um aviso.

**A partir de um JSON:** `json`, `caminho` (chaves separadas por ponto; só dicionários), `unidade` (padrão eV), `unidade_erro`,
`campo_energia` (padrão `E`), `campo_erro`, `tirar_prefixo` (regex removida do nome), `abre_estrutura` (modelo com `{nome}` e
campos do item para abrir uma estrutura ao clicar), `nivel` (selo; sem ele, "não registrado"). O JSON mapeia nome → número ou
nome → dicionário.

```yaml
ranking:
  - {titulo: "Arranjos do dímero", grupo: dimeros, por_fu: false, nota: "A barra é a dispersão entre as 3 partidas."}
```

## 9. `medidas`

Medidas geométricas calculadas em cada estrutura (geometria inicial e final).

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `id` | texto | `m1`, `m2`... | |
| `nome`, `explicacao` | texto | `id` | |
| `tipo` | texto | `distancia` | ver tabela abaixo |
| `a`, `b`, `c`, `d` | seletor | — | grupos de átomos (sintaxe abaixo) |
| `estruturas` | lista | todas | ids **ou** `grupo`s onde a medida vale |
| `casas` | int | 3 (Å) / 1 (°) | casas decimais |
| `referencia` | número ou dict | — | valor de comparação (abaixo) |
| `tolerancia` | `[t1, t2]` | — | \|Δ\| ≤ t1: ok (verde); ≤ t2: atenção; acima: fora. Com um só valor, t2 = 2,5·t1 |
| `agregar` | texto | `media` | quando há vários pares: `media`, `min`, `max`, `primeiro`, `ponto_medio` |
| `mais_proximo` | bool | `true` se `b` tem mais de um grupo | para cada grupo de `a`, usa o grupo de `b` (e a imagem periódica) mais próximo; falso emparelha pela ordem |
| `lados` | bool | `false` | retém o vizinho mais próximo de cada lado do plano de `a` (até 2) |

Tipos (unidade): `distancia` (Å, entre centroides), `perpendicular` (Å, distância centro–centro projetada na normal do plano
de `a`), `deslizamento` (Å, componente no plano), `angulo_planos` (°, entre as normais dos planos de `a` e `b`; planos por SVD,
precisam de 3+ átomos), `angulo` (°, `a`-`b`-`c`, vértice em `b`), `diedro` (°, `a`-`b`-`c`-`d`), `distancia_minima` (Å, menor
distância átomo–átomo entre `a` e `b`, com imagens periódicas). Em `angulo` e `diedro`, cada seletor usa o centroide do
**primeiro** grupo que resolver.

**Seletores** (texto; vários grupos podem ser devolvidos):

| Seletor | Seleciona |
|---|---|
| `todos` (`all`, `*`) | todos os átomos (um grupo) |
| `0-11,14` ou `idx:0-11,14` | índices base 0 (um grupo); um número isolado (`"1"`) vale |
| `mol:2` | a 2ª molécula (base 1, na ordem do primeiro átomo de cada uma) |
| `mol:C6H6` | cada molécula com essa fórmula (um grupo por molécula) |
| `mol:C6H6#2` | a 2ª molécula com essa fórmula |
| `mol:*` | cada molécula |
| `anel:6`, `anel:C6`, `anel:C3N2`, `anel:*` | anéis (ciclos mínimos até 8 átomos) por tamanho, composição ou todos |
| `comp:nome` | moléculas do componente nomeado |
| `el:C`, `el:C,N` | todos os átomos do(s) elemento(s) (um grupo) |
| `grupo:nome` | seleção de `grupos` (topo) |
| `A&B` | filtro: cada grupo de `A` restrito aos átomos de `B` (`mol:C6H6&el:C`) |

Moléculas são reconstruídas por ligações (raios covalentes ×1,15), inclusive atravessando a célula periódica.

**`referencia`:**

| Forma | Efeito |
|---|---|
| `3.9` | número digitado (marcado) |
| `{valor: 3.9, fonte: "raio X"}` | número digitado com fonte |
| `{estrutura: dimero_dft, inicial: false}` | valor medido nessa estrutura (final; `inicial: true` usa a geometria inicial); a fonte mostrada é o nome da estrutura |
| `{json: ref.json, caminho: "a.b", fonte: "..."}` | número lido de um JSON |
| ... `aplicar_a: [PD, dimero_dft]` | restringe a referência a estas estruturas; cada nome pode ser id, `grupo` ou `item` |

```yaml
medidas:
  - id: dcc
    nome: "Distância centroide–centroide"
    tipo: distancia
    a: "mol:1&el:C"
    b: "mol:2&el:C"
    estruturas: [dimeros, dft, sp]
    referencia: {estrutura: dimero_dft, aplicar_a: [PD, dimero_dft, sp_dimero]}
    tolerancia: [0.1, 0.25]
```

## 10. `frequencias`

Pode ser uma **lista** de sistemas ou um dicionário `{sistemas: [...], comparar: [...]}`.

Sistema (um item da lista; texto simples = só o `arquivo`):

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `arquivo` | caminho/glob | **obrigatório** | saída com frequências (ORCA `.out`/`.hess`, Gaussian, VASP IBRION 5-8, CP2K `-VIBRATIONS-*.mol`) ou JSON de frequências (ver `formato-dados.md`) |
| `id` | texto | nome do arquivo | com glob, o `stem` é acrescentado |
| `nome` | texto | `id` | |
| `rotulo` | texto | o do JSON, se houver | etiqueta; contendo "explorat" (sem distinguir maiúsculas) ativa o banner **EXPLORATÓRIO** na seção |
| `nivel` | dict | — | declaração do que o arquivo não registra |
| `classe` | texto | pelo programa | `MLIP`, `QM`, `semiempírico`, `clássico` (muda a cor) |
| `referencia` | dict ou lista | — | valores de comparação (abaixo) |
| `estrutura` | texto | — | id de estrutura associada (guardado; sem efeito visível hoje) |

**`referencia` inline:** `{fonte: "...", tolerancia: [30, 80], modos: [{rotulo, valor, calc}]}`. `valor` em cm⁻¹ (`exp` é aceito
como sinônimo); `calc` opcional fixa a frequência calculada pareada; sem `calc`, usa-se a frequência calculada **positiva mais
próxima** (sem garantir pareamento um-a-um). Resultado: MAE, erro máximo e cores por `tolerancia` (padrão `[30, 80]` cm⁻¹).
Uma lista simples de modos também é aceita no lugar do dicionário.

**`referencia` em JSON:** `{json: tabela.json, caminho: "dados.modos", campo_rotulo: "{especie} · {descricao}", campo_valor: valor,
campo_calc: calculado, fonte: "...", tolerancia: [..]}`. O JSON deve apontar (via `caminho`) para uma **lista de dicionários**;
linhas sem o campo de valor são ignoradas; `campo_rotulo` pode ser um modelo com `{campos}` da linha (padrões: `rotulo`,
`valor`). As demais chaves (`fonte`, `tolerancia`) passam adiante.

**`comparar`:** lista de `{a: id, b: id, acima_de: 300}` (ou `[a, b]`). Pareia cada frequência de `a` (acima de `acima_de` cm⁻¹,
padrão 300, para ignorar modos de baixa frequência) com a mais próxima de `b` e informa MAE e máximo. Ids inexistentes geram
aviso.

```yaml
frequencias:
  sistemas:
    - id: bz_uma
      nome: "Benzeno · UMA"
      arquivo: calc/uma/freq/benzeno.json
      rotulo: EXPLORATÓRIO
      referencia:
        fonte: "fundamentais experimentais (cite a fonte exata)"
        modos: [{rotulo: "ν1 (respiração do anel)", valor: 993}]
    - {id: bz_dft, nome: "Benzeno · B97-3c", arquivo: calc/orca/benzeno/benzeno.out}
  comparar: [{a: bz_uma, b: bz_dft}]
```

Os modos normais (para a animação) ocupam espaço; acima de ~6 MB somados, os modos dos últimos sistemas são omitidos (as
frequências ficam) e o painel avisa.

## 11. `fila`

Cálculos pesados ou remotos, com o SCF mostrado e o critério de convergência correto de cada programa. Cada item (texto =
`saida`):

**Saídas de arquivo**

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `saida` (ou `arquivo`) | glob | — | arquivos de saída; se o glob casar uma **pasta**, usa a saída `.out`/`.log` mais recente dentro dela |
| `nome` | texto | `{stem}` (arquivo) / `{pasta}` (pasta) | modelo com `{stem}` e `{pasta}` |
| `grupo` | texto | — | agrupa na tabela |
| `nivel` | texto/dict | — | declarado, se a saída não registrar |
| `criterio` | dict | do arquivo | `{nome, valor, coluna, nota}`; sobrepõe o que o leitor achou |
| `ativo_s` | número | o de topo | limiar "rodando"/"parado" só para este item |
| `estado` | texto | do arquivo | força o estado |
| `nota` | texto | — | |

**Estado ao vivo por JSON**

| Chave | Tipo | Significado |
|---|---|---|
| `json_vivo` | caminho/glob | JSON de acompanhamento escrito por um script externo (formato em `formato-dados.md`) |
| `grupo`, `programa`, `versao`, `nivel`, `criterio`, `nota` | | como acima; `programa` e `versao` alimentam o selo |
| `nomes_de` | lista de caminhos | arquivos com um nome de job por linha (`#` comenta); os que o JSON não cita aparecem como `pendente` |
| `pastas` | lista de glob | cada pasta casada vira um job `pendente` (se o JSON não o citar) |

Sem `criterio` e havendo coluna de convergência nos dados, o painel **presume** CP2K (`EPS_SCF = 1e-6`, coluna `Convergence`) e
escreve isso na nota ("critério presumido"): declare `criterio` para outros programas.

```yaml
fila:
  - {saida: "calc/orca/*/*.out", grupo: "ORCA (DFT)"}
  - {json_vivo: remoto/ao_vivo.json, grupo: "Servidor", programa: CP2K,
     criterio: {nome: EPS_SCF, valor: 1.0e-6, coluna: Convergence}}
```

## 12. `metodos`

Cartões extras (os de cada nível de cálculo usado são gerados sozinhos, lidos dos arquivos). Estes ficam marcados "declarado na
configuração (não lido de arquivo)".

| Chave | Tipo | Significado |
|---|---|---|
| `titulo` | texto | título do cartão |
| `campos` | dict ou lista de pares | `{Origem: "...", Otimizador: "..."}` |
| `selo` | texto | sobrepõe o selo padrão |

```yaml
metodos:
  - titulo: "Geometrias iniciais"
    campos: {Origem: "CSD, refcode XXXX", Partidas: "0 = exata; 1 e 2 = ruído de 0,02 Å"}
```

---

## 13. `forcas` (erro de força por átomo entre dois métodos)

Compara, **na mesma geometria**, as forças de dois cálculos (por exemplo um MLIP e o DFT) e colore os átomos por
|ΔF| = ‖F_a − F_b‖ (norma da diferença, em meV/Å) no Explorador e no 🔍 Ampliar (modo `|ΔF|`, escala em meV/Å até o
percentil 99, no mínimo 50 meV/Å). Também alimenta a seção **Validação método × referência** (seção 14). Sem `forcas`,
o botão `|ΔF|` e a seção não aparecem. Uma lista simples vale como `forcas: {pares: [...]}`.

Duas fontes de dados:

- **Dois cálculos no mesmo ponto** (`pares`): as forças vêm dos leitores (ASE/extxyz/traj, ORCA, CP2K, VASP, Gaussian com
  `NoSymm`; ver `leitores.md`). Os dois cálculos precisam ter os mesmos átomos na mesma ordem e a mesma geometria
  (diferença máxima `tol_geom`, padrão 0,02 Å, descontado o deslocamento rígido do centroide ou, com célula, a imagem
  periódica). Se não for o mesmo ponto, o par é **recusado com aviso** (nunca se compara forças de pontos diferentes).
- **Erro por átomo já calculado** (`precalculado`): um JSON com um número por átomo.

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `pares` | lista | `[]` | cada item: `{a, b, id, nome, sistema, rotulo_a, rotulo_b, grupo, ressalvas}` (abaixo) |
| `precalculado` | lista | `[]` | cada item: `{estrutura, json, caminho, unidade, id, nome, sistema, rotulo_a, rotulo_b, nivel, ressalvas}` |
| `piores_pct` | lista de números | `[5, 10]` | fração do erro total contida nos k% piores átomos |
| `tol_geom` | número (Å) | `0.02` | tolerância para dizer que as duas geometrias são a mesma |

Item de `pares`:

| Chave | Significado |
|---|---|
| `a` | id da estrutura do método **avaliado** (por exemplo, o MLIP) |
| `b` | id da estrutura do método de **referência** (por exemplo, o DFT) |
| `a_grupo` | alternativa a `a`: um par para cada estrutura desse `grupo`; `b` pode usar `{item}`, `{replica}`, `{id}`, `{stem}` da estrutura de `a` (e `id`/`sistema`/`nome` também) |
| `id`, `nome`, `sistema` | rótulos (padrões: `a_x_b`, `"{a} × {b}"`, nome da estrutura `a`) |
| `rotulo_a`, `rotulo_b` | nome dos métodos nos textos e na barra de cores (padrão: o nome da estrutura) |
| `grupo` | agrupa na seção de validação |
| `ressalvas` | ressalvas deste par (seção 17) |

Cada estrutura de um par ganha o |ΔF| por átomo (a primeira vez que aparece; uma segunda coloração da mesma estrutura gera aviso).

**O que é calculado.** `MAE de força` = média de |ΔF_ia| sobre as 3N componentes cartesianas (o "MAE de força" usual);
`maior componente` = máx |ΔF_ia|; `|ΔF| médio por átomo` = média das normas. Por **elemento** e por **componente**
(o que a configuração define em `componentes`; se não houver mais de uma classe, por **molécula** achada pela
conectividade, quando há de 2 a 8) o painel mostra n, MAE, e a **parcela do erro total** (soma de |ΔF| dos átomos do grupo
sobre a soma de todos); e "os k% piores átomos respondem por X% do erro". Se as duas estruturas são periódicas e trazem
tensão (ASE com `stress`, VASP), calcula-se também o MAE de tensão (média das 6 componentes de Voigt, GPa; convenção do ASE,
tração positiva).

`precalculado`: `json` + `caminho` (com pontos) apontam para uma lista de N números (|ΔF| por átomo); `unidade` é `eV/Å`
(padrão) ou `meV/Å`; `estrutura` é o id da estrutura que será colorida. Como só há o erro por átomo, o "MAE" mostrado é o
|ΔF| médio por átomo (rotulado como tal) e não há maior componente nem tensão. Número de valores ≠ número de átomos: recusado com aviso.

```yaml
forcas:
  pares:
    - {id: f_bz, a: benzeno_uma, b: sp_benzeno, sistema: "Benzeno", rotulo_a: "UMA", rotulo_b: "B97-3c"}
    - {id: "f_{item}_p{replica}", a_grupo: dimeros, b: "sp_dimero_{item}_p{replica}", sistema: "Dímero {item} · partida {replica}"}
  precalculado:
    - {estrutura: cristal, json: diagnostico.json, caminho: "sistemas.X.dF_eV_A", rotulo_a: "MLIP", rotulo_b: "DFT"}
```

---

## 14. `validacao` (faixas de qualidade e textos da seção "Validação método × referência")

A seção aparece quando existe `forcas` ou `comparacao_energia`. Por sistema: MAE e maior componente de força, tensão (se
houver), energia relativa, barras de parcela do erro por componente/molécula, tabela por elemento, concentração nos piores
átomos e um botão para abrir o Explorador colorido por |ΔF|. **Nenhum limite está fixo no código**: as faixas vêm daqui;
sem `bandas.forca_mae` vale o padrão da skill (≤ 30 / ≤ 50 / ≤ 100 meV/Å → excelente / aceitável / marginal / falha), que
o painel rotula como "padrão da skill, não é norma" — defina as suas.

| Chave | Tipo | Significado |
|---|---|---|
| `titulo`, `nota` | texto | cabeçalho e comentário da seção |
| `bandas` | dict | faixas por grandeza (abaixo) |
| `ressalvas` | lista | ressalvas da seção inteira (seção 17) |

`bandas`: chaves `forca_mae` (meV/Å), `forca_max` (maior componente, meV/Å), `tensao_mae` (GPa) e `energia_max` (erro máximo
de energia relativa, em `unidade`, padrão kJ/mol). Cada uma: `{limites: [l1, l2, l3], rotulos: [r0, r1, r2, r3], unidade}`.
`limites` crescentes; valor ≤ l1 → `r0`, ≤ l2 → `r1`, … acima do último → o último rótulo (um rótulo a mais que limites; sem
`rotulos`, 3 limites usam excelente/aceitável/marginal/falha). As duas faixas piores ficam amarela e vermelha; as demais, verdes.

```yaml
validacao:
  bandas:
    forca_mae:   {limites: [30, 50, 100], unidade: "meV/Å"}
    tensao_mae:  {limites: [0.05, 0.10, 0.20], unidade: "GPa"}
    energia_max: {limites: [1, 3, 6], unidade: "kJ/mol", rotulos: [ótimo, bom, regular, ruim]}
```

---

## 15. `comparacao_energia` (energia relativa entre dois métodos)

Para vários arranjos (confôrmeros, microestados, polimorfos) calculados por **dois métodos**: dispersão ΔE_A × ΔE_B,
ambas relativas a um arranjo de referência, com a diagonal da concordância perfeita. As energias absolutas não são
comparáveis entre métodos e nunca são comparadas. A unidade segue o seletor global (kJ/mol, kcal/mol, eV).

| Chave | Tipo | Padrão | Significado |
|---|---|---|---|
| `id`, `titulo`, `nota` | texto | `cmpN` | |
| `rotulo_a`, `rotulo_b` | texto | `A`, `B` | método avaliado (eixo y) e de referência (eixo x) |
| `referencia` | texto | 1º item | `rotulo` do item que vale zero nos dois métodos |
| `itens` | lista | — | `{rotulo, a, b, est}`; `a` e `b` são um id de estrutura **ou** um termo de energia (`{estrutura, por_fu}`, `{json, caminho, unidade}`, `{valor, unidade, fonte}` — como em `energia.termos`); `est` (opcional) abre essa estrutura no Explorador ao clicar no ponto |
| `itens_de` | dict/lista | — | gera itens a partir de um `grupo`: `{a_grupo, b: "sp_{item}", rotulo: "{item} p{replica}"}` |
| `por_fu` | bool | `false` | divide as energias de estruturas por `n_fu` |
| `por`, `ressalvas` | | | legenda da normalização; ressalvas |

Métricas (energias em eV internamente): sobre os itens **exceto a referência** — MAE, erro máximo, RMS, viés médio e **MAE
centrado** (MAE do erro depois de tirar o viés médio); sobre **todos** os itens — correlação de **Spearman** e **Kendall**
(τ-b; precisam de ≥ 3 itens) e o arranjo de **menor energia** em cada método: o painel avisa quando os dois métodos
**discordam** sobre qual é o mais estável. Se os itens de um mesmo lado vêm de níveis de cálculo diferentes, há aviso de mistura.

```yaml
comparacao_energia:
  - id: arranjos
    titulo: "Energia relativa dos arranjos: UMA × B97-3c"
    rotulo_a: "UMA"
    rotulo_b: "B97-3c"
    referencia: "PD"
    itens:
      - {rotulo: "PD", a: dimero_PD_p0, b: sp_dimero_PD_p0}
      - {rotulo: "T",  a: dimero_T_p0,  b: sp_dimero_T_p0}
      - {rotulo: "S",  a: dimero_S_p0,  b: sp_dimero_S_p0}
```

---

## 16. `regras` (cartão de regra de decisão)

Uma regra explícita e **escrita antes de ver o resultado**: grandezas, uma estatística, resultados possíveis com
condição, **veredito**, **margem até o limiar**, tabela opcional de **sensibilidade** a definições alternativas e
ressalvas. Nada é específico de um projeto: os nomes, as fórmulas e os limiares são todos seus.

| Chave | Tipo | Significado |
|---|---|---|
| `id`, `titulo`, `pergunta`, `nota` | texto | `pergunta`: o que a regra decide, em uma frase |
| `pre_registrada` | bool | `true`: estatística e limiares fixados **antes** de ver os dados (selo no cartão); `false`: fixados **depois** — o cartão avisa que o veredito é a posteriori e a skill exige (aviso) a tabela de sensibilidade; ausente: "não declarado" |
| `grandezas` | dict | nome → definição (abaixo) |
| `estatistica` | texto ou dict | `"R / U"` ou `{nome, expr, unidade, casas}`: expressão sobre as grandezas; o resultado se chama `T` nas condições |
| `resultados` | lista | `{id, rotulo, quando, severidade, texto}`, avaliados **em ordem**; o primeiro cuja `quando` vale ganha; um sem `quando` vale sempre (ponha por último). `severidade`: `ok`, `warn`, `bad`, `info` |
| `sensibilidade` | lista | `{rotulo, explicacao, grandezas, estatistica}`: cada alternativa **sobrepõe** grandezas (e, se quiser, a estatística) e recalcula tudo |
| `ressalvas` | lista | ressalvas da regra (seção 17) |

**Grandezas.** Cada uma tem `nome`, `unidade`, `fonte`, `explicacao` e **uma** origem:

| Origem | Significado |
|---|---|
| `valor: 3.0` (ou só o número) | digitado (marcado como tal no cartão) |
| `estrutura: id` (+ `por_fu`) | energia da estrutura (selo do arquivo), convertida para `unidade` (padrão eV) |
| `json: arq`, `caminho: "a.b"` | número num JSON, já na `unidade` declarada |
| `comparacao: "id.campo"` | métrica de uma `comparacao_energia`: `mae`, `max_abs`, `rms`, `vies`, `mae_centrado` (energias; `unidade` padrão eV) ou `spearman`, `kendall`, `n` |
| `forcas: "id.campo"` | métrica de um par de `forcas`: `mae`, `max_comp`, `media_atomo`, `max_atomo`, `rmse` (meV/Å) |
| `expr: "max(a, b, piso)"` | expressão sobre outras grandezas; qualquer ordem de declaração (dependência circular ou nome desconhecido = aviso e sem veredito) |

Expressões e condições aceitam números, nomes, `+ − × ÷`, parênteses, `max`, `min`, `abs`, `sqrt` e, nas condições, `< <= > >= == !=`,
`and`, `or`, `not` — mais nada (nenhum código é executado). **Unidades**: o valor de cada grandeza fica na unidade que você declarou
(constantes em `expr` valem nessa unidade); unidades de energia (`eV`, `kJ/mol`, `kcal/mol`, `Ha`, `Ry`, `meV`) seguem o seletor global
na página, as demais aparecem como escritas. A consistência de unidades dentro de uma expressão é de quem escreve.

**Veredito e margem.** O cartão mostra a estatística, o resultado vencedor e a **margem**: distância de `T` até o limiar mais
próximo entre as condições do tipo `T <op> valor`, com a fração do limiar e se aquele limiar já foi atingido. Se uma
grandeza não pode ser calculada, **não há veredito**: o cartão lista o que falta ("o painel não presume o resultado").
Na tabela de sensibilidade, o painel diz se o veredito **muda** conforme a definição.

```yaml
regras:
  - id: pd_vs_t
    titulo: "PD é mais estável que T?"
    pre_registrada: false
    grandezas:
      R:   {nome: "R = E(T) − E(PD)", expr: "E_T - E_PD", unidade: "kJ/mol"}
      E_T: {estrutura: sp_dimero_T_p0, unidade: "kJ/mol"}
      E_PD: {estrutura: sp_dimero_PD_p0, unidade: "kJ/mol"}
      U:   {nome: "incerteza", expr: "max(piso, err)", unidade: "kJ/mol"}
      piso: {valor: 0.1, unidade: "kJ/mol"}
      err: {comparacao: "arranjos.max_abs", unidade: "kJ/mol"}
    estatistica: {nome: "T = R / U", expr: "R / U"}
    resultados:
      - {id: estabelecido, rotulo: "estabelecido", quando: "T >= 2", severidade: ok}
      - {id: refutado, rotulo: "refutado", quando: "T <= -2", severidade: bad}
      - {id: inconclusivo, rotulo: "inconclusivo", severidade: warn}
    sensibilidade:
      - {rotulo: "erro = MAE em vez do máximo", grandezas: {err: {comparacao: "arranjos.mae", unidade: "kJ/mol"}}}
```

---

## 17. `ressalvas` (avisos de limitação)

Uma ressalva é uma limitação conhecida de um resultado. Ela aparece como faixa colorida (`info` azul, `warn` amarela,
`bad` vermelha) onde se aplica, e **na etiqueta do modo Ampliar** quando se refere a uma estrutura. Cada ressalva é um
texto ou `{texto, severidade, id, secoes, estruturas}` (`severidade` aceita também `aviso`, `erro`, `informação`...; padrão `warn`).
Sem `texto` ela é ignorada com aviso.

Em `ressalvas` de topo, o alvo é dado por:

| Chave | Efeito |
|---|---|
| `secoes: [valid, energia, ...]` | faixa sob a introdução dessas seções (ids de `secoes`) |
| `estruturas: [id_ou_grupo, ...]` | na ficha da estrutura (Explorador, Reagentes → Produtos) e na etiqueta do Ampliar; alvo inexistente gera aviso |
| nenhum dos dois | faixa global, no topo da página |

Também se escreve **junto do objeto**, com a chave `ressalvas` (lista): em `estruturas[]`, `energia.parcelas[]`, `ranking[]`,
`forcas.pares[]`/`precalculado[]`, `comparacao_energia[]`, `regras[]` e `validacao`. Ressalvas inline aparecem no próprio cartão.

```yaml
ressalvas:
  - {texto: "Comparação em geometria do método A, não do B.", severidade: warn, secoes: [valid, relativa, regra]}
  - {texto: "Estrutura de partida sacudida.", severidade: info, estruturas: [dimeros]}
```
