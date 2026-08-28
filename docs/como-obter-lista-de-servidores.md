> **Resolvido em 28/08/2026:** a lista é obtida automaticamente por `scripts/baixar_servidores.py`, que chama o backend do portal (não precisa exportar manualmente). Texto original mantido como referência.

# Como obter a lista de servidores (para cargo, lotação e custo médio)

Os dados do TCE-SP trazem quanto foi pago em folha, mas **não** trazem quantos servidores existem,
nem cargos ou secretarias. Para isso é preciso a lista de servidores que a própria prefeitura
publica no portal de transparência (Lei de Acesso à Informação exige).

## Passo a passo

1. Abra https://transparencia-paulinia.smarapd.com.br/
2. Procure no menu algo como **Pessoal**, **Servidores**, **Remuneração** ou **Folha de Pagamento**
   (nos portais SMARAPD costuma ficar em "Pessoal → Servidores" ou "Recursos Humanos").
3. Escolha o **mês de referência** (de preferência dezembro de 2025, ou o mês mais recente) e, se
   houver, o órgão (Prefeitura). Deixe os demais filtros em branco para trazer todos.
4. Procure o botão de **exportar** (ícone de planilha, "Exportar", "CSV", "XLS" ou "Excel").
   Se só houver PDF, exporte o PDF mesmo — dá para extrair.
5. Salve o arquivo em `data/raw/` com o nome `servidores_AAAA_MM.csv` (ou `.xlsx`/`.pdf`),
   por exemplo `data/raw/servidores_2025_12.xlsx`.
6. Repita para a **Câmara Municipal** e a **Paulínia Previ**, se tiverem portais separados
   (opcional; o grosso está na Prefeitura).

## O que a lista costuma ter

Nome, matrícula, cargo/função, lotação (secretaria/departamento), vínculo (efetivo, comissionado,
temporário), data de admissão, remuneração bruta e líquida do mês.

## O que faremos com ela

- Contar servidores por secretaria e por cargo → **custo médio mensal por servidor** (a folha do TCE
  dividida pelo número de pessoas), no total e por área.
- Nova aba "Servidores": quantidade e remuneração média por cargo (professor, médico, guarda,
  agente administrativo…), efetivos x comissionados x temporários, distribuição por secretaria.
- Cruzar a lotação (secretaria) com as áreas do TCE (função de governo) para ter a visão "por secretaria".

Sem nomes: o painel público mostrará apenas agregados (por cargo, secretaria e vínculo), nunca
a lista nominal, embora ela seja pública.

## Se não houver exportação

Diga-me qual tela apareceu (pode mandar um print). Alternativas: pedir os dados via e-SIC
(pedido de acesso à informação, prazo de 20 dias) ou usar o navegador com a extensão do Claude
para percorrer as páginas.
