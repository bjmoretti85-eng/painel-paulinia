#!/usr/bin/env python3
"""
Embute data/painel.json no template e gera painel/index.html (arquivo único,
abre direto no navegador, sem servidor).

Uso:
    python scripts/montar_painel.py
"""
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TEMPLATE = BASE / "painel" / "template.html"
DADOS = BASE / "data" / "painel.json"
SAIDA = BASE / "painel" / "index.html"

html = TEMPLATE.read_text(encoding="utf-8")
dados = DADOS.read_text(encoding="utf-8").replace("</script", "<\\/script")
assert "/*__DADOS__*/null" in html, "placeholder não encontrado no template"
html = html.replace("/*__DADOS__*/null", dados)

# comparativo com outras cidades (opcional: se o arquivo não existir, a seção some)
COMP = BASE / "data" / "comparativo_cargos.json"
comp = COMP.read_text(encoding="utf-8").replace("</script", "<\\/script") if COMP.exists() else "null"
assert "/*__COMPARATIVO__*/null" in html, "placeholder do comparativo não encontrado"
html = html.replace("/*__COMPARATIVO__*/null", comp)
print("comparativo:", "embutido" if COMP.exists() else "ausente (seção oculta)")

SAIDA.write_text(html, encoding="utf-8")
print(f"-> {SAIDA} ({SAIDA.stat().st_size/1024:.0f} KB)")
