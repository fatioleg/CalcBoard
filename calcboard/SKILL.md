---
name: calcboard
description: >-
  CalcBoard: gera um painel HTML único, offline, interativo e didático dos cálculos de estrutura eletrônica / simulação
  atomística de um projeto (moléculas, cristais, superfícies, aglomerados): etapas e estado (concluído/rodando/
  pendente/falhou, ETA), reagentes → produtos em 3D, explorador de geometrias inicial × final, filme da otimização,
  perfil/ciclo de energia, ranking de confôrmeros, distâncias e medidas, frequências vibracionais com modos animados,
  fila de cálculos com SCF ao vivo, métodos e glossário, e — quando há dois métodos no mesmo ponto — erro de força por
  átomo (|ΔF|), validação método × referência, energia relativa entre métodos e cartão de regra de decisão com ressalvas.
  Lê ORCA, CP2K, VASP, Gaussian, QE, ASE e JSON. Use sempre que o usuário pedir "CalcBoard", "painel de cálculos", "painel dos
  cálculos", "visualizar cálculos", "ver geometrias otimizadas", "perfil de energia", "diagrama de energia",
  "acompanhar os cálculos", "ver as frequências", ou em inglês
  "calculation dashboard", "visualize calculations", "show optimized geometries", "energy profile",
  "monitor DFT jobs", "optimization movie" — mesmo sem dizer "skill" ou "painel".
---

# CalcBoard

Transforma as saídas de cálculos de um projeto num `painel.html` que qualquer pessoa abre no navegador, sem internet.
O painel é **somente leitura**: nunca altera, move ou apaga resultados. Todo número vem dos arquivos; o que não foi
registrado aparece como "não registrado" — nunca invente nível de cálculo, versão ou valor.

Caminhos abaixo são relativos a esta skill (`<skill>` = pasta deste arquivo).

## Fluxo

1. **Descobrir os resultados.** Pergunte (ou descubra) a pasta do projeto e rode
   `python <skill>/scripts/painel.py descobrir <pasta> -o painel.yaml` — escreve um rascunho com as saídas reconhecidas
   (programa, versão, nº de quadros, estado). Para conferir um arquivo isolado:
   `python <skill>/scripts/painel.py ler <arquivo>`. Leia também o README/notas do projeto para entender a pergunta
   científica, os sistemas e as etapas.
2. **Escrever a configuração** (`painel.yaml` ou `painel.json`, ao lado dos dados ou numa pasta de trabalho).
   Ponto de partida comentado: `python <skill>/scripts/painel.py init`. Todas as chaves:
   `references/formato-config.md`. O essencial:
   - `estruturas` (com glob + `padrao` para réplicas/confôrmeros), `papel` reagente/produto/ts, `grupo`;
   - `etapas` com `depende_de` e `nota` em linguagem simples (é o que vira o "Você está aqui");
   - `energia.termos` (lidos das estruturas ou de JSON; `valor:` só para números da literatura, marcado como digitado),
     `variantes` por nível de cálculo, `diagramas` (níveis ou perfil R→TS→P) e `parcelas` com explicação;
   - `medidas` (distância, centroides, planos, deslizamento, ângulos), `ranking`, `frequencias`, `fila`;
   - **método × referência** (só se houver dois cálculos no MESMO ponto): `forcas` (erro de força por átomo), `validacao`
     (faixas de qualidade suas), `comparacao_energia` (energia relativa e ordem dos arranjos nos dois métodos), `regras`
     (veredito com margem e sensibilidade; **fixe a estatística antes de ver os dados**: `pre_registrada`) e `ressalvas`
     (limitações junto da seção, estrutura ou resultado). Nunca invente uma faixa de qualidade: pergunte ao usuário ou
     use o padrão rotulado como padrão.
   - `nivel:` só quando o arquivo não registra o método (vira selo "declarado na configuração").
   Siga `references/boas-praticas.md` (comparar métodos na mesma geometria, rotular o exploratório, critério de
   convergência certo por programa). O que cada leitor extrai e suas limitações: `references/leitores.md`.
3. **Gerar:** `python <skill>/scripts/painel.py gerar painel.yaml` (`-o` muda a saída; `--vigiar 120` regenera a
   cada 120 s para acompanhar cálculos ao vivo). A linha final informa tamanho, estruturas, filmes, jobs e **avisos**.
   Leitor que falha vira aviso no painel; corrija a configuração até os avisos fazerem sentido.
4. **Conferir por captura headless:** `python <skill>/scripts/captura.py painel.html -o /tmp/p.png`
   (seções: `--secao s_energia`; modo Ampliar: `--hash "#zoom=<id>"`; tema: `--tema dark`). Saída 0 = sem erros de
   JavaScript. Olhe as imagens: os 3D apareceram? os números e unidades batem com os arquivos? Sem navegador
   (código 3), diga isso ao usuário em vez de afirmar que o painel foi conferido.
5. **Entregar:** caminho do HTML, o que cada seção mostra, avisos restantes e o que não pôde ser lido.

## O que o painel garante

- Modo **|ΔF|** no Explorador e no Ampliar (átomos coloridos pelo erro de força, em meV/Å) quando há `forcas`.
- **Ressalvas** em faixas por seção/estrutura/resultado e na etiqueta do Ampliar; regras que não podem ser calculadas não
  ganham veredito.
- Seletor global **kJ/mol | kcal/mol | eV** (persistido no navegador); tema claro/escuro.
- **Selo de nível de cálculo + programa/versão** em todo resultado; níveis misturados numa diferença geram aviso.
- **🔍 Ampliar** em tela cheia: medidas por clique (distância/ângulo/diedro), isolar região, estilos por componente,
  contatos, vistas, modos vibracionais, filme, export PNG/xyz/cif, link direto por `#zoom=`.
- **Recarga automática** (`recarga_s`), adiada com o Ampliar aberto ou uso recente, com contador e pausa.
- Seções só aparecem se houver dado. HTML único, 3Dmol.js e plotly.js embutidos de `assets/vendor/`.
- Textos em português; `lang: en` para inglês.

## Dependências

Python ≥ 3.9 e numpy; ASE para formatos ASE (extxyz, traj, cif, POSCAR…); PyYAML para `.yaml` (senão use `.json`).
Captura: Playwright + Chromium (preferido), ou Firefox/Chrome/Edge headless.

## Exemplos

O modelo comentado `assets/painel_modelo.yaml` cobre todas as seções. No repositório da skill
(github.com/fatioleg/CalcBoard) há `examples/dimero_benzeno/` (dados reais: UMA + ORCA B97-3c) e
`examples/amostras/` (saídas sintéticas curtas de ORCA, CP2K, VASP, Gaussian, QE e fila ao vivo).
