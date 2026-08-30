# Comparar salário por cargo: Paulínia × Campinas

Este documento reúne o que já estava espalhado pelos scripts (`comparar_cargos.py`,
`importar_servidores.py`) e pelo `CLAUDE.md`, para que a aba **Salários** do painel possa ser
defendida número a número.

> **Atenção:** os textos legais citados aqui (leis complementares, editais) **não estão no
> repositório** — são as fontes que o projeto declara. Antes de usar este documento para
> responder a uma cobrança pública, confira cada um deles na fonte oficial.

## 1. De onde vem cada folha

| | Paulínia | Campinas |
|---|---|---|
| Portal | SMARAPD (`transparencia-paulinia.smarapd.com.br`) | `remuneracoes.campinas.sp.gov.br` |
| Download | automático (`baixar_servidores.py`) | **manual** — o portal exige reCAPTCHA |
| Traz nome? | sim (fica fora do repositório, no `.gitignore`) | não |
| Traz admissão/jornada? | admissão sim, jornada não | nenhuma das duas |
| Formato do bruto | uma linha por servidor × mês × tipo de folha | uma linha por servidor, com o bruto quebrado em 11 parcelas |

Para exportar Campinas: filtros Secretarias / Lotações / Cargos em "Todos", escolher o ano e o
mês **dezembro** (o mesmo mês usado em Paulínia). Com tudo marcado o servidor às vezes devolve
503 — nesse caso, exportar secretaria por secretaria. O captcha é de uso único.

## 2. Qual número entra na comparação

Comparamos a **mediana do bruto recorrente de dezembro**, entre servidores ativos.

- **Mediana, não média**: poucos salários muito altos distorceriam a média.
- **Dezembro nos dois lados**: mês igual evita comparar épocas diferentes do ano.
- **Bruto recorrente** = o bruto do mês **menos as verbas que não se repetem todo mês**.
  - Em Paulínia isso sai de graça: usamos só a folha mensal (`tipo_folha = 9`), que já exclui
    13º, férias e complementares. Aposentados e pensionistas ficam de fora.
  - Em Campinas é preciso subtrair parcela a parcela: **13º Salário, Prêmio Férias,
    Licença Prêmio, Salário Atraso e Eventual**.

### Por que "Eventual" também é descontado

Em **dezembro de 2023**, 86% dos professores de Campinas (1.890 de 2.198) receberam um
"Eventual" de R$ 6.328 (mediana), e 81% de toda a Educação recebeu algo semelhante. Em dezembro
de 2024 e de 2025 esse campo aparece em apenas 2% dos servidores, com mediana de R$ 200 a R$ 300.
O padrão — uma vez só, concentrado na Educação, em dezembro de 2023 — é o do rateio do Fundeb.

Enquanto o "Eventual" era contado como salário recorrente, a comparação de 2023 saía invertida:

| Cargo (2023) | Campinas com o Eventual | Sem o Eventual | Diferença antes | Diferença corrigida |
|---|---|---|---|---|
| Professor dos anos iniciais | R$ 13.884 | R$ 8.010 | −2% | **+70%** |
| Professor de creche e pré-escola | R$ 13.938 | R$ 7.986 | −32% | **+19%** |
| Agente de apoio operacional | R$ 4.854 | R$ 4.028 | +74% | **+109%** |

Em 2024 e 2025 a correção mexe no máximo 3 pontos percentuais. O lado de Paulínia foi conferido
e está limpo: em dezembro o PEB I fica 5% **abaixo** do mês típico, ou seja, não há abono
embutido na folha mensal.

## 3. A tabela de equivalências

O julgamento mora na constante `PARES`, no topo de `scripts/comparar_cargos.py` — é lá que se
altera, não no painel. Cada par declara a confiança:

- **alta** — mesmo cargo, mesma função, jornada conhecida e parecida;
- **media** — mesma função, mas jornada ou carreira diferem;
- **baixa** — fica **fora** do JSON por padrão (só entra com `--incluir-baixa`).

| Par | Paulínia | Campinas | Confiança | Ressalva |
|---|---|---|---|---|
| Professor dos anos iniciais e da educação infantil | PEB I (LC 65/2017) **+ Educadora Infantil (LC 66/2017)** | PEB I + PEB II | media | os nomes significam coisas diferentes nas duas cidades — ver abaixo. Os dois cargos de Paulínia são somados por causa da reclassificação de ago/2025 |
| Professor de creche e pré-escola | Educadora Infantil (LC 66/2017) | PEB I | media | **só de 2025 em diante** (campo `desde`): antes o cargo tinha ~50 pessoas, porque quem fazia creche estava no PEB I. **Não** comparar com o Agente de Educação Infantil de Campinas, que é cargo de apoio, de ensino médio |
| Guarda municipal | Guarda Civil Municipal | todos os cargos "GM …" | media | Campinas divide por classe e até por sexo ("GM 1 Classe Masculino/Feminino"); somamos todos. Paulínia tem cargo único, o que mistura níveis de carreira dos dois lados |
| Enfermeiro | LC 66/2017 | Enfermeiro | alta | em Campinas inclui a Rede Mário Gatti (hospital municipal) |
| Técnico de enfermagem | LC 66/2017 | Técnico Enfermagem | alta | idem, inclui a Rede Mário Gatti |
| Auxiliar de enfermagem | LC 66/2017 | Aux. Enfermagem | alta | cargo em extinção nas duas redes; o efetivo tende a cair |
| Agente de apoio operacional | LC 66/2017 | Ag. Apoio Operacional | media | é o cargo mais numeroso de Paulínia e junta funções variadas; a comparação de atribuição é frouxa |
| Agente administrativo | Auxiliar de Apoio Administrativo | Ag. Administrativo | **baixa** | nomes parecidos, atribuições possivelmente diferentes — **não publicado** |

### PEB I e PEB II não querem dizer a mesma coisa

- Em **Paulínia**, o PEB I cobre creche, pré-escola e do 1º ao 5º ano.
- Em **Campinas**, o PEB I é só educação infantil e o PEB II são os anos iniciais.

Por isso o par soma PEB I + PEB II de Campinas. Os professores temporários (CTD) de Paulínia
ficam de fora. As duas carreiras da educação infantil estão em mudança por causa da Lei federal
15.326/2026.

### A reclassificação de agosto de 2025

Entre julho e agosto de 2025, cerca de 350 servidores saíram do PEB I para Educadora Infantil —
**ajuste de lei, as mesmas pessoas**. O efetivo do PEB I caiu de 845 para 496 e o da Educadora
Infantil subiu de 43 para 390.

Isso quebrou a comparação de 2025 enquanto o par usava só o PEB I: o lado de Paulínia ficou só com
os anos iniciais (mais bem pagos) enquanto o lado de Campinas continuava incluindo a educação
infantil. A diferença saía **+68%** quando o certo era **+54%**. Somando os dois cargos de Paulínia,
a população fica estável nos três anos (883, 885, 864) e equivalente ao escopo de Campinas:

| Ano | Paulínia (PEB I + Educadora) | Campinas (PEB I + PEB II) | Diferença |
|---|---|---|---|
| 2023 | R$ 13.167 (883) | R$ 8.010 | +64% |
| 2024 | R$ 13.901 (885) | R$ 8.399 | +66% |
| 2025 | R$ 14.003 (864) | R$ 9.103 | +54% |

A queda de 2025 é real e do lado de Campinas: a mediana de lá subiu 14% em um ano (R$ 8.399 →
R$ 9.103) enquanto a de Paulínia subiu 6%.

## 4. Hora-aula não é hora-relógio

Paulínia paga o professor por **hora-aula de 50 minutos**; Campinas usa hora-relógio. Comparar
"45 horas" de uma com "40 horas" da outra seria erro: 45 horas-aula equivalem a cerca de 37,5
horas de relógio. Hoje essa ressalva aparece no texto de rodapé da aba, junto com o aviso de que
**parte da diferença que a folha mostra é jornada contratada, não preço da hora**.

Levantamento feito a partir dos editais (Processo Seletivo 001/2026 de Paulínia e Edital 01/2025
de Campinas, PEB II), publicado no painel até o commit `c5c957d` e mantido aqui como registro —
o `comparar_cargos.py` não gera mais essa tabela:

| Paulínia | | Campinas | |
|---|---|---|---|
| 45 horas-aula (≈37,5h) | R$ 7.350,75 | 40 horas | R$ 7.397,41 |
| 38 horas-aula (≈31,7h) | R$ 6.207,30 | 32 horas | R$ 5.917,92 |
| 30 horas-aula (≈25h) | R$ 4.900,50 | 27 horas | R$ 4.993,26 |

Lado a lado, o **salário inicial das duas cidades é praticamente o mesmo**. Ou seja: a diferença
de 30% a 117% que a folha mostra não vem do valor da hora — vem da jornada contratada e das
verbas que cada carreira acumula por cima do vencimento.

No lugar dessa tabela, a aba passou a trazer a seção **"De onde vem o salário"** — a comparação
deixou de ser entre concursos e passou a ser entre a folha e a tabela de vencimentos da própria
Paulínia. Depois dela vem **"Por que dois colegas ganham diferente"**, que separa cada cargo por
jornada e função designada (`scripts/quadro_pessoal.py` → `data/decomposicao_folha.json`) e mostra
o R$/hora de cada grupo — é o que impede ler jornada maior como hora extra.

## 5. De onde vem o salário: folha × tabela de vencimentos

A lei fixa um vencimento para cada cargo; a folha mostra o que cai na conta. A razão entre os dois
diz quanto do salário vem do vencimento e quanto vem de adicionais, gratificações, horas extras e
jornada ampliada.

- **Fonte da tabela**: PDFs do módulo "Folha de Pagamento" do portal da Prefeitura, lidos por
  `scripts/tabelas_salariais.py` (usa `pdftotext -bbox-layout`; parsear o texto alinhado dá errado).
  Saída em `data/tabelas_salariais.json`; o cruzamento com a folha é feito por `tabela_vs_folha()`.
- **Fonte da folha**: a mesma da comparação com Campinas — mediana da folha mensal de dezembro/2025.
- **Filtros**: só cargos pagos por mês e com 25 servidores ou mais. Quem é pago por hora-aula
  (professores, médicos plantonistas) ficaria distorcido sem a jornada de cada pessoa, que a folha
  não informa. Cargos em comissão e funções de confiança também ficam de fora.
- **Duas leis ao mesmo tempo**: LC 66/2017 e LC 133/2025 coexistem com valores diferentes para o
  mesmo cargo (Motorista, por exemplo, aparece como REM2 em uma e REM10 na outra). O casamento
  respeita a lei que consta no nome do cargo na folha.

Conferências feitas nesta revisão, sobre as 23 linhas publicadas:

- as medianas batem exatamente com a folha bruta de dezembro/2025 (conferido cargo a cargo);
- todas usam tabelas da **mesma referência (05/2026)** — não há mistura de tabelas de épocas
  diferentes, que inflaria a razão;
- o casamento de nomes é exato em 22 delas; a única aproximação é "Tecnico de Radiologia" ↔
  "TECNICO EM RADIOLOGIA". Nenhuma linha está marcada para revisar.

**Sobre a progressão de carreira:** o denominador é a referência (REM) que a tabela dá para o cargo,
e no quadro geral cada cargo aparece com uma referência só. A pergunta era se parte da distância
entre a folha e a tabela seria progressão de carreira, e não adicional. **Sim, é** — e dá para medir
sem a lei, comparando o salário por tempo de casa dentro do mesmo cargo e da mesma jornada designada.

Isto agora é **calculado pelo `scripts/quadro_pessoal.py`** e vai para o painel (aba Salários,
seção "E o tempo de casa"). Admissão da folha de dez/2025, jornada do Quadro de Pessoal de set/2025,
mínimo de 8 servidores em cada faixa:

| Cargo · jornada | menos de 10 anos (n) | mais de 20 anos (n) | Diferença |
|---|---|---|---|
| Tecnico de Enfermagem · trabalha as horas normais do cargo | R$ 9.124 (69) | R$ 14.242 (30) | +56% |
| Auxiliar Odontologico · trabalha as horas normais do cargo | R$ 7.894 (11) | R$ 12.031 (15) | +52% |
| Cirurgiao Dentista Plantonista · trabalha em turno ou escala | R$ 32.702 (18) | R$ 47.763 (8) | +46% |
| Professor de Educacao Basica II - PEBII · foi contratado para mais horas | R$ 19.426 (126) | R$ 26.793 (67) | +38% |
| Auxiliar de Enfermagem · trabalha as horas normais do cargo | R$ 9.845 (42) | R$ 12.781 (93) | +30% |
| Enfermeiro · trabalha as horas normais do cargo | R$ 12.920 (48) | R$ 16.488 (29) | +28% |
| Guarda Civil Municipal · trabalha em turno ou escala | R$ 18.401 (37) | R$ 22.367 (91) | +22% |
| Agente de Apoio Operacional · trabalha as horas normais do cargo | R$ 8.105 (22) | R$ 9.442 (464) | +16% |
| Motorista · trabalha em turno ou escala | R$ 14.085 (14) | R$ 16.385 (12) | +16% |
| Professor de Educacao Basica I - PEBI · foi contratado para mais horas | R$ 14.710 (93) | R$ 16.906 (129) | +15% |
| Medico Plantonista · foi contratado para mais horas | R$ 30.062 (43) | R$ 32.135 (56) | +7% |
| Professor de Educacao Basica I - PEBI · trabalha em turno ou escala | R$ 13.705 (78) | R$ 14.321 (106) | +4% |

Mediana das 12 comparações: **+25%**. O tempo de casa pesa, e pesa muito
mais em uns cargos que em outros. Sem controlar pela jornada a diferença aparece maior, porque quem tem
mais tempo também tende a estar em escala ou com função designada — por isso o controle importa.

**Uma versão anterior desta tabela foi feita à mão e não reproduz.** Ela trazia, por exemplo,
"Educadora Infantil · base +9%" — impossível, porque a Prefeitura não admite ninguém nesse cargo desde
2007 e não existe faixa de "menos de 10 anos" para comparar. Os números acima saem do script e são
refeitos a cada rodada; se divergirem de algum texto antigo, os do script é que valem.

Isso foi depois incorporado ao pipeline: o `quadro_pessoal.py` grava o bloco `tempo_de_casa` no
`data/decomposicao_folha.json` (grupos com menos de 8 pessoas numa das faixas ficam fora, o que
derruba as combinações fracas da tabela acima), o painel mostra na seção "E o tempo de casa" da aba
Salários, e a frase do resumo lê a mediana do JSON — hoje **+18% (9 comparações, +2% a +40%)**.
A tabela acima fica como registro da primeira medição, feita à mão com casamento só por matrícula.

## 6. Limites que continuam de pé

- **A folha não informa a jornada** de nenhum dos dois lados (fora os professores, pelo edital).
  Dois enfermeiros com o mesmo cargo podem ter contratos diferentes.
- **Cargo único × carreira em classes**: Paulínia tem cargos únicos onde Campinas tem níveis;
  a mediana de um lado mistura o que do outro está separado.
- **Um mês só**: dezembro. Se uma das cidades pagar algo atípico em dezembro que não caia nas
  cinco parcelas descontadas, o número daquele ano fica torto — foi exatamente o que aconteceu
  com o "Eventual" de 2023.
- **A comparação segue o seletor de ano** (2023–2025). As seções "De onde vem o salário" e "Por que
  dois colegas ganham diferente" não têm série: são de dezembro de 2025 e ficam ocultas nos outros
  anos, para não misturar épocas.
- **Dezembro é atípico na educação**: os professores temporários (CTD) somem da folha em alguns
  dezembros (198 em nov/2024, 4 em dez/2024), quando encerra o ano letivo. Não entra na conta,
  porque o CTD é excluído dos pares, mas explica saltos de efetivo.

## 7. Como refazer

```bash
python scripts/importar_servidores.py --cidade campinas --ano 2025 --mes 12 data/raw/entrada/campinas_2025_12.csv
python scripts/tabelas_salariais.py --baixar   # só quando a Prefeitura publicar tabela nova
python scripts/tabelas_salariais.py
python scripts/comparar_cargos.py
python scripts/montar_painel.py && python scripts/publicar.py
```

`python scripts/comparar_cargos.py --listar` mostra os cargos com 50+ servidores que ainda não
têm par — é por onde começar para ampliar a comparação.
