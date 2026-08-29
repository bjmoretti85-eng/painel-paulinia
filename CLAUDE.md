# Painel das Contas de Paulínia

Painel que traduz as despesas e receitas da Prefeitura de Paulínia (SP) para o cidadão comum,
a partir de dados públicos do TCE-SP. Responda em português. Mantenha a linguagem do painel
simples (sem jargão orçamentário sem explicação).

## Estrutura

```
CLAUDE.md                 este arquivo (contexto do projeto)
docs/planejamento.md      planejamento detalhado, perguntas do painel, decisões
docs/como-obter-lista-de-servidores.md  passo a passo para exportar a lista de servidores do portal da prefeitura
scripts/baixar_dados.py   baixa dados do TCE-SP e filtra Paulínia -> data/raw/
scripts/baixar_servidores.py  baixa a folha por servidor do portal SMARAPD (POST paiportalserver/modulovisao/filter,
                          visão servidor/pagamentoaservidores, 5000 registros/página, retomável) -> data/raw/servidores_{ano}.csv.gz
scripts/comparar_cargos.py  compara salário por cargo entre Paulínia e as cidades importadas.
                          A tabela PARES no topo do arquivo é o julgamento (quais cargos equivalem a quais,
                          com nível de confiança e ressalva); pares de confiança 'baixa' ficam FORA do JSON
                          por padrão. --listar mostra cargos grandes ainda sem par -> data/comparativo_cargos.json
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

O painel tem 5 abas (navegação por hash: #geral, #pessoal, #comparar, #detalhe, #entenda), cada uma é um `<div class="tab" data-tab="...">`:
- geral: números-chave, por área, natureza/órgãos, mês a mês, receitas, receitas x despesas
- pessoal: folha (composição, por área, mês a mês) · quem são os servidores (agregados) · servidor a servidor (funil
  secretaria › vínculo › cargo › indivíduos anônimos, carregado de data/servidores_{ano}.js) · evolução ativos x aposentados
- comparar: Paulínia x outras cidades. Hoje: salário mediano por cargo contra Campinas (dez/2025) +
  vencimento-base por jornada equivalente. Dados de data/comparativo_cargos.json, embutido pelo montar_painel.py
  (opcional: sem o arquivo a aba fica vazia e nada quebra). A aba pessoal tem um botão-ponte (#irComparar).
- detalhe: explorador em funil + ranking/busca de fornecedores
- entenda: glossário
`mostrarTab(nome)` troca de aba; `irPara(caminho)` abre o explorador na aba detalhe.

## Comparação com outras cidades

- O TCE **não** publica dados de pessoal (conferido: os 10 conjuntos são despesas, receitas, RCL, dívida ativa,
  licitações, pareceres, planejamento e afins). Folha por servidor só vem do portal de cada prefeitura.
- **Campinas**: exportação CSV em remuneracoes.campinas.sp.gov.br, com **reCAPTCHA** — download manual, o Bruno
  faz. Filtros: Secretarias/Lotações/Cargos em "Todos", Ano, Mês (usar **dezembro**, igual a Paulínia).
  Com tudo marcado o servidor às vezes devolve 503; nesse caso exportar por secretaria. O captcha é de uso único.
  O arquivo não traz nome, admissão nem jornada; traz o bruto quebrado em 11 parcelas.
- Ao comparar, cuidado: **PEB I e PEB II significam coisas diferentes nas duas cidades** (em Paulínia PEB I vai da
  creche ao 5º ano; em Campinas PEB I é só educação infantil e PEB II são os anos iniciais). E **Paulínia paga por
  hora-aula de 50 minutos**, Campinas por hora-relógio. Detalhes e fontes legais no doc do projeto
  `claude/comparativo-campinas-paulinia.md`.

## Convenções

- Python 3, apenas biblioteca padrão + pandas quando necessário.
- O painel é um HTML único, sem build step; dados embutidos ou carregados de `data/painel.json`.
- Não commitar os ZIPs brutos do TCE (grandes); só os CSVs filtrados de Paulínia (gzip).
- Repositório público: `data/raw/servidores_*.csv.gz` tem nome/matrícula/salário individual e fica no .gitignore.
- Depois de mexer no template ou nos dados: `montar_painel.py` e depois `publicar.py`, senão o site sai desatualizado.
- Publicado em painel-paulinia.bj-moretti85.workers.dev (Cloudflare Worker ligado ao GitHub; `git push` republica).
- As linhas acima já se perderam 4x em edições externas — preserve-as (publicar.py avisa se sumirem).
- Nomes de subfunção usam .capitalize() nos dois arquivos (painel.json e detalhe) — o painel navega por nome.
