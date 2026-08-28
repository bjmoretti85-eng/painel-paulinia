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

# Cache curto no HTML (para o painel atualizar logo depois de um deploy) e
# mais longo nos dados, que só mudam quando o processamento roda de novo.
HEADERS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin

/index.html
  Cache-Control: public, max-age=300

/data/*
  Cache-Control: public, max-age=3600
"""

if not INDEX.exists():
    raise SystemExit("painel/index.html não existe — rode scripts/montar_painel.py antes.")

if DIST.exists():
    shutil.rmtree(DIST)
(DIST / "data").mkdir(parents=True)

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

total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
print(f"-> {DIST} ({copiados + 2} arquivos, {total/1024/1024:.1f} MB)")
