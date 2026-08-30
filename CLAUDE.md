# Painel das Contas de Paulínia

Painel que traduz as despesas e receitas da Prefeitura de Paulínia (SP) para o cidadão comum,
a partir de dados públicos do TCE-SP. Responda em português. Mantenha a linguagem do painel
simples (sem jargão orçamentário sem explicação).

## Estrutura

```
CLAUDE.md                 este arquivo (contexto do projeto)
docs/planejamento.md      planejamento detalhado, perguntas do painel, decisões
docs/como-obter-lista-de-servidores.md  passo a passo para exportar a lista de servidores do portal da prefeitura
docs/comparativo-campinas-paulinia.md  como a comparação com Campinas é feita: fontes, o que entra no bruto
                          recorrente, a tabela de equivalências entre cargos e os limites da comparação
scripts/baixar_dados.py   baixa dados do TCE-SP e filtra Paulínia -> data/raw/
scripts/baixar_servidores.py  baixa a folha por servidor do portal SMARAPD (POST paiportalserver/modulovisao/filter,
                          visão servidor/pagamentoaservidores, 5000 registros/página, retomável) -> data/raw/servidores_{ano}.csv.gz
scripts/tabelas_salariais.py  lê as tabelas de vencimento oficiais (PDFs do módulo escondido
                          "Folha de Pagamento" do portal) e cruza com a folha: quanto cada cargo recebe acima
                          do vencimento da lei. --baixar pega os PDFs, --conferir mostra a cobertura.
                          Usa pdftotext -bbox-layout (coordenadas): parsear o texto alinhado dá errado.
                          ATENÇÃO: LC 66/2017 e LC 133/2025 coexistem com valores diferentes para o mesmo
                          cargo; o casamento respeita a lei que aparece no nome do cargo na folha.
                          -> data/tabelas_salariais.json
scripts/quadro_pessoal.py  lê o Quadro de Pessoal (PDF do mesmo módulo) e separa os servidores por
                          jornada e função designada, para explicar o que puxa o salário acima da tabela.
                          Casa com a folha pela MATRÍCULA (99%). Use o Quadro de SETEMBRO/2025: o de
                          abril/2026 não tem matrícula e traz a admissão como número de série.
                          CUIDADO: jornada designada MENOR que a do cargo (200->180) NÃO significa ganhar
                          menos - esse grupo ganha mais (escala de turno com adicionais).
                          Também mede o TEMPO DE CASA dentro do mesmo cargo E da mesma jornada (a folha dá a
                          admissão, o Quadro dá a jornada): sem controlar a jornada a diferença sai inflada,
                          porque quem tem mais tempo também tende a estar em escala. Cargos fechados a novos
                          concursos (Educadora Infantil, ninguém desde 2007) não têm faixa nova e ficam fora.
                          -> data/decomposicao_folha.json
scripts/comparar_cargos.py  compara salário por cargo entre Paulínia e as cidades importadas.
                          A tabela PARES no topo do arquivo é o julgamento (quais cargos equivalem a quais,
                          com nível de confiança e ressalva); pares de confiança 'baixa' ficam FORA do JSON
                          por padrão. --listar mostra cargos grandes ainda sem par -> data/comparativo_cargos.json
scripts/comparar_cidades.py  Paulínia x as cidades da região: servidores por mil habitantes (IBGE MUNIC
                          2024, administração DIRETA, mesma definição para todos) e arrecadação por
                          habitante (receitas do TCE, sem intra-orçamentárias). --baixar traz a MUNIC e
                          filtra o receitas-{ano}.zip; --refazer rebaixa. O download também grava
                          data/raw/receitas_sp_totais_{ano}.csv (total de TODOS os 644 municípios de SP),
                          que é o que permite a mediana da faixa de porte.
                          --despesas streama o despesas-{ano}.zip (~2 GB, 28 mi de linhas, ~3 min) e grava
                          data/raw/despesas_sp_totais_{ano}.csv: pago, pessoal (elemento 31xx) e folha de
                          ATIVO por município. Mesma régua do processar.py - confere com o painel de Paulínia
                          até o centavo. Rode num terminal de verdade: leva mais que o limite de uma chamada.
                          -> data/comparativo_cidades.json
scripts/importar_servidores.py  importa a folha de OUTRAS cidades a partir do CSV que a prefeitura
                          fornece (download manual: Campinas exige captcha). Mapeia as colunas do portal
                          para o formato de Paulínia -> data/raw/servidores_{cidade}_{ano}_{mes}.csv.gz
                          Use --inspecionar antes, para ver as colunas do arquivo novo.
scripts/processar.py      agrega e gera data/painel.json e data/detalhe_{ano}.js (funil até o empenho)
scripts/montar_painel.py  embute painel.json no template -> painel/index.html
scripts/publicar.py       monta dist/ para o Cloudflare ('../data/' -> 'data/', index na raiz)
data/raw/                 CSVs filtrados de Paulínia (despesas e receitas por ano)
data/painel.json          dados agregados, embutidos no index.html
data/servidores_{ano}.js  secretaria > vínculo > cargo > servidores anônimos [ano adm, bruto mês ref, total ano, 13º, férias, meses, saiu]
data/detalhe_{ano}.js     hierarquia área > subfunção > elemento > fornecedor > empenhos (só pagos), ~3 MB/ano,
                          carregada sob demanda via <script src="../data/detalhe_{ano}.js"> (funciona em file://)
painel/template.html      fonte do painel — EDITE ESTE, nunca o index.html (gerado)
painel/index.html         painel (HTML único, gráficos inline; abre direto no navegador)
dist/                     o que vai para o ar (gerado por publicar.py, versionado; o Worker serve sem build)
```

## Fontes de dados

- **TCE-SP – Portal da Transparência Municipal** (fonte principal, dados AUDESP enviados pela prefeitura)
  - CSVs anuais (todos os municípios de SP, ~2 GB cada; filtramos `codigo_municipio_ibge == 3536505`):
    `https://transparencia.tce.sp.gov.br/sites/default/files/conjunto-dados/despesas-{ano}.zip`
    `https://transparencia.tce.sp.gov.br/sites/default/files/conjunto-dados/receitas-{ano}.zip`
    Separador `;`, codificação Latin-1, decimal com vírgula.
    Colunas de despesas: id_despesa_detalhe, ano_exercicio, ds_municipio, codigo_municipio_ibge, ds_orgao,
    mes_referencia, mes_ref_extenso, tp_despesa (Empenhado/Liquidado/Pago/Reforço/Anulação), nr_empenho,
    tp_identificador_despesa, nr_identificador_despesa (CNPJ/CPF), ds_despesa (fornecedor),
    dt_emissao_despesa, vl_despesa, ds_funcao_governo, ds_subfuncao_governo, cd_programa, ds_programa,
    cd_acao, ds_acao, ds_fonte_recurso, ds_cd_aplicacao_fixo, ds_modalidade_lic, ds_elemento, historico_despesa
  - API mensal (menos campos, sem função): `https://transparencia.tce.sp.gov.br/api/json/despesas/paulinia/{ano}/{mes}`
  - Página: https://transparencia.tce.sp.gov.br/municipio/paulinia/2024/despesas
- Portal oficial da prefeitura (SMARAPD): https://transparencia-paulinia.smarapd.com.br/ — app JS, mas o backend responde a
  POST JSON em `/paiportalserver/modulovisao/filter` (ver baixar_servidores.py). Visão "Pagamentos a Servidores":
  uma linha por servidor x mês x tipo de folha (9 = mensal, 8 = adiantamento salarial já incluído no bruto da mensal, 6 = 13º integral em dezembro, 5 = 1ª parcela do 13º sem descontos, paga em junho (set/2023) e já incluída no bruto do tipo 6, 3 = férias (professores em janeiro), 1 = rescisão, 10 = complementar, 14 = complementar sem descontos). Bruto anual = todos os tipos EXCETO 8 e 5 (senão conta duas vezes); líquido anual = líquido de todos os tipos, inclusive 8 e 5,
  com matrícula, nome, cargo, secretaria (campo Funcao), admissão, rescisão, vencimentos brutos, descontos, líquido.
  Cargo carrega o vínculo: "LC 66/2017"/"LC 65/2017" = efetivos, "(CTD)" = temporários, "Inativo"/"Pensionista" = aposentados
  (na secretaria "Encargos Gerais do Município"), sem sufixo = comissionados/agentes políticos. Ver vinculo() em processar.py.
  Novembro costuma não ter folha mensal carregada; o mês de referência é escolhido automaticamente (último mês completo).
  Custo médio por servidor (portal) = média das folhas mensais + extras do ano/12, por pessoa; custo completo (TCE) = folha de ativos
  da Prefeitura no TCE / headcount médio do ano / 12. Não dividir totais anuais pelo headcount de dezembro (dezembro/2024 caiu 6%).
  Secretarias com prefixo "(NÃO USAR)" são extintas (reforma de mar/2025: Esportes/Cultura separadas; Governo renomeada) — secretaria_curta() limpa o prefixo.
  Headcount é por matrícula (~40 pessoas com dois vínculos ativos). Folha mensal de janeiro dos professores é parcial (férias saem como tipo 3).
  NUNCA expor nomes no painel: só agregados por cargo, secretaria e vínculo.
- Portal da Transparência federal (repasses da União): https://portaldatransparencia.gov.br/localidades/3536505-paulinia
- IBGE: população de Paulínia para valores per capita.

## Regras de negócio importantes

- "Empenhado" = reservado; "Liquidado" = serviço/produto entregue e conferido; "Pago" = dinheiro saiu.
  Para "quanto foi gasto", usar **Pago**; para "quanto foi comprometido", usar Empenhado − Anulação.
- Totais por função devem bater com a página do TCE-SP para o mesmo ano/tipo.
- Rótulos de função em linguagem simples (ex.: "Urbanismo" -> "Cidade: ruas, limpeza e iluminação").

## Perguntas que o painel responde

1. Para onde vai o dinheiro? (por função, R$ e % do total, per capita)
2. Está gastando mais ou menos que antes? (série mensal/anual, comparação entre anos)
3. Para quem a prefeitura paga? (ranking de fornecedores, busca por nome/CNPJ)
4. Quanto entra e de onde vem? (receitas x despesas)
5. Folha de pagamento: composição (salário-base, adicionais, encargos, aposentadorias…), por área, por órgão, mês a mês.
   Seção "Quem são os servidores": headcount, vínculo, secretaria, cargo, faixas salariais, custo médio (portal da prefeitura).
6. Explorar gasto a gasto: funil área > serviço > tipo de gasto > fornecedor > empenhos + busca global no histórico.
7. Glossário embutido.

## Estrutura do painel (abas)

O painel tem 7 abas, NESTA ordem no menu (navegação por hash): #geral, #detalhe, #pessoal, #salarios,
#comparar, #reforma, #entenda. Cada uma é um `<div class="tab" data-tab="...">`, e a ordem das divs no
arquivo acompanha a ordem do menu.
O #comparar voltou a ser aba própria (só comparação entre cidades), então o redirecionamento que existia
em mostrarTab() foi removido.
- geral: números-chave, por área, natureza/órgãos, mês a mês, receitas, receitas x despesas
- pessoal: folha (composição, por área, mês a mês) · quem são os servidores (agregados) · servidor a servidor (funil
  secretaria › vínculo › cargo › indivíduos anônimos, carregado de data/servidores_{ano}.js) · evolução ativos x aposentados.
  Termina com a ponte "E quanto cada um ganha?" (#irComparar) para a aba salarios.
- salarios: tudo sobre quanto se ganha. "Quanto ganha cada cargo" (tabela por cargo, veio da aba pessoal) +
  "De onde vem o salário" (quanto cada cargo recebe acima da tabela de vencimentos de Paulínia)
  e "Por que dois colegas ganham diferente" (mediana e R$/hora por grupo: horas normais,
  contratado para mais horas, turno/escala, chefia). O R$/hora é o que impede a leitura errada:
  jornada maior NÃO é hora extra (a hora vale quase o mesmo); hora valendo muito mais = adicionais.
  A tabela de vencimento-base dos concursos foi removida do painel a pedido do Bruno. Dados de
  data/comparativo_cargos.json, embutido pelo montar_painel.py (opcional: sem o arquivo as seções somem
  e nada quebra). "De onde vem o salário" e "Por que dois colegas ganham diferente" são de dez/2025 e se
  escondem quando outro ano é escolhido (constante REF no template).
  Fecha com "A folha cabe na arrecadação?": razão folha/receita por ano, calculada direto do painel.json.
  CUIDADO ao mexer nesse texto: a folha NÃO vem crescendo acima da arrecadação no período. De 2023 a 2025 a
  receita subiu 30,7% e a folha 28,2%, e a fatia comprometida caiu de 49,8% para 48,8%. Só 2025 isolado teve
  folha (+9,5%) acima da receita (+1,7%). A nota da seção diz isso; não transforme em tendência.
- comparar: só comparação entre cidades. Hoje: salário mediano por cargo contra Campinas (segue o seletor
  de ano; dezembro de cada ano). É onde entra a futura comparação de gasto/receita por morador com as vizinhas.
  ATENÇÃO ao par de professores: a reclassificação de ago/2025 (PEB I -> Educadora Infantil, mesma
  gente) obriga a somar os dois cargos de Paulínia, senão 2025 sai com +68% em vez de +54%. O campo
  'desde' em PARES limita um par aos anos em que ele faz sentido.
- reforma: dependência do ICMS, calendário da reforma tributária e simulador de queda da cota-parte.
  Os números do estudo estão no objeto RT do template; o resto sai do painel.json. Fonte: Comissão Especial
  da Câmara de Paulínia (fev/2024), que cita Afonso, Caiado, Viana e Biasoto (Conjuntura Econômica/FGV,
  jul/2023) — ano-base 2022, ANTERIOR à LC 214/2025. Queda projetada da cota-parte: 68,4%, gradual entre
  2029 e 2078. O painel não faz projeção própria: reproduz o estudo e mostra a aritmética.
- detalhe: explorador em funil + ranking/busca de fornecedores
- entenda: "A situação de Paulínia, em resumo" (o ÚNICO lugar em que o painel interpreta em vez de só medir;
  CUIDADO: a frase sobre tempo de casa já esteve errada DUAS vezes, sempre no mesmo sentido - dizendo que a
  progressão não explica a distância entre folha e tabela. Explica em parte: dentro do mesmo cargo E da mesma
  jornada, quem passou dos 20 anos de casa recebe +18% na mediana (9 comparações,
  de +2% a +40%; grupos com menos de 8 pessoas em uma das faixas ficam fora, o que derrubou
  as comparações infladas de uma rodada antiga do script). Agora isso é CALCULADO pelo quadro_pessoal.py (bloco tempo_de_casa em
  decomposicao_folha.json) e renderizado na seção #tempocasa da aba Salários, então a frase do resumo lê o
  número do JSON e não pode mais divergir. Se alguém reescrever a frase, o número tem que continuar vindo de TC;
  todos os números são calculados dos mesmos dados das outras abas, nada digitado à mão) + glossário.
  O fecho aponta a aritmética e diz explicitamente que o painel não recomenda caminho nenhum. Mantenha assim.
`mostrarTab(nome)` troca de aba; `irPara(caminho)` abre o explorador na aba detalhe.

## Comparação com outras cidades

- **Servidores por habitante depende muito do porte da cidade** (mediana paulista: 67/mil abaixo de 10 mil
  habitantes, 14/mil acima de 500 mil). Por isso "Paulínia tem 3,2x mais servidores que Campinas" mede
  sobretudo tamanho e **não deve ser usado**. A referência honesta é a mediana dos 96 municípios de SP na
  faixa de Paulínia (50-200 mil): 29,3/mil contra 43,8/mil, ou **~1,5x**, acima de 94% deles. O painel usa
  essa referência; a comparação com Campinas fica só para o **formato** (quais áreas puxam) e para o
  **salário**, onde o porte não distorce.
- O outro lado da conta: Paulínia arrecada **R$ 24.752 por morador**, 4,1x a mediana das cidades do mesmo
  porte. As três cidades da região com mais servidores por morador (Paulínia, Vinhedo, Jaguariúna) são
  exatamente as três mais ricas por morador. É assim que a conta fecha hoje - e é esse lado que a reforma muda.
- Custo de pessoal por morador = ~1,5x mais servidores x ~1,5x o salário médio de Campinas = ~2,2x.
  **Os dois fatores pesam parecido**; a versão antiga do texto dizia "o efetivo pesa mais que o salário",
  o que vinha da comparação distorcida com Campinas. Não voltar a isso.
- Nomes de município divergem entre as fontes ("Santa Bárbara d Oeste" no TCE, "Santa Bárbara dOeste" na
  MUNIC, "Santa Barbara D'Oeste" à mão): `norm()` do comparar_cidades.py tira acento, pontuação **e espaços**.
  O dicionário GRAFIA conserta só a exibição.
- **A folha de Paulínia NÃO sufoca o orçamento**: 50,2% do que a cidade gasta, contra 47,2% na mediana da faixa
  de porte (acima de só 75% delas). Não é o número de alarme e não deve ser usado como tal. O que está fora da
  curva é o **custo médio por servidor: R$ 16.647/mês contra R$ 6.772 na mediana (2,5x), acima de 99% delas**.
  A folha cabe porque o orçamento é 4x maior, não porque seja barata.
- **Custo médio não é salário**: folha de ativo (31xx menos 319001/319003/319091/319094/3171) / efetivo / 12.
  Inclui encargos patronais, hora extra, 13º e férias - ~12% acima do bruto médio da folha de Paulínia.
  Divisor = MUNIC direta + indireta - estagiários (bolsa não sai no 31xx), porque a despesa do TCE cobre todos
  os órgãos do município. A coluna de servidores/mil usa só a DIRETA (é a medida comparável por porte), então
  as duas colunas têm divisores diferentes de propósito - não multiplique uma pela outra.
- A MUNIC conta administração DIRETA. Campinas tem outras 6.546 pessoas na indireta, fora da conta - por isso
  a nota da seção diz isso na cara.

- O TCE **não** publica dados de pessoal (conferido: os 10 conjuntos são despesas, receitas, RCL, dívida ativa,
  licitações, pareceres, planejamento e afins). Folha por servidor só vem do portal de cada prefeitura.
- **Campinas**: exportação CSV em remuneracoes.campinas.sp.gov.br, com **reCAPTCHA** — download manual, o Bruno
  faz. Filtros: Secretarias/Lotações/Cargos em "Todos", Ano, Mês (usar **dezembro**, igual a Paulínia).
  Com tudo marcado o servidor às vezes devolve 503; nesse caso exportar por secretaria. O captcha é de uso único.
  O arquivo não traz nome, admissão nem jornada; traz o bruto quebrado em 11 parcelas.
- Ao comparar, cuidado: **PEB I e PEB II significam coisas diferentes nas duas cidades** (em Paulínia PEB I vai da
  creche ao 5º ano; em Campinas PEB I é só educação infantil e PEB II são os anos iniciais). E **Paulínia paga por
  hora-aula de 50 minutos**, Campinas por hora-relógio. Detalhes e fontes legais em
  `docs/comparativo-campinas-paulinia.md`.

## Convenções

- Python 3, apenas biblioteca padrão + pandas quando necessário.
- O painel é um HTML único, sem build step; dados embutidos ou carregados de `data/painel.json`.
- Não commitar os ZIPs brutos do TCE (grandes); só os CSVs filtrados de Paulínia (gzip).
- Repositório público: `data/raw/servidores_*.csv.gz` tem nome/matrícula/salário individual e fica no .gitignore.
- Depois de mexer no template ou nos dados: `montar_painel.py` e depois `publicar.py`, senão o site sai desatualizado.
- Publicado em painel-paulinia.bj-moretti85.workers.dev (Cloudflare Worker ligado ao GitHub; `git push` republica).
- As linhas acima já se perderam 4x em edições externas — preserve-as (publicar.py avisa se sumirem).
- Nomes de subfunção usam .capitalize() nos dois arquivos (painel.json e detalhe) — o painel navega por nome.
