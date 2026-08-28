# Painel das Contas de Paulínia

Painel que traduz as despesas e receitas da Prefeitura de Paulínia (SP) para o cidadão comum,
a partir dos dados públicos do TCE-SP.

**Para ver o painel:** abra `painel/index.html` no navegador. Não precisa de servidor.
Mantenha a pasta `data/` ao lado de `painel/`: a seção "Explore gasto a gasto" carrega `data/detalhe_{ano}.js` sob demanda.

## Atualizar os dados

```bash
python scripts/baixar_dados.py      # baixa do TCE-SP e filtra Paulínia (demora: ~2 GB por ano em streaming)
python scripts/baixar_servidores.py # baixa a folha por servidor do portal da prefeitura (retomável)
python scripts/processar.py         # gera data/painel.json e data/detalhe_{ano}.js
python scripts/montar_painel.py     # embute o JSON no template -> painel/index.html
```

Para acrescentar um ano novo (ex.: 2026, quando o TCE publicar `despesas-2026.zip`):
`python scripts/baixar_dados.py 2026`, adicione a população em `POPULACAO` no `processar.py`
e rode os dois scripts seguintes.

## Estrutura

```
CLAUDE.md                 contexto para o Claude Code
docs/planejamento.md      planejamento, decisões e próximos passos
scripts/baixar_dados.py   download em streaming + filtro de Paulínia (TCE-SP)
scripts/baixar_servidores.py  folha por servidor x mês (portal SMARAPD da prefeitura) -> data/raw/servidores_{ano}.csv.gz
scripts/processar.py      agregação -> data/painel.json + data/detalhe_{ano}.js (rótulos amigáveis ficam aqui)
scripts/montar_painel.py  template + JSON -> painel/index.html
scripts/publicar.py       painel/index.html + data/*.js -> dist/ (site publicado)
painel/template.html      o painel (HTML/CSS/JS puros, sem dependências)
painel/index.html         versão pronta, com dados embutidos
data/raw/                 CSVs de Paulínia (gzip), 2023-2025: despesas, receitas e servidores
                          (as pastas data/raw/servidores_{ano}/ são cache de download e podem ser apagadas)
data/painel.json          agregados (embutidos no index.html)
data/detalhe_{ano}.js     funil completo (área > serviço > tipo de gasto > fornecedor > empenhos), carregado sob demanda
dist/                     o que vai para o ar: index.html na raiz + data/*.js ao lado
```

Só usa a biblioteca padrão do Python 3.

## Publicar (Cloudflare Pages)

O site é 100% estático, sem build. A pasta `dist/` é gerada por `scripts/publicar.py`
e vai versionada no repositório — o Cloudflare só precisa servi-la.

Configuração no painel do Cloudflare (Workers & Pages › Create › Pages › Connect to Git):

| Campo | Valor |
|---|---|
| Framework preset | None |
| Build command | *(vazio)* |
| Build output directory | `dist` |

A cada `git push` na branch `main` o site é republicado sozinho.

Para atualizar os dados do painel no ar:

```bash
python scripts/baixar_dados.py
python scripts/baixar_servidores.py
python scripts/processar.py
python scripts/montar_painel.py
python scripts/publicar.py
git add -A && git commit -m "dados: atualiza para <mês>" && git push
```

`painel/index.html` continua abrindo offline como antes; `dist/index.html` é a mesma
página com os caminhos dos dados ajustados para a raiz do site.

## Privacidade

O CSV bruto da folha (`data/raw/servidores_*.csv.gz`) tem nome, matrícula e salário
individual e por isso **não é versionado** (ver `.gitignore`). O painel publica apenas
agregados anônimos por secretaria, vínculo e cargo. Quem clonar o repositório refaz o
arquivo com `python scripts/baixar_servidores.py`.
