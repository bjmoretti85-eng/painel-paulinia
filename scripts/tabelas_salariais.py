#!/usr/bin/env python3
"""Lê as tabelas salariais oficiais de Paulínia (PDFs do portal) e cruza com a folha.

O portal tem um módulo escondido, "Folha de Pagamento", que publica as tabelas de
vencimentos em PDF. Elas dizem quanto **a lei** paga em cada cargo. A folha diz quanto
a pessoa **recebe**. A razão entre as duas é o indicador: quanto do salário vem do
vencimento e quanto vem de adicionais, gratificações e jornada.

    python scripts/tabelas_salariais.py --baixar     # busca os PDFs do portal
    python scripts/tabelas_salariais.py              # lê os PDFs -> data/tabelas_salariais.json
    python scripts/tabelas_salariais.py --conferir   # mostra o que casou e o que não casou

Precisa do pdftotext (poppler-utils). Fora isso, só biblioteca padrão.
"""
import argparse
import csv
import difflib
import gzip
import json
import re
import statistics
import subprocess
import unicodedata
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PDFS = RAIZ / "data/raw/tabelas"
SAIDA = RAIZ / "data/tabelas_salariais.json"

HOST = "https://transparencia-paulinia.smarapd.com.br"
API = HOST + "/paiportalserver"
# atenção: os arquivos NÃO ficam no paiportalserver, e sim no paifileserver
ARQUIVOS = HOST + "/paifileserver/filemanager/pai/download?nomeArquivo="
HEADERS = {"User-Agent": "Mozilla/5.0 (painel-paulinia; dados publicos)",
           "Accept": "*/*", "Referer": HOST + "/"}

REF = re.compile(r"\b(RE[MH]\d+|RM[HM]\d+)\b\s*(?:R\$\s*)?([\d.]+,\d{2})(\s*/\s*h(?:ora-aula)?)?")
CONECTIVO = re.compile(r"(,|\b(?:de|do|da|dos|das|e|em|com|para)\.?)$", re.I)
COL = 58  # onde começa a coluna da direita no texto com -layout


def api(caminho):
    with urllib.request.urlopen(urllib.request.Request(API + caminho, headers=HEADERS), timeout=40) as r:
        return json.load(r)


def baixar():
    PDFS.mkdir(parents=True, exist_ok=True)
    itens, alvos = api("/modulovisao/fixo/ServidoresConsolidado/folhadepagamento")["VisaoItens"], []

    def anda(lista):
        for it in lista:
            if it.get("ExibeDetalhes"):
                alvos.append((it["key"], it["title"]))
            if it.get("children"):
                anda(it["children"])

    anda(itens)
    for chave, titulo in alvos:
        try:
            d = api(f"/ModuloVisaoItemDetalhe/ServidoresConsolidado/folhadepagamento/{int(chave)}")
            url, nome = d.get("UrlArquivo"), (d.get("NomeArquivo") or f"{chave}.pdf").replace("/", "-")
            if not url:
                continue
            destino = PDFS / nome
            if not destino.exists():
                with urllib.request.urlopen(urllib.request.Request(ARQUIVOS + url + "&isInlineContent=true",
                                                                   headers=HEADERS), timeout=120) as r:
                    destino.write_bytes(r.read())
            print(f"   {destino.stat().st_size:>9,} B  {nome}".replace(",", "."))
        except Exception as e:
            print(f"   [falhou] {titulo.strip()}: {e}")


def texto(pdf):
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout


def num(s):
    return float(s.replace(".", "").replace(",", "."))


def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"\s*[-–]\s*(?:LC|LEI)\s*N?[º°]?\s*[\d./-]+", "", s)   # tira "- LC 66/2017"
    s = re.sub(r"\((?:CTD|PEB\s*I+)\)", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def palavras(pdf):
    """Palavras com coordenadas (pdftotext -bbox-layout). Adivinhar a estrutura da
    tabela pelo texto alinhado dá errado: o nome do cargo quebra em várias linhas e a
    referência aparece no meio do bloco. Com as coordenadas isso deixa de ser chute."""
    xml = subprocess.run(["pdftotext", "-bbox-layout", str(pdf), "-"],
                         capture_output=True, text=True, check=True).stdout
    saida, pagina = [], 0
    for linha in xml.splitlines():
        if "<page " in linha:
            pagina += 1
        m = re.search(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*)</word>', linha)
        if m:
            x0, y0, x1, y1, txt = m.groups()
            txt = (txt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                      .replace("&quot;", '"').replace("&#39;", "'"))
            saida.append({"pag": pagina, "x0": float(x0), "y0": float(y0),
                          "x1": float(x1), "y1": float(y1),
                          "yc": (float(y0) + float(y1)) / 2, "txt": txt})
    return saida


ANCORA = re.compile(r"^(RE[MH]\d+|RM[HM]\d+)$")
VALOR = re.compile(r"^R?\$?\s*([\d.]+,\d{2})")
LIXO = re.compile(r"^(R\$|\*+|REFER[EÊ]NCIA|ANEXO|VENCIMENTO-?INICIAL)$", re.I)


def parse_referencias(pdf, tabela):
    ws = palavras(pdf)
    saida = []
    for pag in sorted({w["pag"] for w in ws}):
        pw = [w for w in ws if w["pag"] == pag]
        ancoras = [w for w in pw if ANCORA.match(w["txt"])]
        if not ancoras:
            continue
        ancoras.sort(key=lambda w: w["yc"])
        # valor: primeira palavra à direita da âncora, na mesma altura
        for a in ancoras:
            a["valor"], a["unidade"] = None, "mes"
            cand = sorted([w for w in pw if w["x0"] > a["x1"] and abs(w["yc"] - a["yc"]) < 6],
                          key=lambda w: w["x0"])
            for i, w in enumerate(cand):
                m = VALOR.match(w["txt"])
                if m:
                    a["valor"] = float(m.group(1).replace(".", "").replace(",", "."))
                    resto = w["txt"][m.end():] + ("".join(c["txt"] for c in cand[i + 1:i + 2]))
                    if "aula" in resto.lower():
                        a["unidade"] = "hora-aula"
                    elif re.search(r"/\s*h", resto, re.I):
                        a["unidade"] = "hora"
                    break
        ancoras = [a for a in ancoras if a["valor"]]
        if not ancoras:
            continue
        # coluna do cargo = tudo à esquerda da coluna das âncoras
        x_ref = min(a["x0"] for a in ancoras)
        corte = ancoras[0]["yc"] - 14        # acima da 1ª âncora é cabeçalho
        esq = [w for w in pw if w["x1"] < x_ref - 2 and w["yc"] > corte and not LIXO.match(w["txt"])]
        grupos = {a["txt"]: [] for a in ancoras}
        for w in esq:                        # cada palavra vai para a âncora mais próxima na vertical
            perto = min(ancoras, key=lambda a: abs(a["yc"] - w["yc"]))
            grupos[perto["txt"]].append(w)
        for a in ancoras:
            ws_g = sorted(grupos[a["txt"]], key=lambda w: (round(w["yc"], 1), w["x0"]))
            if not ws_g:
                continue
            linhas, atual, y = [], [], None
            for w in ws_g:                   # remonta as linhas
                if y is None or abs(w["yc"] - y) < 4:
                    atual.append(w["txt"])
                else:
                    linhas.append(" ".join(atual)); atual = [w["txt"]]
                y = w["yc"]
            if atual:
                linhas.append(" ".join(atual))
            # junta linha que termina em conectivo/travessão com a seguinte
            juntas = []
            for ln in linhas:
                ln = ln.strip()
                anterior = juntas[-1] if juntas else ""
                continua = anterior and (CONECTIVO.search(anterior) or anterior.endswith(("-", "–")))
                if continua:
                    juntas[-1] = (anterior.rstrip("–- ") + " " + ln).strip()
                else:
                    juntas.append(ln)
            texto_todo = " ".join(juntas)
            cargos = ([c.strip() for c in texto_todo.split(",")] if "," in texto_todo
                      else [c.strip() for c in juntas])
            for c in cargos:
                if len(c) > 3:
                    saida.append({"cargo": c, "referencia": a["txt"], "vencimento": a["valor"],
                                  "unidade": a["unidade"], "tabela": tabela, "revisar": False})
    return saida


def parse_guarda(txt, tabela):
    """Matriz classe x letra da carreira, mais os cargos de chefia que vêm no mesmo PDF.

    O piso e o teto têm que sair só das linhas de CLASSE: Comandante e Corregedor são
    cargos à parte e, se entrassem no 'topo', inflariam a régua da carreira.
    """
    carreira, saida = [], []
    for linha in txt.splitlines():
        valores = [num(v) for v in re.findall(r"R\$\s*([\d.]+,\d{2})", linha)]
        if not valores:
            continue
        if re.search(r"\bCLASSE\b", linha, re.I):
            carreira += valores
        else:
            m = re.match(r"\s*([A-Za-zÀ-ÿ ]{6,60}?)\s+R\$", linha)
            if m:
                saida.append({"cargo": m.group(1).strip(), "referencia": "LC 139/2026",
                              "vencimento": valores[0], "unidade": "mes",
                              "tabela": tabela, "revisar": False})
    if carreira:
        saida.append({"cargo": "Guarda Civil Municipal", "referencia": "LC 139/2026 (carreira)",
                      "vencimento": min(carreira), "vencimento_topo": max(carreira),
                      "unidade": "mes", "tabela": tabela, "revisar": False})
    return saida


def carregar_tabelas():
    if not PDFS.exists():
        raise SystemExit("Não achei data/raw/tabelas. Rode com --baixar primeiro.")
    registros = []
    for pdf in sorted(PDFS.glob("*.pdf")):
        nome = pdf.name.upper()
        if "QUADRO DE PESSOAL" in nome or "ESTAGI" in nome:
            continue          # esses são listagens de lotação, não tabelas de vencimento
        if "GUARDA CIVIL" in nome:
            registros += parse_guarda(texto(pdf), pdf.stem)
        elif "CHEFIA" in nome or "CONFIAN" in nome or "AGENTE POL" in nome:
            continue          # layout de matriz/duas colunas; não parseado (ver README)
        else:
            registros += parse_referencias(pdf, pdf.stem)
    return registros


def folha_por_cargo(ano=2025):
    arq = RAIZ / f"data/raw/servidores_{ano}.csv.gz"
    por_cargo = {}
    with gzip.open(arq, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["mes"] != "12" or r["tipo_folha"] != "9":
                continue
            if "Inativo" in r["cargo"] or "Pensionista" in r["cargo"]:
                continue
            v = float(r["vencimentos"] or 0)
            if v > 0:
                por_cargo.setdefault(r["cargo"], []).append(v)
    return por_cargo


LEI = re.compile(r"\bLC\s*n?[ºo°]?\s*(\d+)[/-](\d{4})", re.I)

# Cargos temporários e outros nomes que não aparecem nas tabelas, mapeados à mão.
# Isto é julgamento: revise antes de publicar.
ALIASES = {
    # temporários (CTD) e nomes abreviados na folha -> cargo equivalente na tabela + lei
    "PROFESSOR DE E BASICA I": ("PROFESSOR DE EDUCACAO BASICA I PEB I LICENCIATURA SUPERIOR", "65"),
    "PROFESSOR DE E B II": ("PROFESSOR DE EDUCACAO BASICA II PEB II", "65"),
    "PROFESSOR DE E BASICA II": ("PROFESSOR DE EDUCACAO BASICA II PEB II", "65"),
    "PROFESSOR DE EDUCACAO BASICA I PEBI": ("PROFESSOR DE EDUCACAO BASICA I PEB I LICENCIATURA SUPERIOR", "65"),
    "PROFESSOR DE EDUCACAO BASICA II PEBII": ("PROFESSOR DE EDUCACAO BASICA II PEB II", "65"),
    "TECNICO DE ENFERMAGEM": ("TECNICO DE ENFERMAGEM", "66"),
    "ENFERMEIRO": ("ENFERMEIRO", "66"),
    "FISIOTERAPEUTA": ("FISIOTERAPEUTA ANALISTA DE SISTEMAS", "66"),   # bloco mal separado no PDF
    "AUXILIAR DE ENFERMAGEM": ("AUXILIAR DE ENFERMAGEM DO TRABALHO", "66"),  # mesma referência REM16
}


def lei_do_cargo(cargo):
    m = LEI.search(cargo)
    return m.group(1) if m else None


def lei_da_tabela(tabela):
    m = re.search(r"LC\s*(\d+)", tabela, re.I)
    return m.group(1) if m else None


def casar(cargos_folha, registros):
    # um índice por lei: LC 66/2017 e LC 133/2025 coexistem com valores bem diferentes
    # para o mesmo cargo, então casar pelo nome sem olhar a lei dá número errado.
    indices = {}
    for reg in registros:
        indices.setdefault(lei_da_tabela(reg["tabela"]), {}).setdefault(norm(reg["cargo"]), reg)
    todos = {}
    for lei, idx in indices.items():
        for k, reg in idx.items():
            todos.setdefault(k, reg)

    casados, sem_par = {}, []
    for cargo, valores in cargos_folha.items():
        k, lei = norm(cargo), lei_do_cargo(cargo)
        apelido = ALIASES.get(k)
        if apelido:
            k, lei = apelido
        idx = indices.get(lei) if lei else todos
        reg = idx.get(k)
        modo = "exato" if lei else "exato (sem lei no nome)"
        if apelido:
            modo += " via alias"
        if not reg:
            perto = difflib.get_close_matches(k, list(idx), n=1, cutoff=0.86)
            if perto:
                reg, modo = idx[perto[0]], f"aproximado ({perto[0]})"
        if reg:
            casados[cargo] = {"n": len(valores), "mediana": round(statistics.median(valores), 2),
                              "tabela": reg["tabela"], "referencia": reg["referencia"],
                              "vencimento": reg["vencimento"],
                              "vencimento_topo": reg.get("vencimento_topo"),
                              "unidade": reg["unidade"], "match": modo,
                              "revisar": reg.get("revisar", False)}
        else:
            sem_par.append((len(valores), cargo))
    return casados, sorted(sem_par, reverse=True)


def brl(v):
    return ("R$ " + f"{v:,.0f}").replace(",", ".")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baixar", action="store_true", help="baixa os PDFs do portal")
    ap.add_argument("--conferir", action="store_true", help="relatório de cobertura")
    a = ap.parse_args()
    if a.baixar:
        return baixar()

    registros = carregar_tabelas()
    folha = folha_por_cargo()
    casados, sem_par = casar(folha, registros)

    total = sum(len(v) for v in folha.values())
    cobertos = sum(c["n"] for c in casados.values())
    print(f"tabelas lidas: {len(registros)} cargos")
    print(f"folha dez/2025: {total} servidores em {len(folha)} cargos")
    print(f"casados: {cobertos} servidores ({100*cobertos/total:.0f}%) em {len(casados)} cargos\n")

    if a.conferir:
        print("SEM PAR na tabela (20+ servidores):")
        for n, cargo in sem_par:
            if n >= 20:
                print(f"   {n:5d}  {cargo}")
        print("\nCASADOS POR APROXIMAÇÃO ou que precisam de revisão:")
        for cargo, c in sorted(casados.items(), key=lambda x: -x[1]["n"]):
            if c["match"] != "exato" or c["revisar"]:
                print(f"   {c['n']:5d}  {cargo}  ->  {c['referencia']} {brl(c['vencimento'])}"
                      f"  [{c['match']}{', revisar' if c['revisar'] else ''}]")
        return

    print(f"{'cargo':44s} {'tabela':>10s} {'mediana':>10s} {'acima':>7s}")
    print("-" * 76)
    for cargo, c in sorted(casados.items(), key=lambda x: -x[1]["n"])[:25]:
        if c["unidade"] != "mes":
            print(f"{cargo[:44]:44s} {c['vencimento']:9,.2f}/{c['unidade'][:4]} {brl(c['mediana']):>10s}"
                  f"       —  (pago por hora)".replace(",", "."))
            continue
        base = c["vencimento_topo"] or c["vencimento"]
        rot = " (topo)" if c["vencimento_topo"] else ""
        print(f"{cargo[:44]:44s} {brl(base):>10s} {brl(c['mediana']):>10s} {c['mediana']/base:6.2f}x{rot}")

    SAIDA.write_text(json.dumps({"tabelas": registros, "cruzamento": casados},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
