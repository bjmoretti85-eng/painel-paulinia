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
  uma linha por servidor x mês x tipo de folha (9 = mensal, 8 = adiantamento já incluído na mensal, 6 = 13º em dezembro, 3 = folha de férias em janeiro, 5 = abono 1/3 de férias em junho, 1 = rescisão, 10 = complementar, 14 = complementar sem descontos; os tipos 8 e 9 do mesmo mês somados dão o líquido recebido),
  com matrícula, nome, cargo, secretaria (campo Funcao), admissão, rescisão, vencimentos brutos, descontos, líquido.
  Cargo carrega o vínculo: "LC 66/2017"/"LC 65/2017" = efetivos, "(CTD)" = temporários, "Inativo"/"Pensionista" = aposentados
  (na secretaria "Encargos Gerais do Município"), sem sufixo = comissionados/agentes políticos. Ver vinculo() em processar.py.
  Novembro costuma não ter folha mensal carregada; o mês de referência é escolhido automaticamente (último mês completo).
  Custo médio por servidor (portal) = média das folhas mensais + extras do ano/12, por pessoa; custo completo (TCE) = folha de ativos
  da Prefeitura no TCE / headcount médio do ano / 12. Não dividir totais anuais pelo headcount de dezembro (dezembro/2024 caiu 6%).
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

O painel tem 4 abas (navegação por hash: #geral, #pessoal, #detalhe, #entenda), cada uma é um `<div class="tab" data-tab="...">`:
- geral: números-chave, por área, natureza/órgãos, mês a mês, receitas, receitas x despesas
- pessoal: folha (composição, por área, mês a mês) · quem são os servidores (agregados) · servidor a servidor (funil
  secretaria › vínculo › cargo › indivíduos anônimos, carregado de data/servidores_{ano}.js) · evolução ativos x aposentados
- detalhe: explorador em funil + ranking/busca de fornecedores
- entenda: glossário
`mostrarTab(nome)` troca de aba; `irPara(caminho)` abre o explorador na aba detalhe.

## Convenções

- Python 3, apenas biblioteca padrão + pandas quando necessário.
- O painel é um HTML único, sem build step; dados embutidos ou carregados de `data/painel.json`.
- Não commitar os ZIPs brutos do TCE (grandes); só os CSVs filtrados de Paulínia (gzip).
- Repositório público: `data/raw/servidores_*.csv.gz` tem nome/matrícula/salário individual e fica no .gitignore.
- Depois de mexer no template ou nos dados: `montar_painel.py` e depois `publicar.py`, senão o site sai desatualizado.
- Publicado em painel-paulinia.bj-moretti85.workers.dev (Cloudflare Worker ligado ao GitHub; `git push` republica).
- ESTAS TRÊS LINHAS E AS DUAS DE publicar.py/dist/ ACIMA JÁ SE PERDERAM DUAS VEZES EM EDIÇÕES DO ARQUIVO — preserve-as.
- Nomes de subfunção usam .capitalize() nos dois arquivos (painel.json e detalhe) — o painel navega por nome.
