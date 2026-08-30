#!/usr/bin/env python3
"""Compara o salário por cargo entre Paulínia e as cidades importadas.

O julgamento fica todo na tabela PARES abaixo: cada linha diz exatamente
quais cargos de cada cidade entram na conta, o quanto se confia na
equivalência e o que o leitor precisa saber para não interpretar errado.
Fora dessa tabela, o resto é aritmética.

    python scripts/comparar_cargos.py              # relatório + data/comparativo_cargos.json
    python scripts/comparar_cargos.py --listar     # cargos grandes que ainda não foram pareados

Fontes das jornadas e das ressalvas: ver docs/comparativo-campinas-paulinia.md
(LC 65/2017 e LC 66/2017 de Paulínia, PS 001/2026 de Paulínia, editais
01/2025 e 01/2022 de Campinas).
"""
import argparse
import csv
import gzip
import json
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ANOS = [2023, 2024, 2025]

# ---------------------------------------------------------------------------
# A TABELA DE EQUIVALÊNCIAS. É aqui que mora o julgamento — revise esta parte.
#
# confianca: alta  = mesmo cargo, mesma função, jornada conhecida e parecida
#            media = mesma função, mas jornada ou carreira diferem
#            baixa = só publique com a ressalva bem visível
# Os nomes em "paulinia"/"campinas" são exatos (sem acento, maiúsculas).
# ---------------------------------------------------------------------------
PARES = [
    {
        "nome": "Professor dos anos iniciais e da educação infantil",
        # Entre julho e agosto de 2025 cerca de 350 servidores saíram do PEB I para Educadora
        # Infantil: ajuste de lei, as mesmas pessoas. Somar os dois mantém a população igual nos
        # três anos (883, 885, 864) e igual ao escopo do lado de Campinas (PEB I + PEB II, que
        # também cobre creche e anos iniciais). Só o PEB I de 2025 inflaria a diferença em 14 pontos.
        "paulinia": ["PROFESSOR DE EDUCACAO BASICA I - PEBI - LC 65/2017",
                     "EDUCADORA INFANTIL - LC 66/2017"],
        "campinas": ["PROFESSOR PEB I", "PROFESSOR PEB II"],
        "confianca": "media",
        "jornada": {"paulinia": "30, 38 ou 45 horas-aula de 50 min (≈25h, 31,7h ou 37,5h)",
                    "campinas": "32h ou 40h de relógio, definidas pela Prefeitura"},
        "obs": ("PEB I e PEB II querem dizer coisas diferentes nas duas cidades: em Paulínia "
                "o PEB I cobre creche, pré-escola e o 1º ao 5º ano; em Campinas o PEB I é só "
                "educação infantil e o PEB II são os anos iniciais. Por isso somamos os dois "
                "de Campinas. Não inclui os professores temporários (CTD) de Paulínia."),
    },
    {
        "nome": "Professor de creche e pré-escola",
        "paulinia": ["EDUCADORA INFANTIL - LC 66/2017"],
        "campinas": ["PROFESSOR PEB I"],
        "confianca": "media",
        # Antes de agosto/2025 este cargo tinha só ~50 pessoas: quem fazia creche e pré-escola
        # estava no PEB I. Comparar 2023/2024 aqui seria descrever outro grupo.
        "desde": 2025,
        "jornada": {"paulinia": "36h (30h com alunos + 6h de preparação)",
                    "campinas": "32h ou 40h"},
        "obs": ("A Educadora Infantil de Paulínia exerce regência em creche, mas está no quadro "
                "geral, não no magistério. O equivalente pela função em Campinas é o PEB I de "
                "educação infantil. NÃO comparar com o Agente de Educação Infantil de Campinas, "
                "que é cargo de cuidado e apoio, de ensino médio. As duas carreiras estão em "
                "mudança por causa da Lei federal 15.326/2026."),
    },
    {
        "nome": "Guarda municipal",
        "paulinia": ["GUARDA CIVIL MUNICIPAL"],
        "campinas": ["__PREFIXO__GM "],
        "confianca": "media",
        "jornada": {"paulinia": "não informada na folha", "campinas": "não informada na folha"},
        "obs": ("Em Campinas o cargo é dividido por classe e até por sexo ('GM 1 Classe "
                "Masculino/Feminino'); somamos todos. Paulínia tem um cargo único, o que mistura "
                "níveis de carreira diferentes dos dois lados."),
    },
    {
        "nome": "Enfermeiro",
        "paulinia": ["ENFERMEIRO - LC 66/2017"],
        "campinas": ["ENFERMEIRO"],
        "confianca": "alta",
        "jornada": {"paulinia": "não informada na folha", "campinas": "não informada na folha"},
        "obs": "Em Campinas inclui a Rede Mário Gatti, que é o hospital municipal.",
    },
    {
        "nome": "Técnico de enfermagem",
        "paulinia": ["TECNICO DE ENFERMAGEM - LC 66/2017"],
        "campinas": ["TECNICO ENFERMAGEM"],
        "confianca": "alta",
        "jornada": {"paulinia": "não informada na folha", "campinas": "não informada na folha"},
        "obs": "Em Campinas inclui a Rede Mário Gatti.",
    },
    {
        "nome": "Auxiliar de enfermagem",
        "paulinia": ["AUXILIAR DE ENFERMAGEM - LC 66/2017"],
        "campinas": ["AUX.ENFERMAGEM"],
        "confianca": "alta",
        "jornada": {"paulinia": "não informada na folha", "campinas": "não informada na folha"},
        "obs": "Cargo em extinção nas duas redes; o efetivo tende a cair.",
    },
    {
        "nome": "Agente de apoio operacional",
        "paulinia": ["AGENTE DE APOIO OPERACIONAL - LC 66/2017"],
        "campinas": ["AG. APOIO OPERACIONAL"],
        "confianca": "media",
        "jornada": {"paulinia": "não informada na folha", "campinas": "não informada na folha"},
        "obs": ("É o cargo mais numeroso de Paulínia (826) e junta funções variadas de apoio. "
                "A comparação de atribuição é frouxa."),
    },
    {
        "nome": "Agente administrativo",
        "paulinia": ["AUXILIAR DE APOIO ADMINISTRATIVO - LC 66/2017"],
        "campinas": ["AG.ADMINISTRATIVO"],
        "confianca": "baixa",
        "jornada": {"paulinia": "não informada na folha", "campinas": "não informada na folha"},
        "obs": "Nomes parecidos, atribuições possivelmente diferentes. Conferir antes de publicar.",
    },
]

def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", s).strip()


def ler_paulinia(ano):
    """Folha mensal (tipo 9) de dezembro, só quem está na ativa."""
    caminho = RAIZ / f"data/raw/servidores_{ano}.csv.gz"
    if not caminho.exists():
        return None
    por_cargo = defaultdict(list)
    with gzip.open(caminho, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["mes"] != "12" or r["tipo_folha"] != "9":
                continue
            if "Inativo" in r["cargo"] or "Pensionista" in r["cargo"]:
                continue
            v = float(r["vencimentos"] or 0)
            if v > 0:
                por_cargo[norm(r["cargo"])].append(v)
    return por_cargo


def ler_cidade(cidade, ano):
    caminho = RAIZ / f"data/raw/servidores_{cidade}_{ano}_12.csv.gz"
    if not caminho.exists():
        return None
    por_cargo = defaultdict(list)
    with gzip.open(caminho, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            v = float(r["bruto_recorrente"] or r["vencimentos"] or 0)
            if v > 0:
                por_cargo[norm(r["cargo"])].append(v)
    return por_cargo


def juntar(por_cargo, chaves):
    valores = []
    for chave in chaves:
        if chave.startswith("__PREFIXO__"):
            p = chave.replace("__PREFIXO__", "")
            for k, v in por_cargo.items():
                if k.startswith(p):
                    valores += v
        else:
            valores += por_cargo.get(chave, [])
    return valores


def resumo(valores):
    if not valores:
        return None
    ordenado = sorted(valores)
    q = statistics.quantiles(ordenado, n=4) if len(ordenado) >= 4 else [ordenado[0]] * 3
    return {"n": len(ordenado), "mediana": round(statistics.median(ordenado), 2),
            "media": round(statistics.fmean(ordenado), 2),
            "p25": round(q[0], 2), "p75": round(q[2], 2)}


def tabela_vs_folha(minimo=25):
    """Quanto cada cargo recebe acima do vencimento da tabela oficial da própria Paulínia.

    Vem de scripts/tabelas_salariais.py. Só entram cargos pagos por mês: quem é pago por
    hora-aula (professores, médicos plantonistas) precisaria da jornada de cada pessoa,
    que a folha não informa.
    """
    arq = RAIZ / "data/tabelas_salariais.json"
    if not arq.exists():
        return []
    cruz = json.loads(arq.read_text(encoding="utf-8")).get("cruzamento", {})
    linhas = []
    for cargo, c in cruz.items():
        if c.get("unidade") != "mes" or c["n"] < minimo:
            continue
        base = c.get("vencimento_topo") or c["vencimento"]
        if not base:
            continue
        linhas.append({
            "cargo": re.sub(r"\s*-\s*LC\s*[\d/]+", "", cargo).strip(),
            "n": c["n"], "mediana": c["mediana"], "vencimento": base,
            "acima": round(c["mediana"] / base, 3),
            "referencia": c["referencia"],
            "topo_de_carreira": bool(c.get("vencimento_topo")),
        })
    linhas.sort(key=lambda x: -x["acima"])
    return linhas


def decomposicao():
    """Vem de scripts/quadro_pessoal.py: mediana por grupo (jornada padrão, ampliada,
    em escala, com função de chefia) dentro de cada cargo."""
    arq = RAIZ / "data/decomposicao_folha.json"
    if not arq.exists():
        return {}
    return json.loads(arq.read_text(encoding="utf-8"))


# Cargos de Paulínia -> cargos de Campinas, para o teste da jornada padrão.
# Os nomes de Paulínia são os que saem de scripts/quadro_pessoal.py (sem o "- LC ...").
EQUIVALENTES_JP = {
    "Auxiliar de Apoio Administrativo": ["AG.ADMINISTRATIVO"],
    "Agente de Apoio Operacional": ["AG. APOIO OPERACIONAL"],
    "Monitor": ["MONITOR INFANTO JUVENIL I"],
    "Guarda Civil Municipal": ["__PREFIXO__GM "],
    "Farmaceutico": ["FARMACEUTICO"],
    "Medico Plantonista": ["MEDICO GERAL"],
}


def jornada_padrao(ano=2025):
    """A pergunta que a comparação cargo a cargo deixa em aberto: e se a diferença for só
    jornada? Este bloco compara com Campinas SOMENTE os servidores de Paulínia que estão
    na jornada padrão do cargo e sem função de chefia — sem hora a mais, sem gratificação
    de comando. Se a diferença sobrevive a isso, jornada não explica a distância.

    Vem de data/decomposicao_folha.json (grupo "base") cruzado com a folha de Campinas.
    """
    arq = RAIZ / "data/decomposicao_folha.json"
    if not arq.exists():
        return []
    dec = {c["cargo"]: c for c in json.loads(arq.read_text(encoding="utf-8")).get("cargos", [])}
    campinas = ler_cidade("campinas", ano)
    if not campinas:
        return []
    linhas = []
    for cargo, chaves in EQUIVALENTES_JP.items():
        item = dec.get(cargo)
        if not item or "base" not in item["grupos"]:
            continue
        base = item["grupos"]["base"]
        valores = juntar(campinas, chaves)
        if not valores:
            continue
        mc = statistics.median(valores)
        linhas.append({
            "cargo": cargo, "n": base["n"], "horas": base.get("horas"),
            "paulinia": base["mediana"], "campinas": round(mc, 2),
            "dif_pct": round(100 * (base["mediana"] / mc - 1), 1),
            # quantas horas por mês Paulínia teria que trabalhar para a diferença ser só jornada
            "horas_necessarias": round(base["horas"] * base["mediana"] / mc) if base.get("horas") else None,
        })
    linhas.sort(key=lambda x: -x["dif_pct"])
    return linhas


# População para o cálculo por habitante. Paulínia sai do painel.json; Campinas é
# constante porque não temos os dados do TCE dela carregados aqui.
POPULACAO = {"campinas": 1_189_761}       # estimativa IBGE, cidades-e-estados

# Secretaria de Paulínia -> secretaria(s) de Campinas. Julgamento explícito, como a
# tabela PARES: os nomes vêm exatamente como aparecem em cada folha.
AREAS = {
    "Educação": (["SECRETARIA MUNICIPAL DE EDUCACAO"], ["EDUCACAO"]),
    "Saúde": (["SECRETARIA MUNICIPAL DE SAUDE"], ["SAUDE", "REDE MARIO GATTI"]),
    "Segurança e defesa civil": (["SECRETARIA MUNICIPAL DE SEGURANCA PUBLICA",
                                  "SECRETARIA MUNICIPAL DE PROTECAO E DEFESA CIVIL"],
                                 ["SEGURANCA PUBLICA"]),
    "Assistência social": (["SECRETARIA MUNICIPAL DE ASSISTENCIA SOCIAL E PROTECAO A PESSOA"],
                           ["DESENVOLVIMENTO E ASSISTENCIA SOCIAL"]),
    "Obras e serviços públicos": (["SECRETARIA MUNICIPAL DE OBRAS E SERVICOS PUBLICOS"],
                                  ["SERVICOS PUBLICOS", "INFRAESTRUTURA"]),
}


def contar_por_secretaria(ano=2025):
    """Servidores e folha do mês por secretaria, nas duas cidades."""
    pau_n, pau_v = Counter(), defaultdict(float)
    with gzip.open(RAIZ / f"data/raw/servidores_{ano}.csv.gz", "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            v = float(r["vencimentos"] or 0)
            if (r["mes"] == "12" and r["tipo_folha"] == "9" and v > 0
                    and "Inativo" not in r["cargo"] and "Pensionista" not in r["cargo"]):
                pau_n[norm(r["secretaria"])] += 1
                pau_v[norm(r["secretaria"])] += v
    cam_n, cam_v = Counter(), defaultdict(float)
    caminho = RAIZ / f"data/raw/servidores_campinas_{ano}_12.csv.gz"
    if caminho.exists():
        with gzip.open(caminho, "rt", encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter=";"):
                v = float(r["bruto_recorrente"] or r["vencimentos"] or 0)
                if v > 0:
                    cam_n[norm(r["secretaria"])] += 1
                    cam_v[norm(r["secretaria"])] += v
    return (pau_n, pau_v), (cam_n, cam_v)


def por_habitante(ano=2025):
    """Servidores por mil habitantes, por área. Separa 'paga mais' de 'tem mais gente':
    são duas perguntas diferentes e o total gasto é o produto das duas."""
    painel = json.loads((RAIZ / "data/painel.json").read_text(encoding="utf-8"))
    pop_pau = painel["despesas"][str(ano)]["populacao"]
    pop_cam = POPULACAO["campinas"]
    (pau_n, pau_v), (cam_n, cam_v) = contar_por_secretaria(ano)
    if not cam_n:
        return {}
    def soma(c, chaves):
        return sum(c.get(k, 0) for k in chaves)
    areas = []
    for nome, (kp, kc) in AREAS.items():
        a, b = soma(pau_n, kp), soma(cam_n, kc)
        if not a or not b:
            continue
        ra, rb = 1000 * a / pop_pau, 1000 * b / pop_cam
        areas.append({"area": nome, "paulinia_n": a, "campinas_n": b,
                      "paulinia": round(ra, 2), "campinas": round(rb, 2),
                      "vezes": round(ra / rb, 2)})
    areas.sort(key=lambda x: -x["vezes"])
    ta, tb = sum(pau_n.values()), sum(cam_n.values())
    ra, rb = 1000 * ta / pop_pau, 1000 * tb / pop_cam
    fa, fb = sum(pau_v.values()) / pop_pau, sum(cam_v.values()) / pop_cam
    return {"populacao": {"paulinia": pop_pau, "campinas": pop_cam},
            "areas": areas,
            "total": {"paulinia_n": ta, "campinas_n": tb,
                      "paulinia": round(ra, 2), "campinas": round(rb, 2),
                      "vezes": round(ra / rb, 2)},
            "folha_por_habitante": {"paulinia": round(fa, 2), "campinas": round(fb, 2),
                                    "vezes": round(fa / fb, 2),
                                    "vezes_efetivo": round(ra / rb, 2),
                                    "vezes_salario": round((fa / fb) / (ra / rb), 2)}}


def brl(v):
    return ("R$ " + f"{v:,.0f}").replace(",", ".")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listar", action="store_true",
                    help="mostra os cargos grandes que ainda não estão pareados")
    ap.add_argument("--ano", type=int, default=2025, help="ano do relatório na tela")
    ap.add_argument("--incluir-baixa", action="store_true",
                    help="grava no JSON também os pares de confiança baixa (fora por padrão, "
                         "para não vazarem para o painel sem revisão)")
    args = ap.parse_args()

    dados = {"paulinia": {}, "campinas": {}}
    for ano in ANOS:
        dados["paulinia"][ano] = ler_paulinia(ano)
        dados["campinas"][ano] = ler_cidade("campinas", ano)

    if args.listar:
        def ja_pareado(cargo, chaves):
            for c in chaves:
                if c.startswith("__PREFIXO__"):
                    if cargo.startswith(c.replace("__PREFIXO__", "")):
                        return True
                elif cargo == c:
                    return True
            return False

        pareados_p = [c for p in PARES for c in p["paulinia"]]
        pareados_c = [c for p in PARES for c in p["campinas"]]
        for cidade in ("paulinia", "campinas"):
            d = dados[cidade].get(args.ano)
            if not d:
                continue
            print(f"\n{cidade.upper()} {args.ano} — cargos com 50+ servidores ainda sem par:")
            for cargo, v in sorted(d.items(), key=lambda x: -len(x[1])):
                if len(v) < 50:
                    break
                ja = ja_pareado(cargo, pareados_p if cidade == "paulinia" else pareados_c)
                if not ja:
                    print(f"   {len(v):5d}  {brl(statistics.median(v)):>10s}  {cargo}")
        return

    saida = {"gerado_em": date.today().isoformat(), "anos": ANOS,
             "tabela_vs_folha": tabela_vs_folha(),
             "decomposicao": decomposicao(),
             "jornada_padrao": jornada_padrao(),
             "por_habitante": por_habitante(), "pares": []}

    print(f"Paulínia × Campinas — dezembro/{args.ano}, mediana do bruto mensal")
    print("(Paulínia: folha mensal, ativos. Campinas: bruto sem verbas de uma vez só.)\n")
    print(f"{'cargo':44s} {'Paulínia':>16s} {'Campinas':>16s}   dif  conf")
    print("-" * 96)

    for par in PARES:
        item = {k: par[k] for k in ("nome", "confianca", "obs", "jornada")}
        if par.get("desde"):
            item["desde"] = par["desde"]
        item["cargos"] = {"paulinia": par["paulinia"], "campinas": par["campinas"]}
        item["dados"] = {}
        for ano in ANOS:
            if ano < par.get("desde", 0):
                continue
            dp, dc = dados["paulinia"].get(ano), dados["campinas"].get(ano)
            if not dp or not dc:
                continue
            rp, rc = resumo(juntar(dp, par["paulinia"])), resumo(juntar(dc, par["campinas"]))
            if not rp or not rc:
                continue
            item["dados"][ano] = {
                "paulinia": rp, "campinas": rc,
                "dif_pct": round(100 * (rp["mediana"] - rc["mediana"]) / rc["mediana"], 1),
            }
        if par["confianca"] != "baixa" or args.incluir_baixa:
            saida["pares"].append(item)

        d = item["dados"].get(args.ano)
        if not d:
            print(f"{par['nome'][:44]:44s} {'sem dados no ano':>33s}")
            continue
        print(f"{par['nome'][:44]:44s} "
              f"{brl(d['paulinia']['mediana']):>9s} ({d['paulinia']['n']:4d}) "
              f"{brl(d['campinas']['mediana']):>9s} ({d['campinas']['n']:4d}) "
              f" {d['dif_pct']:+5.0f}%  {par['confianca']}")

    destino = RAIZ / "data/comparativo_cargos.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> {destino.relative_to(RAIZ)}")
    baixa = [p["nome"] for p in PARES if p["confianca"] == "baixa"]
    if baixa:
        estado = "incluídos" if args.incluir_baixa else "FORA do JSON"
        print(f"\nConfiança baixa ({estado}): {', '.join(baixa)}")


if __name__ == "__main__":
    main()
