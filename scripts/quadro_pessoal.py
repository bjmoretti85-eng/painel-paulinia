#!/usr/bin/env python3
"""Lê o Quadro de Pessoal (PDF do portal) e explica de onde vem o salário acima da tabela.

O portal publica, no mesmo módulo escondido das tabelas salariais, um Quadro de Pessoal
com uma linha por servidor: nome, cargo, classe, secretaria, admissão, **jornada**,
**jornada de designação** e **função designada**.

A folha não diz quanto é hora extra e quanto é gratificação — o portal não publica isso.
Mas com o Quadro dá para separar os servidores em grupos e comparar a mediana de cada um:

    sem função e com a jornada do cargo   -> o "salário de base" real
    com jornada de designação maior       -> jornada ampliada
    com função designada                  -> gratificação de chefia

A diferença entre o primeiro grupo e a tabela de vencimentos é o que sobra: adicionais
(quinquênio, sexta-parte, insalubridade, noturno) e horas extras, que continuam juntos.

    python scripts/quadro_pessoal.py --listar     # quais Quadros existem em data/raw/tabelas
    python scripts/quadro_pessoal.py              # -> data/decomposicao_folha.json

Precisa do pdftotext. Os PDFs vêm com scripts/tabelas_salariais.py --baixar.
"""
import argparse
import csv
import gzip
import json
import re
import statistics
import subprocess
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PDFS = RAIZ / "data/raw/tabelas"
SAIDA = RAIZ / "data/decomposicao_folha.json"
MIN_CARGO = 25          # cargos com menos servidores que isso não entram
MIN_GRUPO = 8           # grupos menores que isso não viram mediana publicada

# Os dois Quadros publicados têm cabeçalhos diferentes: o de setembro/2025 traz
# MATRÍCULA (que é a melhor chave para casar com a folha) e o de abril/2026 não.
# Por isso as colunas são descobertas pelo cabeçalho de cada página, não fixadas.
# Não precisamos separar nome, cargo e secretaria do PDF: o casamento é pela MATRÍCULA
# e todo o resto já vem da folha. Então basta reconhecer, em cada linha, os campos que
# têm formato próprio: matrícula (inteiro no começo), admissão (data), as duas jornadas
# e o que sobra depois delas, que é a função designada.
LINHA = re.compile(
    r"^\s*(\d{3,7})\s+.*?(\d{2}/\d{2}/\d{4})\s+([\d.,]+)\s+([\d.,]+)\s*(.*?)\s*$")


def ler_quadro(pdf):
    """Lê o Quadro de Pessoal. Só serve o layout que traz matrícula (setembro/2025);
    o de abril/2026 publica data de admissão como número de série e não tem matrícula."""
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                         capture_output=True, text=True, check=True).stdout
    registros = []
    for linha in txt.splitlines():
        m = LINHA.match(linha)
        if not m:
            continue
        matricula, admissao, jornada, jornada_des, funcao = m.groups()
        # a função designada não pode ser um pedaço de número solto
        if re.fullmatch(r"[\d.,]*", funcao):
            funcao = ""
        registros.append({"matricula": matricula.lstrip("0"), "admissao": admissao,
                          "jornada": jornada, "jornada_designacao": jornada_des,
                          "funcao_designada": funcao})
    return registros


def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9 ]", " ", re.sub(r"\s+", " ", s)).strip()


def numero(s):
    try:
        return float((s or "").replace(".", "").replace(",", "."))
    except ValueError:
        return None


def folha(ano=2025, mes="12"):
    por_cargo = defaultdict(list)
    with gzip.open(RAIZ / f"data/raw/servidores_{ano}.csv.gz", "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["mes"] != mes or r["tipo_folha"] != "9":
                continue
            if "Inativo" in r["cargo"] or "Pensionista" in r["cargo"]:
                continue
            v = float(r["vencimentos"] or 0)
            if v > 0:
                por_cargo[r["cargo"]].append((norm(r["nome"]), r["matricula"].strip().lstrip("0"), v))
    return por_cargo


def grupo_do_servidor(reg):
    """Quatro grupos. Cuidado com o terceiro: jornada designada MENOR que a do cargo
    (200 -> 180, por exemplo) não significa ganhar menos. Na prática esses servidores
    ganham bem mais, o que sugere escala de turno com adicionais — mas o portal não
    informa a verba, então o rótulo descreve o fato e não a causa."""
    if reg["funcao_designada"]:
        return "funcao"
    j, jd = numero(reg["jornada"]), numero(reg["jornada_designacao"])
    if j and jd:
        if jd > j:
            return "ampliada"
        if jd < j:
            return "designada_menor"
    return "base"


# Rótulos em português de gente. "Jornada designada" é vocabulário de RH público e
# engana: o grupo de jornada MENOR ganha MAIS. Os rótulos abaixo dizem o que a pessoa
# faz, não como o RH classifica.
ROTULOS_PUBLICOS = {
    "base": "trabalha as horas normais do cargo",
    "ampliada": "foi contratado para mais horas",
    "designada_menor": "trabalha em turno ou escala",
    "funcao": "chefia uma equipe",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--pdf", help="qual Quadro usar (padrão: o mais próximo de dezembro)")
    a = ap.parse_args()

    quadros = sorted(PDFS.glob("QUADRO DE PESSOAL*.pdf"))
    if a.listar or not quadros:
        for q in quadros:
            print("  ", q.name)
        if not quadros:
            print("Nenhum Quadro de Pessoal. Rode: python scripts/tabelas_salariais.py --baixar")
        return

    # o Quadro de setembro/2025 é o mais perto da folha de dezembro/2025
    escolhido = (PDFS / a.pdf) if a.pdf else next(
        (q for q in quadros if "SETEMBRO" in q.name.upper()), quadros[0])
    print(f"Quadro de Pessoal: {escolhido.name}")
    quadro = ler_quadro(escolhido)
    print(f"  {len(quadro)} servidores lidos")

    por_matricula = {}
    for reg in quadro:
        por_matricula.setdefault(reg["matricula"], reg)
    print(f"  matrículas distintas: {len(por_matricula)}")

    por_cargo, saida = folha(), []
    def achar(nome, matricula):
        return por_matricula.get(matricula)

    casados = sum(1 for c in por_cargo for n, mat, _ in por_cargo[c] if achar(n, mat))
    total = sum(len(v) for v in por_cargo.values())
    print(f"  casaram com a folha de dez/2025: {casados}/{total} ({100*casados/total:.0f}%)\n")

    for cargo, pessoas in por_cargo.items():
        ligados = [(achar(n, mat), v) for n, mat, v in pessoas if achar(n, mat)]
        if len(ligados) < MIN_CARGO:
            continue
        grupos = defaultdict(list)
        for reg, v in ligados:
            horas = numero(reg["jornada_designacao"]) or numero(reg["jornada"])
            grupos[grupo_do_servidor(reg)].append((v, horas))
        item = {"cargo": re.sub(r"\s*-\s*LC\s*[\d/]+", "", cargo).strip(),
                "n_folha": len(pessoas), "n_casado": len(ligados),
                "rotulos": ROTULOS_PUBLICOS, "grupos": {}}
        for nome, vals in grupos.items():
            if len(vals) < MIN_GRUPO:
                continue
            salarios = [v for v, _ in vals]
            horas = [h for _, h in vals if h]
            # o valor da hora é o que desarma a leitura errada: mostra se a diferença
            # é quantidade de trabalho ou outra coisa
            por_hora = [v / h for v, h in vals if h]
            item["grupos"][nome] = {
                "n": len(vals),
                "mediana": round(statistics.median(salarios), 2),
                "horas": round(statistics.median(horas)) if horas else None,
                "por_hora": round(statistics.median(por_hora), 2) if por_hora else None,
            }
        if "base" in item["grupos"] and len(item["grupos"]) > 1:
            saida.append(item)

    saida.sort(key=lambda x: -x["n_casado"])
    print(f"{'cargo':30s} {'grupo':36s} {'n':>5s} {'horas':>6s} {'mediana':>11s} {'R$/hora':>9s}")
    print("-" * 104)
    for item in saida[:12]:
        for chave in ("base", "ampliada", "designada_menor", "funcao"):
            g = item["grupos"].get(chave)
            if g:
                print(f"{item['cargo'][:30]:30s} {ROTULOS_PUBLICOS[chave]:36s} {g['n']:5d} "
                      f"{(g['horas'] or 0):6d} "
                      f"{('R$ ' + format(g['mediana'], ',.0f')).replace(',', '.'):>11s} "
                      f"{('R$ ' + format(g['por_hora'] or 0, ',.2f')).replace(',', '@').replace('.', ',').replace('@', '.'):>9s}")
        print()

    SAIDA.write_text(json.dumps({"quadro": escolhido.name, "cargos": saida},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {SAIDA.relative_to(RAIZ)}  ({len(saida)} cargos)")


if __name__ == "__main__":
    main()
