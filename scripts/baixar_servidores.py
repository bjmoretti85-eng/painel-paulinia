#!/usr/bin/env python3
"""
Baixa a folha de pagamento por servidor do portal de transparência da Prefeitura
de Paulínia (SMARAPD, visão "Pagamentos a Servidores") e grava em
data/raw/servidores_{ano}.csv.gz. É retomável: se interromper, rode de novo e ele continua
de onde parou (as páginas ficam em data/raw/servidores_{ano}/; pode apagar depois).
O CSV final tem uma linha por servidor x mês x tipo de folha.

Campos: matricula, nome, cargo, secretaria, data_admissao, data_rescisao, ano, mes,
tipo_folha, vencimentos, descontos, liquido.

Uso:
    python scripts/baixar_servidores.py            # anos padrão
    python scripts/baixar_servidores.py 2025       # um ano
"""
import csv
import gzip
import json
import sys
import time
import urllib.request
from pathlib import Path

ANOS = [2023, 2024, 2025]
URL = "https://transparencia-paulinia.smarapd.com.br/paiportalserver/modulovisao/filter"
POR_PAGINA = 5000
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://transparencia-paulinia.smarapd.com.br",
    "Referer": "https://transparencia-paulinia.smarapd.com.br/",
    "User-Agent": "Mozilla/5.0 (painel-paulinia; dados publicos)",
}
CAMPOS = ["matricula", "nome", "cargo", "secretaria", "data_admissao", "data_rescisao",
          "ano", "mes", "tipo_folha", "vencimentos", "descontos", "liquido"]


def pagina(ano, pag):
    corpo = json.dumps({
        "ChaveModulo": "servidor", "NomeVisao": "pagamentoaservidores", "Filtros": [],
        "Periodicidade": "ANUAL", "Periodo": None, "Exercicio": ano,
        "Pagina": pag, "QuantidadeRegistros": str(POR_PAGINA),
        "Ordenacao": [{"ColunaOrdem": "NomeServidor", "TipoOrdem": "ascend", "Ordem": 1}],
        "FiltroRedirecionaVisao": {"Campo": None, "Valor": None, "TipoValor": None},
    }).encode()
    req = urllib.request.Request(URL, data=corpo, headers=HEADERS)
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:  # noqa
            print(f"   tentativa {tentativa+1} falhou: {e}")
            time.sleep(3 * (tentativa + 1))
    raise RuntimeError(f"não consegui baixar {ano} página {pag}")


def num(s):
    return s.replace(".", "").replace(",", ".") if s else "0"


def mes_do_id(v, ano):
    # ID = matricula + tipo_folha + ano + mes  (ex.: 150071 9 2025 12)
    prefixo = v["Matricula"] + v["TipoFolha"] + str(ano)
    ident = v.get("ID", "")
    return ident[len(prefixo):] if ident.startswith(prefixo) else ""


def baixar(ano):
    """Baixa página a página em data/raw/servidores_{ano}/pag_N.json.gz (retomável) e,
    quando todas existirem, consolida em data/raw/servidores_{ano}.csv.gz."""
    pasta = RAW / f"servidores_{ano}"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = RAW / f"servidores_{ano}.csv.gz"
    pag, total_pags = 1, None
    while True:
        arq = pasta / f"pag_{pag}.json.gz"
        if arq.exists():
            with gzip.open(arq, "rt", encoding="utf-8") as f:
                total_pags = json.load(f)["QuantidadePaginas"]
        else:
            j = pagina(ano, pag)
            total_pags = j["QuantidadePaginas"]
            with gzip.open(arq, "wt", encoding="utf-8") as f:
                json.dump(j, f, ensure_ascii=False)
            print(f"   {ano}: página {pag}/{total_pags}", flush=True)
        if pag >= total_pags:
            break
        pag += 1
    n = 0
    with gzip.open(destino, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(CAMPOS)
        for pag in range(1, total_pags + 1):
            with gzip.open(pasta / f"pag_{pag}.json.gz", "rt", encoding="utf-8") as g:
                j = json.load(g)
            for v in j["Valores"]:
                w.writerow([v["Matricula"], v["NomeServidor"], v["Cargo"], v["Funcao"], v["DataAdmissao"],
                            v["DtRescisao"], ano, mes_do_id(v, ano), v["TipoFolha"],
                            num(v["TotalVencimentos"]), num(v["TotalDescontos"]), num(v["SalarioLiquido"])])
                n += 1
    print(f"-> {destino.name}: {n:,} linhas ({total_pags} páginas)")


def main(argv):
    anos = [int(a) for a in argv if a.isdigit()] or ANOS
    RAW.mkdir(parents=True, exist_ok=True)
    for ano in anos:
        print(f"Baixando servidores {ano}…")
        baixar(ano)


if __name__ == "__main__":
    main(sys.argv[1:])
