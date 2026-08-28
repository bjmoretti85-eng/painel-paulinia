#!/usr/bin/env python3
"""
Baixa os conjuntos de dados anuais do TCE-SP (despesas e receitas de todos os
municípios paulistas) e guarda em data/raw/ apenas as linhas de Paulínia,
comprimidas (.csv.gz).

Os arquivos de despesas têm ~2 GB cada (ZIP com um único CSV dentro). Para não
ocupar disco, o ZIP é lido em streaming: o cabeçalho local do ZIP é pulado e o
fluxo deflate é descomprimido em memória enquanto é baixado.

Uso:
    python scripts/baixar_dados.py                # anos padrão (ver ANOS)
    python scripts/baixar_dados.py 2024 2025      # anos específicos
    python scripts/baixar_dados.py --so-receitas  # só receitas (rápido)
"""
import gzip
import struct
import sys
import urllib.request
import zlib
from pathlib import Path

ANOS = [2023, 2024, 2025]
IBGE_PAULINIA = "3536505"
NOME_PAULINIA_LATIN1 = "Paul\xedn\x69a".encode("latin-1")  # "Paulínia" em Latin-1

BASE = "https://transparencia.tce.sp.gov.br/sites/default/files/conjunto-dados/"
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def abrir(url):
    req = urllib.request.Request(url, headers={"User-Agent": "painel-paulinia/1.0"})
    return urllib.request.urlopen(req, timeout=120)


def linhas_do_zip_em_streaming(resp, chunk=1 << 20):
    """Gera as linhas (bytes, sem \\n) do primeiro arquivo dentro de um ZIP
    lido em streaming a partir de um objeto de resposta HTTP."""
    cabecalho = resp.read(30)
    assinatura, _, _, metodo, _, _, _, _, _, tam_nome, tam_extra = struct.unpack(
        "<IHHHHHIIIHH", cabecalho
    )
    if assinatura != 0x04034B50:
        raise RuntimeError("Não parece um arquivo ZIP")
    resp.read(tam_nome + tam_extra)
    if metodo == 8:
        d = zlib.decompressobj(-15)
        descomprimir = d.decompress
    elif metodo == 0:
        descomprimir = lambda b: b  # armazenado sem compressão
    else:
        raise RuntimeError(f"Método de compressão não suportado: {metodo}")

    resto = b""
    while True:
        bloco = resp.read(chunk)
        if not bloco:
            break
        dados = resto + descomprimir(bloco)
        partes = dados.split(b"\n")
        resto = partes.pop()
        for linha in partes:
            yield linha.rstrip(b"\r")
    if resto:
        yield resto.rstrip(b"\r")


def filtrar(url, destino, coluna, valor):
    print(f"Baixando {url}")
    total = 0
    mantidas = 0
    with abrir(url) as resp, gzip.open(destino, "wb") as saida:
        for i, linha in enumerate(linhas_do_zip_em_streaming(resp)):
            if i == 0:
                saida.write(linha + b"\n")
                continue
            total += 1
            campos = linha.split(b";")
            if len(campos) > coluna and campos[coluna] == valor:
                saida.write(linha + b"\n")
                mantidas += 1
            if total % 2_000_000 == 0:
                print(f"  ... {total:,} linhas lidas, {mantidas:,} de Paulínia", flush=True)
    print(f"  OK: {mantidas:,} linhas de Paulínia (de {total:,}) -> {destino.name}")


def main(argv):
    anos = [int(a) for a in argv if a.isdigit()] or ANOS
    so_receitas = "--so-receitas" in argv
    RAW.mkdir(parents=True, exist_ok=True)
    for ano in anos:
        # receitas: coluna 3 = ds_municipio ("Paulínia")
        filtrar(f"{BASE}receitas-{ano}.zip", RAW / f"receitas_paulinia_{ano}.csv.gz", 2, NOME_PAULINIA_LATIN1)
        if not so_receitas:
            # despesas: coluna 4 = codigo_municipio_ibge
            filtrar(f"{BASE}despesas-{ano}.zip", RAW / f"despesas_paulinia_{ano}.csv.gz", 3, IBGE_PAULINIA.encode())


if __name__ == "__main__":
    main(sys.argv[1:])
