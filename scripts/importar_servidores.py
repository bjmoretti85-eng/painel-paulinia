#!/usr/bin/env python3
"""Importa a folha de pagamento de OUTRAS cidades para o formato do painel.

Cada prefeitura publica a folha de um jeito, e algumas (Campinas) exigem
captcha, ou seja, o download é manual. Este script não baixa nada: ele lê o
arquivo que a prefeitura forneceu e devolve sempre o mesmo formato, o mesmo
de data/raw/servidores_{ano}.csv.gz de Paulínia:

    matricula;nome;cargo;secretaria;data_admissao;data_rescisao;ano;mes;
    tipo_folha;vencimentos;descontos;liquido[;jornada]

Assim cada cidade nova vira um mapeamento de colunas, não um raspador.

Uso:
    # 1. ver o que tem dentro do arquivo que você baixou
    python scripts/importar_servidores.py --inspecionar data/raw/entrada/arquivo.csv

    # 2. converter para o formato do painel
    python scripts/importar_servidores.py --cidade campinas --ano 2025 --mes 12 \
        data/raw/entrada/arquivo.csv

Só biblioteca padrão.
"""
import argparse
import csv
import gzip
import re
import statistics
import sys
import unicodedata
from collections import Counter
from pathlib import Path

SCHEMA = ["matricula", "nome", "cargo", "secretaria", "data_admissao",
          "data_rescisao", "ano", "mes", "tipo_folha", "vencimentos",
          "descontos", "liquido", "bruto_recorrente", "jornada"]

# vencimentos       = tudo que a cidade chama de bruto no mês
# bruto_recorrente  = o bruto sem verbas de uma vez só (13º, prêmio férias,
#                     licença-prêmio, salário atrasado, eventual). É o número honesto
#                     para comparar cargos entre cidades. Vazio = use vencimentos.

# Nomes de coluna que cada campo pode ter nos portais. Comparação sem acento,
# sem espaço e sem maiúscula, então "Data Admissão" casa com "dataadmissao".
COLUNAS = {
    "matricula":     ["matricula", "matriculaservidor", "registro", "rf", "cadastro"],
    "nome":          ["nome", "nomeservidor", "servidor", "nomefuncionario"],
    "cargo":         ["cargo", "cargofuncao", "funcao", "descricaocargo",
                      "cargoatual", "denominacaocargo"],
    "secretaria":    ["secretaria", "orgao", "unidade", "lotacao", "setor",
                      "orgaolotacao", "secretariamunicipal"],
    "data_admissao": ["dataadmissao", "admissao", "dtadmissao", "dataingresso",
                      "dataexercicio"],
    "data_rescisao": ["datarescisao", "rescisao", "desligamento", "dtdemissao",
                      "datademissao", "dataexoneracao"],
    "vencimentos":   ["vencimentos", "salariobruto", "totalbruto", "bruto",
                      "remuneracaobruta", "proventos", "totalvencimentos",
                      "totalproventos", "remuneracaobasica", "salariobase"],
    "descontos":     ["descontos", "totaldescontos", "totaldedescontos"],
    "liquido":       ["liquido", "salarioliquido", "totalliquido", "valorliquido",
                      "remuneracaoliquida", "liquidoreceber"],
    "jornada":       ["jornada", "cargahoraria", "ch", "jornadatrabalho"],
    "ano":           ["ano", "anoreferencia", "exercicio"],
    "mes":           ["mes", "mesreferencia", "competencia"],
}

# Ajustes por cidade. "extra" acrescenta nomes de coluna ao mapa acima.
CIDADES = {
    "campinas": {
        "nome_exibicao": "Campinas",
        "ibge": 3509502,
        "fonte": "https://remuneracoes.campinas.sp.gov.br/remuneracoes/relatorio/"
                 "PMCTransparenciaSalarioServidor (exportação CSV, exige captcha)",
        "adaptador": "adaptar_campinas",
        "extra": {},
    },
    "novaodessa": {
        "nome_exibicao": "Nova Odessa",
        "ibge": 3533403,
        "fonte": "https://transparencia-novaodessa.smarapd.com.br (mesmo sistema "
                 "de Paulínia; dá para usar baixar_servidores.py)",
        "extra": {},
    },
}


def adaptar_campinas(reg):
    """Layout da exportação CSV de Campinas (conferido em dez/2025).

    Matricula;Secretaria;Codigo Lotação;Nome Lotação;Código Cargo;Verbas Fixas;
    Cargo Comissão / Função Gratificada;Produtividade;Hora Extra/Adicionais;
    Sucumbência;Eventual;Adic.Crg./ Local/Jorn.;Salário Atraso;Prêmio Férias;
    Licença Prêmio;13º Salário;Total Bruto;Deduções;Bruto c/ Deduções

    Não traz nome (ótimo), nem admissão, nem jornada. "Código Cargo" vem como
    "61011 - MONITOR INFANTO JUVENIL I" com espaços à direita.
    "Total Bruto" é a soma exata das parcelas (conferido: erro <= R$ 0,02).
    "Bruto c/ Deduções" é menor que o bruto e parece ser o valor após as
    deduções legais, ou seja, o líquido - tratamos assim, mas sem certeza.
    """
    def v(col):
        return num(reg.get(col) or 0)

    cargo = (reg.get("Código Cargo") or "").strip()
    codigo = ""
    if " - " in cargo:
        codigo, cargo = cargo.split(" - ", 1)
        codigo, cargo = codigo.strip(), cargo.strip()

    bruto = v("Total Bruto")
    # "Eventual" também é verba de uma vez só: em dez/2023 ela pagou o rateio do Fundeb
    # a 86% dos professores (mediana R$ 6.328) e inflou a mediana da Educação em ~65%.
    # Em dez/2024 e dez/2025 só 2% recebem, e valores pequenos (mediana ~R$ 250).
    uma_vez = (v("13º Salário") + v("Prêmio Férias") + v("Licença Prêmio")
               + v("Salário Atraso") + v("Eventual"))
    liquido = v("Bruto c/ Deduções")
    return {
        "matricula": (reg.get("Matricula") or "").strip(),
        "nome": "",
        "cargo": cargo,
        "secretaria": (reg.get("Secretaria") or "").strip(),
        "data_admissao": "",
        "data_rescisao": "",
        "tipo_folha": "9",
        "vencimentos": bruto,
        "descontos": max(bruto - liquido, 0.0),
        "liquido": liquido,
        "bruto_recorrente": max(bruto - uma_vez, 0.0),
        "jornada": "",
        "_codigo_cargo": codigo,
    }


def chave(texto):
    """'Data Admissão' -> 'dataadmissao'."""
    t = unicodedata.normalize("NFD", str(texto))
    t = t.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def ler_texto(caminho):
    bruto = Path(caminho).read_bytes()
    if str(caminho).endswith(".gz"):
        bruto = gzip.decompress(bruto)
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return bruto.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1", "replace"), "latin-1"


def detectar_sep(linha):
    return max(";,\t|", key=linha.count)


def num(valor):
    """'R$ 1.234,56' e '1234.56' viram 1234.56."""
    if valor is None:
        return 0.0
    s = re.sub(r"[^\d,.\-]", "", str(valor))
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") \
            else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def abrir(caminho):
    texto, enc = ler_texto(caminho)
    linhas = texto.splitlines()
    # Alguns portais põem título/subtítulo antes do cabeçalho: usa a primeira
    # linha que tenha pelo menos 4 separadores como cabeçalho.
    inicio, sep = 0, ";"
    for i, linha in enumerate(linhas[:30]):
        s = detectar_sep(linha)
        if linha.count(s) >= 4:
            inicio, sep = i, s
            break
    leitor = csv.DictReader(linhas[inicio:], delimiter=sep)
    return leitor, enc, sep, inicio


def mapear(cabecalho, cidade):
    mapa = {k: list(v) for k, v in COLUNAS.items()}
    for campo, nomes in CIDADES.get(cidade, {}).get("extra", {}).items():
        mapa.setdefault(campo, []).extend(nomes)
    disponiveis = {chave(c): c for c in cabecalho if c}
    achados, faltando = {}, []
    for campo, candidatos in mapa.items():
        for cand in candidatos:
            if cand in disponiveis:
                achados[campo] = disponiveis[cand]
                break
        else:
            faltando.append(campo)
    return achados, faltando


def inspecionar(caminho):
    leitor, enc, sep, inicio = abrir(caminho)
    cabecalho = leitor.fieldnames or []
    print(f"arquivo    : {caminho}")
    print(f"codificação: {enc}   separador: {sep!r}   cabeçalho na linha {inicio + 1}")
    print(f"colunas    : {len(cabecalho)}")
    for c in cabecalho:
        print(f"   - {c}   [{chave(c)}]")
    print()
    for i, linha in enumerate(leitor):
        if i >= 3:
            break
        print(f"linha {i + 1}: " + " | ".join(f"{k}={v}" for k, v in linha.items() if v))
    print()
    for cidade in CIDADES:
        achados, faltando = mapear(cabecalho, cidade)
        print(f"mapeamento como '{cidade}': {len(achados)} campos reconhecidos")
        for campo, col in achados.items():
            print(f"   {campo:15s} <- {col}")
        if faltando:
            print(f"   NÃO ENCONTRADO: {', '.join(faltando)}")
        print()


def converter(caminho, cidade, ano, mes, saida):
    leitor, enc, sep, _ = abrir(caminho)
    cabecalho = leitor.fieldnames or []
    especifico = CIDADES.get(cidade, {}).get("adaptador")
    adaptador = globals()[especifico] if especifico else None

    if not adaptador:
        achados, faltando = mapear(cabecalho, cidade)
        if "cargo" in faltando or "vencimentos" in faltando:
            sys.exit("ERRO: não achei as colunas de cargo e/ou bruto. Rode com "
                     "--inspecionar e me mande a saída para eu ajustar o mapa.")

    linhas, brutos, recorrentes, cargos = [], [], [], Counter()
    com_extra = 0
    for reg in leitor:
        if adaptador:
            d = adaptador(reg)
        else:
            def campo(nome):
                col = achados.get(nome)
                return (reg.get(col) or "").strip() if col else ""
            bruto = num(campo("vencimentos"))
            liquido = num(campo("liquido"))
            d = {
                "matricula": campo("matricula"), "nome": campo("nome"),
                "cargo": campo("cargo"), "secretaria": campo("secretaria"),
                "data_admissao": campo("data_admissao"),
                "data_rescisao": campo("data_rescisao"), "tipo_folha": "9",
                "vencimentos": bruto,
                "descontos": num(campo("descontos")) or max(bruto - liquido, 0.0),
                "liquido": liquido, "bruto_recorrente": "", "jornada": campo("jornada"),
            }
        if not d["cargo"] and not d["vencimentos"]:
            continue

        rec = d.get("bruto_recorrente")
        if rec not in ("", None) and abs(rec - d["vencimentos"]) > 0.01:
            com_extra += 1
        linhas.append({
            "matricula": d["matricula"], "nome": d["nome"], "cargo": d["cargo"],
            "secretaria": d["secretaria"], "data_admissao": d["data_admissao"],
            "data_rescisao": d["data_rescisao"], "ano": ano, "mes": mes,
            "tipo_folha": d["tipo_folha"],
            "vencimentos": f"{d['vencimentos']:.2f}",
            "descontos": f"{d['descontos']:.2f}",
            "liquido": f"{d['liquido']:.2f}",
            "bruto_recorrente": f"{rec:.2f}" if rec not in ("", None) else "",
            "jornada": d["jornada"],
        })
        if d["vencimentos"] > 0:
            brutos.append(d["vencimentos"])
            cargos[d["cargo"]] += 1
        if rec not in ("", None) and rec > 0:
            recorrentes.append(rec)

    if not linhas:
        sys.exit("ERRO: nenhuma linha aproveitada. Rode com --inspecionar.")

    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(saida, "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA, delimiter=";")
        w.writeheader()
        w.writerows(linhas)

    def brl(v):
        return ("R$ " + f"{v:,.2f}").replace(",", "@").replace(".", ",").replace("@", ".")

    print(f"{CIDADES[cidade]['nome_exibicao']} {mes:02d}/{ano}")
    print(f"  {len(linhas)} linhas -> {saida}")
    print(f"  bruto        mediana {brl(statistics.median(brutos))}"
          f"   média {brl(statistics.fmean(brutos))}")
    if recorrentes:
        print(f"  sem verba de uma vez só  mediana {brl(statistics.median(recorrentes))}"
              f"   média {brl(statistics.fmean(recorrentes))}")
        print(f"  {com_extra} de {len(linhas)} linhas "
              f"({100 * com_extra / len(linhas):.0f}%) têm verba de uma vez só no bruto")
    print("  cargos mais frequentes:")
    for cargo, n_ in cargos.most_common(8):
        print(f"     {n_:6d}  {cargo}")
    if not any(l["jornada"] for l in linhas):
        print("  AVISO: sem coluna de jornada. Comparar salário por cargo entre")
        print("         cidades sem saber a jornada engana (professor 20h x 40h).")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("arquivo", help="CSV baixado do portal da cidade")
    p.add_argument("--inspecionar", action="store_true",
                   help="só mostra colunas e amostra, não converte")
    p.add_argument("--cidade", choices=sorted(CIDADES))
    p.add_argument("--ano", type=int)
    p.add_argument("--mes", type=int, default=12,
                   help="mês de referência (o painel usa 12, igual a Paulínia)")
    p.add_argument("--saida")
    a = p.parse_args()

    if a.inspecionar:
        return inspecionar(a.arquivo)
    if not a.cidade or not a.ano:
        sys.exit("informe --cidade e --ano (ou use --inspecionar)")
    saida = a.saida or f"data/raw/servidores_{a.cidade}_{a.ano}_{a.mes:02d}.csv.gz"
    converter(a.arquivo, a.cidade, a.ano, a.mes, saida)


if __name__ == "__main__":
    main()
