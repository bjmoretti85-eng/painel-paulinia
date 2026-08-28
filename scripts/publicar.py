#!/usr/bin/env python3
"""
Monta a pasta dist/ para publicação estática (Cloudflare Pages).

O painel/index.html usa caminhos '../data/...' porque mora dentro de painel/.
No site publicado o index fica na raiz, então aqui trocamos por 'data/...'
e copiamos ao lado só os arquivos que o navegador realmente carrega.

Uso:
    python scripts/publicar.py
"""
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
INDEX = BASE / "painel" / "index.html"
DATA = BASE / "data"
DIST = BASE / "dist"

# O Cloudflare já serve o HTML com must-revalidate (o painel atualiza no deploy
# seguinte); aqui só damos cache aos dados, que mudam quando o processamento roda.
HEADERS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin

/data/*
  Cache-Control: public, max-age=3600
"""

if not INDEX.exists():
    raise SystemExit("painel/index.html não existe — rode scripts/montar_painel.py antes.")

# Apaga os arquivos antigos sem remover as pastas: no Windows o OneDrive costuma
# manter o diretório aberto e um rmtree falha com "Acesso negado".
(DIST / "data").mkdir(parents=True, exist_ok=True)
for antigo in DIST.rglob("*"):
    if antigo.is_file():
        antigo.unlink()

html = INDEX.read_text(encoding="utf-8")
assert "'../data/" in html, "caminhos '../data/ não encontrados no index.html"
(DIST / "index.html").write_text(html.replace("'../data/", "'data/"), encoding="utf-8")
(DIST / "_headers").write_text(HEADERS, encoding="utf-8")

# Só os .js carregados sob demanda pelo painel; painel.json já vai embutido no HTML
# e os CSVs de data/raw/ não são usados pelo navegador.
copiados = 0
for arquivo in sorted(DATA.glob("*.js")):
    shutil.copy2(arquivo, DIST / "data" / arquivo.name)
    copiados += 1

# O CLAUDE.md ja voltou 3x de edicoes externas sem as linhas de publicacao e sigilo.
# Como este script roda antes de todo deploy, ele e um bom lugar para avisar.
ESSENCIAIS = ["scripts/publicar.py", "servidores_*.csv.gz", "workers.dev"]
contexto = (BASE / "CLAUDE.md").read_text(encoding="utf-8")
sumiram = [e for e in ESSENCIAIS if e not in contexto]
if sumiram:
    print(f"AVISO: CLAUDE.md esta sem: {', '.join(sumiram)} — restaure antes de commitar.")

total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
print(f"-> {DIST} ({copiados + 2} arquivos, {total/1024/1024:.1f} MB)")
