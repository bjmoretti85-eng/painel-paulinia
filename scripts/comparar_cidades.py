#!/usr/bin/env python3
"""Compara Paulínia com as cidades da região: servidores por mil habitantes e
arrecadação por habitante.

Duas fontes, ambas cobrindo todos os municípios com a MESMA definição — que é o que
torna a comparação honesta:

  * IBGE MUNIC 2024 (Base_MUNIC_2024.xlsx): pessoal ocupado na administração direta
    e indireta, e a população de cada município.
  * TCE-SP, conjunto de receitas do ano: arrecadação, excluindo as intra-orçamentárias
    (categoria 7), exatamente como o processar.py faz para Paulínia.

Por que não comparar efetivo com Campinas e pronto: a razão servidores/habitante cai
muito com o tamanho da cidade (mediana paulista: 67 por mil até 10 mil habitantes, 14
por mil acima de 500 mil). Comparar Paulínia com Campinas mede sobretudo a diferença
de porte. Por isso aqui entram cidades da região e a mediana da faixa de população.

    python scripts/comparar_cidades.py --baixar    # MUNIC + receitas do TCE
    python scripts/comparar_cidades.py             # -> data/comparativo_cidades.json
"""
import argparse
import csv
import gzip
import json
import re
import statistics
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MUNIC = RAIZ / "data/raw/ibge/Base_MUNIC_2024.xlsx"
MUNIC_URL = ("https://ftp.ibge.gov.br/Perfil_Municipios/2024/Base_de_Dados/"
             "Base_MUNIC_2024_20251107.xlsx")
SAIDA = RAIZ / "data/comparativo_cidades.json"
TOTAIS_SP = RAIZ / "data/raw/receitas_sp_totais_2025.csv"
DESPESAS_SP = RAIZ / "data/raw/despesas_sp_totais_2025.csv"
ANO = 2025

# A região de Paulínia. "Santa Bárbara d'Oeste" aparece com grafias diferentes nas
# duas fontes; a comparação é feita por nome normalizado, então tanto faz.
CIDADES = ["Paulínia", "Campinas", "Sumaré", "Americana", "Hortolândia", "Nova Odessa",
           "Cosmópolis", "Santa Barbara D'Oeste", "Santa Bárbara d'Oeste", "Valinhos",
           "Vinhedo", "Indaiatuba", "Jaguariúna", "Monte Mor", "Artur Nogueira", "Pedreira"]
FAIXA = (50_000, 200_000)      # porte de Paulínia, para a mediana de referência

# a MUNIC grava alguns nomes sem o apóstrofo; só a exibição precisa de conserto
GRAFIA = {"SANTABARBARADOESTE": "Santa Bárbara d'Oeste"}


def norm(s):
    """Nome de município comparável entre as fontes.

    O TCE grafa "Santa Bárbara d Oeste" (com espaço), a MUNIC "Santa Bárbara D'Oeste"
    (com apóstrofo). Tirando acentos, pontuação e TODOS os espaços, as duas viram
    SANTABARBARADOESTE e a junção funciona."""
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z]", "", s)


def val(s):
    try:
        return float((s or "0").strip().replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(".", "").replace(",", "."))
    except (ValueError, TypeError):
        return None


def baixar(refazer=False):
    import sys
    MUNIC.parent.mkdir(parents=True, exist_ok=True)
    if not MUNIC.exists():
        print(f"Baixando {MUNIC_URL}")
        req = urllib.request.Request(MUNIC_URL, headers={"User-Agent": "painel-paulinia/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(MUNIC, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
    print(f"  {MUNIC.stat().st_size / 1e6:.1f} MB  {MUNIC.name}")

    destino = RAIZ / f"data/raw/receitas_rmc_{ANO}.csv.gz"
    if destino.exists() and not refazer:
        print(f"  já existe  {destino.name}  (use --refazer para baixar de novo)")
        return
    sys.path.insert(0, str(RAIZ / "scripts"))
    import baixar_dados as bd
    alvo = {norm(c) for c in CIDADES}
    print(f"Baixando receitas-{ANO}.zip do TCE")
    n = m = 0
    cab = None
    totais = defaultdict(float)   # todos os municípios de SP, para a mediana da faixa
    with bd.abrir(f"{bd.BASE}receitas-{ANO}.zip") as resp, gzip.open(destino, "wb") as out:
        for i, linha in enumerate(bd.linhas_do_zip_em_streaming(resp)):
            if i == 0:
                out.write(linha + b"\n")
                cab = [c.strip() for c in linha.decode("latin-1").split(";")]
                icat, ival = cab.index("ds_categoria"), cab.index("vl_arrecadacao")
                continue
            n += 1
            campos = linha.split(b";")
            if len(campos) <= max(2, icat, ival):
                continue
            nome = norm(campos[2].decode("latin-1"))
            if nome in alvo:
                out.write(linha + b"\n")
                m += 1
            cod = re.match(r"\s*(\d+)", campos[icat].decode("latin-1"))
            if cod and cod.group(1).startswith("7"):
                continue          # intra-orçamentária, igual ao processar.py
            totais[nome] += val(campos[ival].decode("latin-1"))
    print(f"  {n:,} linhas lidas, {m:,} guardadas -> {destino.name}".replace(",", "."))
    with open(TOTAIS_SP, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["municipio_norm", "arrecadacao"])
        for k, v in sorted(totais.items()):
            w.writerow([k, f"{v:.2f}"])
    print(f"  {len(totais)} municípios de SP -> {TOTAIS_SP.name}")



# Elementos 31xx que NÃO são folha de servidor ativo — mesma régua do processar.py
NAO_ATIVOS = ("319001", "319003", "319091", "319094", "3171")


def baixar_despesas():
    """Streama o despesas-{ano}.zip inteiro (~2 GB) e guarda, por município,
    só três totais: valor pago, gasto com pessoal (elemento 31xx) e a parte do
    pessoal que é de servidor ativo (fora aposentadoria, precatório e consórcio).

    É o mesmo critério que o processar.py usa para Paulínia, aplicado aos 645
    municípios — é isso que torna o percentual comparável entre cidades."""
    import sys, time
    sys.path.insert(0, str(RAIZ / "scripts"))
    import baixar_dados as bd
    pago = defaultdict(float)
    pessoal = defaultdict(float)
    ativos = defaultdict(float)
    t0, n = time.time(), 0
    print(f"Baixando despesas-{ANO}.zip do TCE (~2 GB, alguns minutos)")
    with bd.abrir(f"{bd.BASE}despesas-{ANO}.zip") as resp:
        it = bd.linhas_do_zip_em_streaming(resp)
        cab = [c.strip() for c in next(it).decode("latin-1").split(";")]
        imun, itp = cab.index("ds_municipio"), cab.index("tp_despesa")
        ivl, iel = cab.index("vl_despesa"), cab.index("ds_elemento")
        largura = max(imun, itp, ivl, iel) + 1
        for linha in it:
            n += 1
            if n % 2_000_000 == 0:
                print(f"  {n:,} linhas em {time.time()-t0:.0f}s".replace(",", "."), flush=True)
            campos = linha.split(b";")
            if len(campos) < largura or campos[itp] != b"Valor Pago":
                continue
            mun = norm(campos[imun].decode("latin-1"))
            v = val(campos[ivl].decode("latin-1"))
            pago[mun] += v
            elem = campos[iel].decode("latin-1").lstrip()
            if elem[:2] == "31":
                pessoal[mun] += v
                cod = re.match(r"(\d+)", elem)
                if not (cod and cod.group(1).startswith(NAO_ATIVOS)):
                    ativos[mun] += v
    with open(DESPESAS_SP, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["municipio_norm", "pago", "pessoal", "pessoal_ativos"])
        for k in sorted(pago):
            w.writerow([k, f"{pago[k]:.2f}", f"{pessoal[k]:.2f}", f"{ativos[k]:.2f}"])
    print(f"  {n:,} linhas lidas em {time.time()-t0:.0f}s, {len(pago)} municípios "
          f"-> {DESPESAS_SP.name}".replace(",", "."))


def ler_munic():
    """Todos os municípios de SP: população, administração direta e indireta."""
    import openpyxl
    wb = openpyxl.load_workbook(MUNIC, read_only=True, data_only=True)
    ws = wb["Recursos humanos"]
    it = ws.iter_rows(values_only=True)
    next(it)
    saida = {}
    for r in it:
        if r[1] != "SP":
            continue
        pop, direta, indireta = num(r[4]), num(r[12]), num(r[19]) or 0
        estagiarios = num(r[10]) or 0        # MREH0114: recebem bolsa, não entram na folha 31xx
        if pop and direta is not None:
            saida[norm(r[3])] = {"cidade": r[3], "pop": pop, "direta": direta,
                                 "indireta": indireta, "estagiarios": estagiarios}
    return saida


def ler_receitas():
    caminho = RAIZ / f"data/raw/receitas_rmc_{ANO}.csv.gz"
    if not caminho.exists():
        return {}
    total = defaultdict(float)
    with gzip.open(caminho, "rt", encoding="latin-1", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            cod = re.match(r"\s*(\d+)", r["ds_categoria"] or "")
            if cod and cod.group(1).startswith("7"):
                continue          # intra-orçamentária, igual ao processar.py
            total[norm(r["ds_municipio"])] += val(r["vl_arrecadacao"])
    return dict(total)


def ler_despesas():
    """Total pago, gasto com pessoal e folha de servidor ativo, por município."""
    if not DESPESAS_SP.exists():
        return {}
    saida = {}
    with open(DESPESAS_SP, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            saida[r["municipio_norm"]] = {k: float(r[k]) for k in ("pago", "pessoal", "pessoal_ativos")}
    return saida


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baixar", action="store_true")
    ap.add_argument("--refazer", action="store_true",
                    help="rebaixa as receitas mesmo se o arquivo já existir")
    ap.add_argument("--despesas", action="store_true",
                    help="streama o despesas-{ano}.zip (~2 GB) para o total pago e a folha de cada município")
    a = ap.parse_args()
    if a.despesas:
        return baixar_despesas()
    if a.baixar or a.refazer:
        return baixar(a.refazer)
    if not MUNIC.exists():
        raise SystemExit("Falta a base da MUNIC. Rode com --baixar.")

    todos, receitas, despesas = ler_munic(), ler_receitas(), ler_despesas()

    def indicadores(chave, d):
        """% da despesa que vai para a folha e custo médio mensal por servidor.

        O custo médio NÃO é salário: é a folha de servidor ativo (fora aposentadoria,
        precatório e consórcio) dividida pelo efetivo da MUNIC, e inclui encargos
        patronais, hora extra, 13º e férias. Denominador = direta + indireta menos
        estagiários, que recebem bolsa e não entram no elemento 31xx."""
        x = despesas.get(chave)
        if not x or not x["pago"]:
            return {}
        serv = d["direta"] + d["indireta"] - d["estagiarios"]
        out = {"folha_pct": round(100 * x["pessoal"] / x["pago"], 2)}
        if serv > 0:
            out["custo_medio"] = round(x["pessoal_ativos"] / serv / 12, 2)
        return out
    alvo = {norm(c) for c in CIDADES}
    cidades = []
    for chave, d in todos.items():
        if chave not in alvo:
            continue
        linha = {"cidade": GRAFIA.get(chave, d["cidade"]), "pop": int(d["pop"]),
                 "servidores": int(d["direta"]), "indireta": int(d["indireta"]),
                 "por_mil": round(1000 * d["direta"] / d["pop"], 2)}
        if chave in receitas:
            linha["receita"] = round(receitas[chave], 2)
            linha["receita_hab"] = round(receitas[chave] / d["pop"], 2)
        linha.update(indicadores(chave, d))
        cidades.append(linha)
    cidades.sort(key=lambda x: -x.get("receita_hab", 0))

    faixa = [d for d in todos.values() if FAIXA[0] <= d["pop"] < FAIXA[1]]
    mediana_faixa = statistics.median([1000 * d["direta"] / d["pop"] for d in faixa])
    com_receita = [c for c in cidades if "receita_hab" in c]

    # mediana de arrecadação por habitante da MESMA faixa de porte, com todos os
    # municípios paulistas — não só os da região
    totais_sp = {}
    if TOTAIS_SP.exists():
        with open(TOTAIS_SP, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                totais_sp[r["municipio_norm"]] = float(r["arrecadacao"])
    faixa_rec = [totais_sp[k] / d["pop"] for k, d in todos.items()
                 if FAIXA[0] <= d["pop"] < FAIXA[1] and totais_sp.get(k)]

    ind_faixa = [indicadores(k, d) for k, d in todos.items()
                 if FAIXA[0] <= d["pop"] < FAIXA[1]]
    fp_faixa = sorted(x["folha_pct"] for x in ind_faixa if x.get("folha_pct"))
    cm_faixa = sorted(x["custo_medio"] for x in ind_faixa if x.get("custo_medio"))

    # onde Paulínia fica dentro da faixa de porte
    pm_faixa = sorted(1000 * d["direta"] / d["pop"] for d in faixa)
    pau = todos["PAULINIA"]
    pau_pm = 1000 * pau["direta"] / pau["pop"]
    abaixo = sum(1 for v in pm_faixa if v < pau_pm)
    rec_faixa = sorted(faixa_rec)
    pau_rec = totais_sp.get("PAULINIA", 0) / pau["pop"]
    abaixo_rec = sum(1 for v in rec_faixa if v < pau_rec)
    pau_ind = indicadores("PAULINIA", pau)
    def posicao(lista, v):
        return round(100 * sum(1 for x in lista if x < v) / len(lista)) if lista and v else None

    saida = {"ano": ANO,
             "fonte_pessoal": "IBGE, MUNIC 2024 (administração direta)",
             "fonte_receita": f"TCE-SP, receitas {ANO} (sem intra-orçamentárias)",
             "cidades": cidades,
             "referencia": {
                 "faixa": list(FAIXA), "municipios_na_faixa": len(faixa),
                 "mediana_por_mil": round(mediana_faixa, 2),
                 "municipios_na_faixa_com_receita": len(faixa_rec),
                 "pct_abaixo_por_mil": round(100 * abaixo / len(pm_faixa)),
                 "pct_abaixo_receita_hab": round(100 * abaixo_rec / len(rec_faixa)) if rec_faixa else None,
                 "mediana_receita_hab": round(statistics.median(faixa_rec), 2) if faixa_rec else None,
                 "mediana_folha_pct": round(statistics.median(fp_faixa), 2) if fp_faixa else None,
                 "mediana_custo_medio": round(statistics.median(cm_faixa), 2) if cm_faixa else None,
                 "pct_abaixo_folha_pct": posicao(fp_faixa, pau_ind.get("folha_pct")),
                 "pct_abaixo_custo_medio": posicao(cm_faixa, pau_ind.get("custo_medio")),
                 "mediana_por_mil_regiao": round(statistics.median(
                     [c["por_mil"] for c in cidades]), 2),
                 "mediana_receita_hab_regiao": round(statistics.median(
                     [c["receita_hab"] for c in com_receita]), 2) if com_receita else None}}
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")

    def f(v, c=1):
        return f"{v:,.{c}f}".replace(",", "@").replace(".", ",").replace("@", ".")
    cab = f"{'município':22s} {'população':>10s} {'serv/mil':>9s} {'custo médio':>13s} {'folha/pago':>11s} {'arrecad./hab':>14s}"
    print(cab)
    print("-" * len(cab))
    for c in cidades:
        r = "R$ " + f(c["receita_hab"], 0) if "receita_hab" in c else "—"
        cm = "R$ " + f(c["custo_medio"], 0) if "custo_medio" in c else "—"
        fp = f(c["folha_pct"]) + "%" if "folha_pct" in c else "—"
        print(f"{c['cidade']:22s} {f(c['pop'],0):>10s} {f(c['por_mil']):>9s} {cm:>13s} {fp:>11s} {r:>14s}")
    print("-" * len(cab))
    ref = saida["referencia"]
    print(f"mediana da região: {f(ref['mediana_por_mil_regiao'])} serv/mil · "
          f"R$ {f(ref['mediana_receita_hab_regiao'],0)}/hab")
    print(f"mediana dos {ref['municipios_na_faixa']} municípios de SP entre "
          f"{f(FAIXA[0],0)} e {f(FAIXA[1],0)} habitantes: {f(ref['mediana_por_mil'])} serv/mil · "
          f"R$ {f(ref['mediana_receita_hab'],0)}/hab ({ref['municipios_na_faixa_com_receita']} com receita)")
    if ref.get("mediana_custo_medio"):
        print(f"  custo médio por servidor: R$ {f(ref['mediana_custo_medio'],0)}/mês "
              f"(Paulínia acima de {ref['pct_abaixo_custo_medio']}% deles) · "
              f"folha/pago: {f(ref['mediana_folha_pct'])}% "
              f"(Paulínia acima de {ref['pct_abaixo_folha_pct']}%)")
    print(f"\n-> {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
