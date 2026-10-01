"""Textos do lado Python (avisos, selos, métodos, notas dos leitores) e glossário padrão, em português (padrão) e inglês.

Os leitores não conhecem o idioma: devolvem `Msg(chave, **campos)`, um `str` em português que carrega a chave e os
campos. O montador chama `traduzir` ao gravar o aviso/nota, e o texto sai no idioma da configuração."""

TXT = {
    "pt": {
        "nao_registrado": "não registrado", "versao_nr": "versão não registrada", "programa_nr": "programa não registrado",
        "declarado": "declarado na configuração", "declarado_cfg": "declarado na configuração (não lido de arquivo)",
        "digitado": "número digitado na configuração", "sem_fonte": "sem fonte", "principal": "principal",
        "geom_inicial": "geometria inicial", "ranking": "Ranking", "titulo_padrao": "Painel dos cálculos",
        "av_sem_arquivo": "nenhum arquivo encontrado para {}", "av_sem_geometria": "{}: o arquivo não traz geometria",
        "av_inicial": "{}: geometria inicial ilegível ({})", "av_json_vivo": "{}: JSON de acompanhamento ilegível ({})",
        "av_expr": "expressão '{}' inválida: {}",
        "av_id_repetido": "id {} repetido: {} ignorado (ids de estrutura precisam ser únicos)",
        "av_termo": "termo {} (variante {}): {}", "av_termo_tipo": "termo de energia sem 'estrutura', 'json' ou 'valor'",
        "av_sem_energia": "a estrutura {} não tem energia lida", "av_sem_freq": "{}: sem frequências no arquivo",
        "av_comparar": "comparação de frequências {} × {}: sistema ausente",
        "av_mistura": "aviso de níveis · '{}' {} mistura resultados de níveis de cálculo diferentes: {}",
        "crit_padrao_vivo": "critério presumido (EPS_SCF = 1e-6 do CP2K); declare 'criterio' na configuração da fila",
        "m_nivel": "Nível / método", "m_funcional": "Funcional", "m_base": "Base", "m_dispersao": "Dispersão", "m_corte": "Corte de energia",
        "m_pseudo": "Pseudopotenciais", "m_scf": "Algoritmo do SCF", "m_linha": "Linha de comando", "m_hessiana": "Hessiana",
        "m_tarefa": "Tarefa (MLIP)", "m_modelo": "Modelo", "m_programa": "Programa", "m_crit_scf": "Critério do SCF",
        "m_crit_opt": "Critério da otimização", "m_carga": "Carga / multiplicidade", "m_usado": "Usado em",
    },
    "en": {
        "nao_registrado": "not recorded", "versao_nr": "version not recorded", "programa_nr": "program not recorded",
        "declarado": "declared in the configuration", "declarado_cfg": "declared in the configuration (not read from a file)",
        "digitado": "number typed in the configuration", "sem_fonte": "no source", "principal": "main",
        "geom_inicial": "initial geometry", "ranking": "Ranking", "titulo_padrao": "Calculation dashboard",
        "av_sem_arquivo": "no file found for {}", "av_sem_geometria": "{}: the file has no geometry",
        "av_inicial": "{}: unreadable initial geometry ({})", "av_json_vivo": "{}: unreadable live JSON ({})",
        "av_expr": "invalid expression '{}': {}",
        "av_id_repetido": "duplicate id {}: {} skipped (structure ids must be unique)",
        "av_termo": "term {} (variant {}): {}", "av_termo_tipo": "energy term without 'estrutura', 'json' or 'valor'",
        "av_sem_energia": "structure {} has no energy", "av_sem_freq": "{}: no frequencies in the file",
        "av_comparar": "frequency comparison {} × {}: missing system",
        "av_mistura": "level warning · '{}' {} mixes results from different levels of theory: {}",
        "crit_padrao_vivo": "assumed criterion (CP2K EPS_SCF = 1e-6); declare 'criterio' in the queue configuration",
        "m_nivel": "Level / method", "m_funcional": "Functional", "m_base": "Basis", "m_dispersao": "Dispersion", "m_corte": "Energy cutoff",
        "m_pseudo": "Pseudopotentials", "m_scf": "SCF algorithm", "m_linha": "Command line", "m_hessiana": "Hessian",
        "m_tarefa": "Task (MLIP)", "m_modelo": "Model", "m_programa": "Program", "m_crit_scf": "SCF criterion",
        "m_crit_opt": "Optimization criterion", "m_carga": "Charge / multiplicity", "m_usado": "Used in",
    },
}

GLOSSARIO = {
    "pt": [
        ("DFT", "Teoria do funcional da densidade: calcula a energia de um sistema a partir da densidade de elétrons. É o 'cálculo quântico' mais usado; lento, mas confiável quando o funcional é adequado."),
        ("Funcional e base", "O funcional (PBE, B3LYP, B97-3c...) é a aproximação para a interação entre elétrons; a base (def2-SVP, TZV2P, ondas planas com corte...) é o conjunto de funções que descreve os orbitais. Juntos definem o 'nível de cálculo'."),
        ("MLIP", "Potencial interatômico de aprendizado de máquina (UMA, MACE, CHGNet...): uma rede neural treinada em milhões de cálculos DFT que estima energia e forças em segundos. Deve ser conferido contra DFT no sistema de interesse."),
        ("Nível de cálculo (selo)", "Toda energia vale só para o método com que foi calculada. Por isso cada resultado deste painel traz um selo com o nível e o programa, lidos do próprio arquivo de saída."),
        ("SCF", "Ciclo autoconsistente: o programa ajusta os orbitais repetidamente até que a energia e a densidade parem de mudar. Cada iteração aparece como um ponto no gráfico de convergência."),
        ("Critério de convergência do SCF", "Limite abaixo do qual o SCF é considerado convergido. Cada programa compara uma grandeza diferente: no CP2K (OT) é a coluna 'Convergence' contra EPS_SCF; no ORCA, ΔE e a variação da densidade; no VASP, ΔE contra EDIFF; no pw.x, a 'estimated scf accuracy' contra conv_thr."),
        ("Otimização de geometria", "Sequência de passos em que os átomos se movem na direção em que a energia cai, até as forças ficarem pequenas. O 'filme' mostra esse caminho."),
        ("fmax", "A maior força restante sobre um átomo (eV/Å). Uma otimização termina quando fmax fica abaixo do critério escolhido."),
        ("σ (tensão)", "Tensão interna de um cristal (GPa). Com a célula livre, a otimização também ajusta a caixa até a tensão ficar pequena."),
        ("Célula e supercélula", "A célula unitária é a caixa que se repete para formar o cristal; a supercélula mostra várias cópias lado a lado para enxergar a vizinhança."),
        ("|Δr|", "Quanto cada átomo se moveu da geometria inicial até a final (descontada a translação/rotação de moléculas ou a deformação da célula)."),
        ("Frequência vibracional", "Cada modo normal é um jeito coletivo de os átomos vibrarem, com uma frequência (cm⁻¹). Uma frequência imaginária (negativa) indica que a geometria não é um mínimo naquela direção (ou ruído numérico)."),
        ("ZPE", "Energia de ponto zero: a energia vibracional que resta mesmo a 0 K, soma de metade de cada frequência."),
        ("Perfil de energia", "Diagrama dos níveis de energia relativos (reagentes, intermediários, estados de transição, produtos) ou das parcelas de um ciclo termodinâmico."),
        ("Energia de interação", "Diferença entre a energia do complexo e a soma das partes isoladas; negativa quando a associação é favorável. Sem correção de BSSE e sem ZPE, salvo indicação."),
        ("Confôrmeros / microestados", "Arranjos diferentes do mesmo sistema. O ranking compara as energias relativas; barras de erro mostram a dispersão entre réplicas (partidas diferentes)."),
        ("Exploratório", "Resultado preliminar, ainda não validado: serve para orientar, não para concluir."),
        ("Erro de força |ΔF|", "Diferença, átomo a átomo, entre as forças de dois métodos na MESMA geometria (por exemplo, um MLIP e o DFT). O MAE de força é a média de |ΔF| sobre as componentes x, y, z de todos os átomos, em meV/Å; colorir os átomos por |ΔF| mostra onde o método avaliado erra."),
        ("MAE, Spearman, Kendall", "MAE: erro médio absoluto. Spearman e Kendall medem se dois métodos ordenam os arranjos da mesma forma (1 = mesma ordem, 0 = sem relação). Um MAE pequeno com a ordem trocada ainda é um problema quando o que importa é qual arranjo é o mais estável."),
        ("Regra de decisão", "Uma regra escrita antes de olhar o resultado: quais grandezas entram, qual estatística as combina e a partir de que valor cada conclusão (estabelecido, refutado, inconclusivo) vale. A margem diz a que distância do limiar o resultado ficou."),
        ("Ressalva", "Limitação conhecida de um resultado (método, geometria, definição escolhida depois de ver os dados...). Aparece junto da seção ou da estrutura a que se aplica, inclusive na etiqueta do modo Ampliar."),
    ],
    "en": [
        ("DFT", "Density functional theory: computes the energy from the electron density. The most common quantum-chemical method; slower, but reliable when the functional is adequate."),
        ("Functional and basis", "The functional (PBE, B3LYP, B97-3c...) approximates electron–electron interaction; the basis (def2-SVP, TZV2P, plane waves with a cutoff...) describes the orbitals. Together they define the 'level of theory'."),
        ("MLIP", "Machine-learning interatomic potential (UMA, MACE, CHGNet...): a neural network trained on millions of DFT calculations that predicts energies and forces in seconds. Check it against DFT on your system."),
        ("Level of theory (badge)", "An energy is only meaningful for the method that produced it. Every result here carries a badge with the level and program, read from the output file itself."),
        ("SCF", "Self-consistent field: the program updates the orbitals until energy and density stop changing. Each iteration is a point on the convergence plot."),
        ("SCF convergence criterion", "Threshold below which the SCF is converged. Each program compares a different quantity: CP2K (OT) compares the 'Convergence' column with EPS_SCF; ORCA, ΔE and the density change; VASP, ΔE against EDIFF; pw.x, the 'estimated scf accuracy' against conv_thr."),
        ("Geometry optimization", "A sequence of steps moving atoms downhill in energy until forces are small. The 'movie' shows this path."),
        ("fmax", "Largest remaining force on an atom (eV/Å). An optimization stops when fmax drops below the chosen threshold."),
        ("σ (stress)", "Internal stress of a crystal (GPa). With a free cell, the box is also optimized until the stress is small."),
        ("Cell and supercell", "The unit cell is the repeating box of a crystal; a supercell shows several copies side by side."),
        ("|Δr|", "How far each atom moved from the initial to the final geometry (rigid translation/rotation of molecules or cell deformation removed)."),
        ("Vibrational frequency", "Each normal mode is a collective vibration with a frequency (cm⁻¹). An imaginary (negative) frequency means the geometry is not a minimum along that mode (or numerical noise)."),
        ("ZPE", "Zero-point energy: vibrational energy left even at 0 K, half the sum of the frequencies."),
        ("Energy profile", "Diagram of relative energy levels (reactants, intermediates, transition states, products) or of the terms of a thermodynamic cycle."),
        ("Interaction energy", "Energy of the complex minus the sum of the isolated parts; negative when association is favourable. No BSSE correction or ZPE unless stated."),
        ("Conformers / microstates", "Different arrangements of the same system. The ranking compares relative energies; error bars show the spread between replicas (different starting points)."),
        ("Exploratory", "Preliminary, not yet validated result: useful for guidance, not for conclusions."),
        ("Force error |ΔF|", "Atom-by-atom difference between the forces of two methods on the SAME geometry (for example an MLIP and DFT). The force MAE is the mean of |ΔF| over the x, y, z components of every atom, in meV/Å; colouring atoms by |ΔF| shows where the assessed method goes wrong."),
        ("MAE, Spearman, Kendall", "MAE: mean absolute error. Spearman and Kendall tell whether two methods rank the arrangements the same way (1 = same order, 0 = unrelated). A small MAE with the order swapped is still a problem when what matters is which arrangement is the most stable."),
        ("Decision rule", "A rule written before looking at the result: which quantities enter, which statistic combines them and from which value each conclusion (established, refuted, inconclusive) holds. The margin says how far from the threshold the result landed."),
        ("Caveat", "A known limitation of a result (method, geometry, a definition chosen after seeing the data...). It shows next to the section or structure it applies to, including in the badge of the Zoom mode."),
    ],
}


TXT_NOVO = {
    "pt": {
        "r_orca_scf_nota": "o ORCA exige também TolRMSP/TolMaxP; o gráfico mostra |ΔE| contra TolE",
        "r_orca_scf_nota_p": "o ORCA exige também TolRMSP/TolMaxP; o gráfico mostra |ΔE| contra TolE e RMS-DP contra TolRMSP = {v}",
        "r_quadros_de": "quadros lidos de {arq}", "r_ilegivel": "{arq} ilegível: {erro}",
        "r_hess_discorda": "frequências do .out e do .hess discordam; usando as do .hess",
        "r_hess_ilegivel": "{arq} ilegível ({erro}); só as frequências do .out",
        "r_nivel_de": "nível lido de {arq} (a saída não o imprime)",
        "r_cp2k_crit": "compare a coluna Convergence do CP2K com EPS_SCF (não o ΔE da última coluna)",
        "r_scf_nao_conv": "SCF não convergiu (SCF run NOT converged)",
        "r_oszicar": "OSZICAR ilegível: {erro}", "r_outcar_freq": "frequências do OUTCAR ilegíveis: {erro}",
        "r_vasp_crit": "o VASP compara a variação de energia entre iterações eletrônicas com EDIFF",
        "r_gauss_crit": "o Gaussian compara a variação RMS da matriz densidade (RMSDP) com o critério pedido",
        "r_qe_crit": "o pw.x compara a 'estimated scf accuracy' com conv_thr",
        "r_qe_ase": "geometrias não lidas pelo ASE (espresso-out): {erro}",
        "r_est_ilegivel": "estrutura {est} ilegível: {erro}", "r_nao_achado": "arquivo não encontrado: {arq}",
        "r_nao_li": "{arq}: não consegui ler ({tipo}: {erro})",
        "r_e_molden": "Molden sem [FREQ]/[FR-NORM-COORD] consistentes",
        "r_e_gauss_freq": "bloco de frequências do Gaussian sem modos legíveis",
        "r_e_sem_estrutura": "nenhuma estrutura reconhecida no arquivo",
        "r_e_json": "JSON sem esquema reconhecido (freqs_cm1 / energia_eV / energia_Ha)",
        "r_e_sel": "seleção desconhecida: {t}", "r_e_medida": "tipo de medida desconhecido: {tipo}",
        "r_e_expr": "expressão não permitida: {x}",
        "m_tarefa_curto": "tarefa", "faixas_padrao": ["excelente", "aceitável", "marginal", "falha"],
        "av_registro": "{}: registro {} ilegível ({})", "av_ref_ilegivel": "{}: referência ilegível ({})",
        "av_forca_def": "forças {}: informe 'a' e 'b' (ids de estrutura) ou 'estrutura' + 'json'",
        "av_forca_ausente": "forças {}: estrutura '{}' ausente",
        "av_forca_sem": "forças {}: '{}' não traz forças lidas do arquivo",
        "av_forca_n": "forças {}: '{}' e '{}' não têm o mesmo número de átomos",
        "av_forca_geom": "forças {}: as geometrias de '{}' e '{}' diferem em até {:.3f} Å (limite {} Å); não é o mesmo ponto e a comparação foi ignorada",
        "av_forca_json": "forças {}: JSON por átomo ilegível ({})",
        "av_forca_json_n": "forças {}: o JSON tem {} valores e a estrutura '{}' tem {} átomos",
        "av_forca_dup": "forças {}: a estrutura '{}' já tem a coloração de erro de outro par; mantido o primeiro",
        "av_cmp_def": "energia relativa {}: sem itens", "av_cmp_item": "energia relativa {} · item '{}': {}",
        "av_cmp_ref": "energia relativa {}: a referência '{}' não está entre os itens; usando '{}'",
        "av_cmp_poucos": "energia relativa {}: menos de 2 itens com energia nos dois métodos; omitida",
        "av_regra_gr": "regra {} · grandeza {}: {}", "av_regra_expr": "regra {}: {}",
        "av_regra_sem": "regra {}: sem veredito (faltam: {})",
        "av_regra_pos": "regra {}: a estatística foi fixada depois de ver os dados e não há tabela de sensibilidade; declare definições alternativas em 'sensibilidade'",
        "av_ressalva": "ressalva sem texto ignorada", "av_ressalva_alvo": "ressalva '{}': o alvo '{}' não existe",
        "av_cfg_tipo": "'{}' precisa ser uma lista",
    },
    "en": {
        "r_orca_scf_nota": "ORCA also requires TolRMSP/TolMaxP; the plot shows |ΔE| against TolE",
        "r_orca_scf_nota_p": "ORCA also requires TolRMSP/TolMaxP; the plot shows |ΔE| against TolE and RMS-DP against TolRMSP = {v}",
        "r_quadros_de": "frames read from {arq}", "r_ilegivel": "{arq} unreadable: {erro}",
        "r_hess_discorda": "frequencies in the .out and the .hess disagree; using the .hess ones",
        "r_hess_ilegivel": "{arq} unreadable ({erro}); using only the frequencies in the .out",
        "r_nivel_de": "level read from {arq} (the output does not print it)",
        "r_cp2k_crit": "compare CP2K's Convergence column with EPS_SCF (not the ΔE in the last column)",
        "r_scf_nao_conv": "SCF did not converge (SCF run NOT converged)",
        "r_oszicar": "OSZICAR unreadable: {erro}", "r_outcar_freq": "OUTCAR frequencies unreadable: {erro}",
        "r_vasp_crit": "VASP compares the energy change between electronic iterations with EDIFF",
        "r_gauss_crit": "Gaussian compares the RMS change of the density matrix (RMSDP) with the requested criterion",
        "r_qe_crit": "pw.x compares the 'estimated scf accuracy' with conv_thr",
        "r_qe_ase": "geometries not read by ASE (espresso-out): {erro}",
        "r_est_ilegivel": "structure {est} unreadable: {erro}", "r_nao_achado": "file not found: {arq}",
        "r_nao_li": "{arq}: could not read ({tipo}: {erro})",
        "r_e_molden": "Molden without consistent [FREQ]/[FR-NORM-COORD]",
        "r_e_gauss_freq": "Gaussian frequency block without readable modes",
        "r_e_sem_estrutura": "no structure recognised in the file",
        "r_e_json": "JSON with no recognised schema (freqs_cm1 / energia_eV / energia_Ha)",
        "r_e_sel": "unknown selection: {t}", "r_e_medida": "unknown measure type: {tipo}",
        "r_e_expr": "expression not allowed: {x}",
        "m_tarefa_curto": "task", "faixas_padrao": ["excellent", "acceptable", "marginal", "fail"],
        "av_registro": "{}: record {} unreadable ({})", "av_ref_ilegivel": "{}: unreadable reference ({})",
        "av_forca_def": "forces {}: give 'a' and 'b' (structure ids) or 'estrutura' + 'json'",
        "av_forca_ausente": "forces {}: structure '{}' is missing",
        "av_forca_sem": "forces {}: '{}' has no forces read from its file",
        "av_forca_n": "forces {}: '{}' and '{}' do not have the same number of atoms",
        "av_forca_geom": "forces {}: the geometries of '{}' and '{}' differ by up to {:.3f} Å (limit {} Å); they are not the same point and the comparison was skipped",
        "av_forca_json": "forces {}: unreadable per-atom JSON ({})",
        "av_forca_json_n": "forces {}: the JSON has {} values and structure '{}' has {} atoms",
        "av_forca_dup": "forces {}: structure '{}' already has the error colouring of another pair; keeping the first",
        "av_cmp_def": "relative energy {}: no items", "av_cmp_item": "relative energy {} · item '{}': {}",
        "av_cmp_ref": "relative energy {}: reference '{}' is not among the items; using '{}'",
        "av_cmp_poucos": "relative energy {}: fewer than 2 items with energies from both methods; omitted",
        "av_regra_gr": "rule {} · quantity {}: {}", "av_regra_expr": "rule {}: {}",
        "av_regra_sem": "rule {}: no verdict (missing: {})",
        "av_regra_pos": "rule {}: the statistic was fixed after seeing the data and there is no sensitivity table; declare alternative definitions under 'sensibilidade'",
        "av_ressalva": "caveat without text ignored", "av_ressalva_alvo": "caveat '{}': target '{}' does not exist",
        "av_cfg_tipo": "'{}' must be a list",
    },
}
for _l in TXT:
    TXT[_l].update(TXT_NOVO[_l])


class Msg(str):
    """texto em português (padrão) que guarda a chave e os campos, para ser traduzido na hora de gravar no painel."""

    def __new__(cls, chave, **kw):
        obj = super().__new__(cls, TXT["pt"][chave].format(**kw))
        obj.chave, obj.kw = chave, kw
        return obj


def traduzir(x, lang="pt"):
    """Msg (ou exceção cujo primeiro argumento é Msg) -> texto no idioma; qualquer outra coisa volta como veio."""
    if isinstance(x, BaseException) and x.args and isinstance(x.args[0], Msg):
        x = x.args[0]
    if isinstance(x, Msg):
        d = TXT.get(lang, TXT["pt"])
        return (d.get(x.chave) or TXT["pt"][x.chave]).format(**{k: traduzir(v, lang) for k, v in x.kw.items()})
    return x
