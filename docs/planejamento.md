# Planejamento — Painel das Contas de Paulínia

## Objetivo

Responder, em linguagem simples, as perguntas que um morador faria sobre o dinheiro da prefeitura,
usando apenas dados oficiais e públicos.

## Estado atual (28/08/2026)

Protótipo funcional em `painel/index.html`, com dados de 2023, 2024 e 2025 (anos completos), organizado em 4 abas: Visão geral · Pessoal · Gasto a gasto · Entenda.

Seções: cabeçalho com números-chave (gasto total, por morador, arrecadado, % em pessoal, % em
investimento) · gasto por área (função), com detalhe por subfunção · pessoal x custeio x
investimento x dívida · divisão por órgão · série mensal comparando anos · receitas por origem ·
receitas x despesas por ano · ranking e busca de fornecedores · **folha de pagamento** (composição, por área com salário-base/adicionais/encargos, por órgão, mês a mês; **servidores** (5.039 ativos em dez/2025, por vínculo, secretaria, cargo, faixas salariais, custo médio); evolução ano a ano de ativos x aposentados com % de crescimento, por morador, % do gasto e % das receitas) · **explorador em funil** (área › serviço › tipo de gasto › fornecedor › cada empenho com descrição, mais busca em todos os pagamentos do ano) · glossário.

## Fontes e decisões

- **TCE-SP, conjunto de dados anual** (`despesas-{ano}.zip`, `receitas-{ano}.zip`): única fonte com
  função/subfunção/elemento. Lido em streaming e filtrado por `codigo_municipio_ibge = 3536505`.
- **Validação**: o "empenhado − anulação" de 2024 (R$ 2.739.224.011,24) bate exatamente com o total
  exibido na página do TCE para Paulínia/2024.
- **"Quanto foi gasto" = Valor Pago.** Empenhado aparece só como complemento.
- **Órgãos somados**: Prefeitura + Câmara + Paulínia Previ. Há dupla contagem parcial nas
  contribuições previdenciárias (a Prefeitura paga à Previ, que paga aposentadorias). Registrado
  como nota no painel; a alternativa (consolidar) exige tratar elementos 3191/3391 e pode ser feita depois.
- **Folha de pagamento** aparece no TCE com fornecedor "MUNICIPIO DE PAULINIA" (elementos 31xx).
  O ranking de fornecedores exclui elementos de pessoal e os órgãos internos.
- **Receitas**: excluídas as intra-orçamentárias (categoria 7). Grupos amigáveis definidos por
  prefixo do código da natureza de receita (ver `RECEITAS` em `processar.py`).
- **População** (IBGE): 2023 = Censo 2022 (110.537); 2024 = 115.690; 2025 = 116.674.
- **API mensal do TCE** (`/api/json/despesas/paulinia/{ano}/{mes}`) funciona, mas não traz função;
  serve para conferência ou para um "mês corrente" antes do CSV anual ser atualizado.

## Ideias para as próximas versões

1. **Comparar com cidades parecidas** (Indaiatuba, Hortolândia, Valinhos, Sumaré) — o mesmo CSV
   tem todos os municípios; basta filtrar outros códigos IBGE. "Paulínia gasta X por morador em
   saúde; a média das vizinhas é Y" é o argumento mais forte para o cidadão.
2. **Orçamento previsto x realizado** — exige a LOA (planejamento municipal também está nos
   conjuntos de dados do TCE: "Planejamento Municipal").
3. **Contratos e licitações** — o TCE publica "Licitações e Contratos" mensalmente.
4. ~~Buscar no histórico dos empenhos~~ — feito (busca global do explorador). Limitação: muitos empenhos têm histórico genérico ("folha de pagamento", "medição 5"); não há campo de bairro/unidade.
5. **Consolidar previdência** para eliminar a dupla contagem.
6. **Publicação**: GitHub Pages (o painel é um HTML único) + GitHub Action mensal que roda os três
   scripts. Considerar versão mobile mais enxuta.
7. **Deflacionar** valores pelo IPCA para comparar anos em termos reais.
8. ~~Servidores por cargo e secretaria~~ — feito (28/08): `baixar_servidores.py` puxa a folha do portal da prefeitura; seção "Quem são os servidores" e funil "Servidor a servidor" (sem nomes/matrículas) na aba Pessoal. Próximos: evolução do headcount por secretaria ano a ano; cruzar secretaria x função do TCE; horas extras por cargo (o portal não separa rubricas).

## Como continuar no Claude Code

Abra o terminal nesta pasta e rode `claude`. O `CLAUDE.md` já dá o contexto. Sugestões de pedidos:
"adicione a comparação com cidades vizinhas", "crie um workflow do GitHub Actions para atualizar
mensalmente", "melhore o layout mobile".
