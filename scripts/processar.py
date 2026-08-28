#!/usr/bin/env python3
"""
Lê os CSVs filtrados de Paulínia em data/raw/ e gera data/painel.json com os
agregados que alimentam o painel (painel/index.html).

Uso:
    python scripts/processar.py
"""
import csv
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "raw"
SAIDA = BASE / "data" / "painel.json"

# População (IBGE). 2023 usa o Censo 2022 (o IBGE não divulgou estimativa em 2023).
POPULACAO = {2023: 110_537, 2024: 115_690, 2025: 116_674}

# Tradução das funções de governo para linguagem simples
FUNCOES = {
    "SAÚDE": ("Saúde", "Hospital, UBS, remédios, exames e profissionais de saúde", "🏥"),
    "EDUCAÇÃO": ("Educação", "Escolas, creches, professores, merenda e transporte escolar", "🎓"),
    "ADMINISTRAÇÃO": ("Administração", "Funcionamento da prefeitura, secretarias e serviços internos", "🏛️"),
    "PREVIDÊNCIA SOCIAL": ("Aposentadorias", "Aposentadorias e pensões dos servidores municipais", "👴"),
    "URBANISMO": ("Cidade", "Ruas, iluminação, limpeza urbana, praças e obras viárias", "🏙️"),
    "ENCARGOS ESPECIAIS": ("Dívidas e precatórios", "Pagamento de dívidas, precatórios e sentenças judiciais", "⚖️"),
    "ASSISTÊNCIA SOCIAL": ("Assistência social", "CRAS, apoio a famílias vulneráveis, idosos e crianças", "🤝"),
    "SEGURANÇA PÚBLICA": ("Segurança", "Guarda Municipal, monitoramento e defesa civil", "🚨"),
    "DESPORTO E LAZER": ("Esporte e lazer", "Ginásios, campos, eventos e escolinhas esportivas", "⚽"),
    "TRANSPORTE": ("Transporte", "Transporte coletivo, trânsito e mobilidade", "🚌"),
    "CULTURA": ("Cultura", "Teatro, eventos culturais, bibliotecas e patrimônio", "🎭"),
    "LEGISLATIVA": ("Câmara Municipal", "Funcionamento da Câmara e dos vereadores", "🗳️"),
    "GESTÃO AMBIENTAL": ("Meio ambiente", "Parques, arborização, fiscalização ambiental", "🌳"),
    "HABITAÇÃO": ("Habitação", "Programas habitacionais e regularização", "🏠"),
    "ESSENCIAL À JUSTIÇA": ("Procuradoria", "Defesa jurídica do município", "📜"),
    "COMÉRCIO E SERVIÇOS": ("Comércio e turismo", "Apoio ao comércio, turismo e desenvolvimento econômico", "🛍️"),
    "DIREITOS DA CIDADANIA": ("Cidadania", "Direitos da mulher, do consumidor, da pessoa com deficiência", "🧑‍🤝‍🧑"),
    "SANEAMENTO": ("Saneamento", "Água, esgoto e drenagem", "💧"),
    "CIÊNCIA E TECNOLOGIA": ("Ciência e tecnologia", "Inovação e tecnologia", "🔬"),
    "TRABALHO": ("Trabalho", "Qualificação profissional e emprego", "👷"),
    "AGRICULTURA": ("Agricultura", "Apoio ao produtor rural", "🌾"),
    "INDÚSTRIA": ("Indústria", "Apoio à indústria", "🏭"),
    "COMUNICAÇÕES": ("Comunicação", "Comunicação institucional", "📣"),
    "ENERGIA": ("Energia", "Energia", "⚡"),
}

NATUREZA = {
    "31": ("Pessoal", "Salários, encargos e aposentadorias dos servidores"),
    "33": ("Custeio", "Contratos, serviços, materiais, medicamentos, terceirizados"),
    "44": ("Investimentos", "Obras, equipamentos e compra de imóveis"),
    "45": ("Investimentos", "Inversões financeiras"),
    "32": ("Dívida", "Juros e amortização de dívidas"),
    "46": ("Dívida", "Juros e amortização de dívidas"),
}

# Composição da folha (elementos 31xx). Ordem importa: o primeiro prefixo que casar vence.
FOLHA = [
    ("319001", "Aposentadorias e pensões", "Proventos, 13º e pensões de aposentados e pensionistas (Paulínia Previ)"),
    ("319003", "Aposentadorias e pensões", "Pensões"),
    ("31901175", "Prefeito, vice, secretários e vereadores", "Subsídios dos agentes políticos"),
    ("31901101", "Salário-base", "Vencimentos dos servidores efetivos e comissionados"),
    ("31900411", "Contratos temporários", "Salários de contratados por tempo determinado"),
    ("319004", "Contratos temporários", "13º, férias e encargos dos temporários"),
    ("31901644", "Horas extras", "Serviços extraordinários"),
    ("31901143", "13º salário e férias", ""),
    ("31901144", "13º salário e férias", ""),
    ("31901145", "13º salário e férias", ""),
    ("31901137", "Gratificações e adicionais", "Tempo de serviço, funções, abono de permanência, licenças"),
    ("31901133", "Gratificações e adicionais", ""),
    ("31901107", "Gratificações e adicionais", ""),
    ("31901699", "Gratificações e adicionais", "Outras despesas variáveis"),
    ("319011", "Gratificações e adicionais", ""),
    ("319113", "Encargos (previdência e FGTS)", "Parte patronal da previdência municipal, INSS e FGTS"),
    ("319013", "Encargos (previdência e FGTS)", ""),
    ("319007", "Encargos (previdência e FGTS)", ""),
    ("319091", "Decisões judiciais e indenizações", "Precatórios, sentenças e indenizações trabalhistas"),
    ("319094", "Decisões judiciais e indenizações", ""),
    ("3171", "Pessoal de consórcios", "Rateio de pessoal dos consórcios públicos (ex.: CISMETRO)"),
]
FOLHA_ATIVOS_EXCLUI = {"Aposentadorias e pensões", "Decisões judiciais e indenizações", "Pessoal de consórcios"}

# Número de servidores por área (opcional). Preencha quando tiver a lista de servidores da prefeitura
# (portal SMARAPD -> Pessoal). Com isso o painel calcula o custo médio mensal por servidor.
# Ex.: SERVIDORES = {2025: {"Educação": 2100, "Saúde": 1800, "_total": 5500}}
SERVIDORES = {}


def grupo_folha(cod):
    for prefixo, nome, _ in FOLHA:
        if cod.startswith(prefixo):
            return nome
    return "Outros"


# Grupos de receita (prefixo do código de 8 dígitos em ds_d3 / ds_tipo)
RECEITAS = [
    ("172150", "ICMS (repasse do Estado)", "Parte do ICMS gerado no município – reflete a refinaria e as indústrias de Paulínia"),
    ("172151", "IPVA (repasse do Estado)", "Parte do IPVA dos veículos de Paulínia"),
    ("172152", "IPI (repasse via Estado)", "Cota-parte do IPI exportação"),
    ("1721", "Outros repasses do Estado", "Demais participações na receita estadual"),
    ("1722", "Royalties e compensações (Estado)", "Compensações financeiras repassadas pelo Estado"),
    ("1712", "Royalties e compensações (União)", "Compensações pela exploração de petróleo e recursos naturais"),
    ("1711", "FPM e repasses da União", "Fundo de Participação dos Municípios e outros repasses federais"),
    ("1713", "SUS (União)", "Recursos federais para a saúde"),
    ("1723", "SUS (Estado)", "Recursos estaduais para a saúde"),
    ("1714", "FNDE (União)", "Recursos federais para a educação"),
    ("1751", "FUNDEB", "Fundo da educação básica"),
    ("1715", "FUNDEB", "Complementação da União ao FUNDEB"),
    ("17", "Outros repasses", "Convênios e outras transferências"),
    ("111250", "IPTU", "Imposto sobre imóveis urbanos"),
    ("111253", "ITBI", "Imposto pago na compra e venda de imóveis"),
    ("1112", "Outros impostos sobre patrimônio", "Impostos sobre o patrimônio"),
    ("1113", "Imposto de Renda retido", "IR retido na fonte dos salários dos servidores e de fornecedores – fica com o município"),
    ("1114", "ISS", "Imposto sobre serviços prestados na cidade"),
    ("199903", "Compensação previdenciária", "Acertos entre o INSS e a previdência municipal"),
    ("112", "Taxas", "Taxas de serviços e fiscalização"),
    ("11", "Outros impostos", "Outros impostos e contribuições de melhoria"),
    ("1241", "Iluminação pública (CIP)", "Contribuição cobrada na conta de luz"),
    ("12", "Contribuições previdenciárias", "Contribuições dos servidores para a previdência municipal"),
    ("13", "Rendimentos financeiros", "Juros de aplicações e aluguéis"),
    ("19", "Multas, restituições e outras", "Multas, indenizações e outras receitas"),
    ("2", "Receitas de capital", "Venda de bens e transferências para obras"),
]

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def val(s):
    return float(s.replace(".", "").replace(",", "."))


def achar(nome):
    """Aceita tanto .csv quanto .csv.gz em data/raw/."""
    for cand in (RAW / nome, RAW / (nome + ".gz")):
        if cand.exists():
            return cand
    return None


def ler(caminho):
    abrir = gzip.open if str(caminho).endswith(".gz") else open
    with abrir(caminho, mode="rt", encoding="latin-1", newline="") as f:
        yield from csv.DictReader(f, delimiter=";")


def codigo(s):
    m = re.match(r"\s*(\d+)", s or "")
    return m.group(1) if m else ""


def rotulo_funcao(nome):
    nome = (nome or "").strip().upper()
    if nome in FUNCOES:
        return FUNCOES[nome]
    return (nome.title(), "", "📌")


def grupo_receita(row):
    cod = codigo(row["ds_tipo"]) or codigo(row["ds_d3"])
    for prefixo, nome, desc in RECEITAS:
        if cod.startswith(prefixo):
            return nome, desc
    return "Outras receitas", ""


def r2(x):
    return round(x, 2)


def processar_despesas(ano):
    caminho = achar(f"despesas_paulinia_{ano}.csv")
    if not caminho:
        return None
    totais = defaultdict(float)
    por_funcao = defaultdict(float)
    por_funcao_empenhado = defaultdict(float)
    por_subfuncao = defaultdict(lambda: defaultdict(float))
    por_mes = defaultdict(lambda: defaultdict(float))  # tipo -> mes -> valor
    por_natureza = defaultdict(float)
    por_orgao = defaultdict(float)
    por_modalidade = defaultdict(float)
    por_fonte = defaultdict(float)
    fornecedores = defaultdict(lambda: {"nome": "", "id": "", "tipo": "", "pago": 0.0, "empenhos": set(),
                                        "funcoes": defaultdict(float), "pessoal": 0.0})
    folha_grupo = defaultdict(float)
    folha_func = defaultdict(lambda: defaultdict(float))
    folha_orgao = defaultdict(lambda: defaultdict(float))
    folha_mes = defaultdict(float)          # ativos, por mês
    folha_mes_grupo = defaultdict(lambda: defaultdict(float))
    n = 0
    for r in ler(caminho):
        n += 1
        v = val(r["vl_despesa"])
        tipo = r["tp_despesa"]
        mes = int(r["mes_referencia"])
        totais[tipo] += v
        por_mes[tipo][mes] += v
        func = rotulo_funcao(r["ds_funcao_governo"])[0]
        if tipo == "Empenhado":
            por_funcao_empenhado[func] += v
        elif tipo == "Anulação":
            por_funcao_empenhado[func] -= v
        if tipo != "Valor Pago":
            continue
        por_funcao[func] += v
        por_subfuncao[func][r["ds_subfuncao_governo"].strip().capitalize()] += v
        elem = codigo(r["ds_elemento"])
        por_natureza[NATUREZA.get(elem[:2], ("Outros", ""))[0]] += v
        por_orgao[r["ds_orgao"].strip().title()] += v
        por_modalidade[r["ds_modalidade_lic"].strip()] += v
        por_fonte[r["ds_fonte_recurso"].strip()] += v
        ident = r["nr_identificador_despesa"].strip()
        nome = " ".join(r["ds_despesa"].split())
        chave = ident or nome
        f = fornecedores[chave]
        f["nome"] = nome
        f["id"] = ident
        f["tipo"] = r["tp_identificador_despesa"].strip()
        f["pago"] += v
        f["empenhos"].add(r["nr_empenho"].strip())
        f["funcoes"][func] += v
        if elem.startswith("31"):
            f["pessoal"] += v
            g = grupo_folha(elem)
            folha_grupo[g] += v
            folha_func[func][g] += v
            folha_orgao[r["ds_orgao"].strip().title()][g] += v
            folha_mes_grupo[g][mes] += v
            if g not in FOLHA_ATIVOS_EXCLUI:
                folha_mes[mes] += v

    pago = totais["Valor Pago"]
    pop = POPULACAO.get(ano)

    def lista(d, empenhado=None):
        out = []
        for k, v in sorted(d.items(), key=lambda kv: -kv[1]):
            item = {"nome": k, "valor": r2(v), "pct": r2(100 * v / pago) if pago else 0}
            if pop:
                item["por_habitante"] = r2(v / pop)
            if empenhado is not None:
                item["empenhado"] = r2(empenhado.get(k, 0))
            out.append(item)
        return out

    funcoes_out = []
    for item in lista(por_funcao, por_funcao_empenhado):
        nome = item["nome"]
        chave = next((k for k, v in FUNCOES.items() if v[0] == nome), None)
        desc, icone = (FUNCOES[chave][1], FUNCOES[chave][2]) if chave else ("", "📌")
        item["descricao"] = desc
        item["icone"] = icone
        item["subfuncoes"] = [
            {"nome": s, "valor": r2(v)}
            for s, v in sorted(por_subfuncao[nome].items(), key=lambda kv: -kv[1])[:8]
        ]
        funcoes_out.append(item)

    # ranking de fornecedores (exclui folha de pagamento e repasses internos)
    internos = ("MUNICIPIO DE PAULINIA", "INSTITUTO DE PREVIDENCIA DOS FUNCIONARIOS PUBLICOS",
                "PAULINIA PREVI", "CAMARA MUNICIPAL DE PAULINIA")
    ranking = []
    for f in fornecedores.values():
        if f["nome"].upper().startswith(internos):
            continue
        externo = f["pago"] - f["pessoal"]
        if externo <= 0:
            continue
        func_principal = max(f["funcoes"].items(), key=lambda kv: kv[1])[0]
        ranking.append({
            "nome": f["nome"], "id": f["id"], "tipo": "PJ" if "JUR" in f["tipo"].upper() else ("PF" if "F" in f["tipo"].upper() else f["tipo"]),
            "pago": r2(externo), "empenhos": len(f["empenhos"]), "area": func_principal,
        })
    ranking.sort(key=lambda x: -x["pago"])
    folha = sum(f["pessoal"] for f in fornecedores.values())

    folha_total = sum(folha_grupo.values())
    folha_ativos = sum(v for g, v in folha_grupo.items() if g not in FOLHA_ATIVOS_EXCLUI)
    ordem_grupos = []
    for _, nome, _ in FOLHA:
        if nome not in ordem_grupos:
            ordem_grupos.append(nome)
    ordem_grupos.append("Outros")
    desc_grupos = {}
    for _, nome, d in FOLHA:
        if d and nome not in desc_grupos:
            desc_grupos[nome] = d
    serv = SERVIDORES.get(ano, {})

    def func_folha(fn):
        d = folha_func[fn]
        tot = sum(d.values())
        ativos = sum(v for g, v in d.items() if g not in FOLHA_ATIVOS_EXCLUI)
        item = {"nome": fn, "total": r2(tot), "ativos": r2(ativos),
                "grupos": {g: r2(d[g]) for g in ordem_grupos if d.get(g)}}
        if serv.get(fn):
            item["servidores"] = serv[fn]
            item["custo_medio_mensal"] = r2(ativos / serv[fn] / 12)
        return item

    folha = {
        "total": r2(folha_total),
        "ativos": r2(folha_ativos),
        "pct_do_gasto": r2(100 * folha_total / pago) if pago else 0,
        "por_habitante": r2(folha_total / pop) if pop else None,
        "salario_base_mes": r2(folha_grupo.get("Salário-base", 0) / max(1, len({m for m in folha_mes}))),
        "grupos": [{"nome": g, "descricao": desc_grupos.get(g, ""), "valor": r2(folha_grupo[g]),
                    "pct": r2(100 * folha_grupo[g] / folha_total) if folha_total else 0}
                   for g in ordem_grupos if folha_grupo.get(g)],
        "por_funcao": sorted([func_folha(fn) for fn in folha_func], key=lambda x: -x["total"]),
        "por_orgao": [{"nome": o, "total": r2(sum(d.values())),
                       "grupos": {g: r2(d[g]) for g in ordem_grupos if d.get(g)}}
                      for o, d in sorted(folha_orgao.items(), key=lambda kv: -sum(kv[1].values()))],
        "por_mes_ativos": [r2(folha_mes.get(m, 0)) for m in range(1, 13)],
        "por_mes_grupos": {g: [r2(folha_mes_grupo[g].get(m, 0)) for m in range(1, 13)] for g in ordem_grupos if folha_grupo.get(g)},
        "servidores_total": serv.get("_total"),
        "custo_medio_mensal": r2(folha_ativos / serv["_total"] / 12) if serv.get("_total") else None,
    }

    meses = sorted({m for t in por_mes.values() for m in t})
    return {
        "folha": folha,
        "ano": ano,
        "populacao": pop,
        "registros": n,
        "meses_disponiveis": len(meses),
        "totais": {
            "empenhado": r2(totais["Empenhado"]),
            "anulado": r2(totais["Anulação"]),
            "empenhado_liquido": r2(totais["Empenhado"] - totais["Anulação"]),
            "liquidado": r2(totais["Valor Liquidado"]),
            "pago": r2(pago),
            "pago_por_habitante": r2(pago / pop) if pop else None,
            "folha_pessoal": r2(folha_total),
        },
        "por_mes": {
            "pago": [r2(por_mes["Valor Pago"].get(m, 0)) for m in range(1, 13)],
            "empenhado": [r2(por_mes["Empenhado"].get(m, 0) - por_mes["Anulação"].get(m, 0)) for m in range(1, 13)],
        },
        "por_funcao": funcoes_out,
        "por_natureza": lista(por_natureza),
        "por_orgao": lista(por_orgao),
        "por_modalidade": lista(por_modalidade),
        "por_fonte": lista(por_fonte),
        "fornecedores_top": ranking[:100],
        "fornecedores_todos": [{"n": x["nome"], "i": x["id"], "v": x["pago"], "a": x["area"]} for x in ranking],
        "total_fornecedores": len(ranking),
    }


def processar_receitas(ano):
    caminho = achar(f"receitas_paulinia_{ano}.csv")
    if not caminho:
        return None
    total = 0.0
    por_grupo = defaultdict(float)
    desc_grupo = {}
    por_mes = defaultdict(float)
    por_orgao = defaultdict(float)
    intra = 0.0
    for r in ler(caminho):
        v = val(r["vl_arrecadacao"])
        if codigo(r["ds_categoria"]).startswith("7"):
            intra += v  # receitas intra-orçamentárias (dinheiro que circula entre órgãos do próprio município)
            continue
        total += v
        g, d = grupo_receita(r)
        por_grupo[g] += v
        desc_grupo[g] = d
        por_mes[int(r["mes_referencia"])] += v
        por_orgao[r["ds_orgao"].strip().title()] += v
    pop = POPULACAO.get(ano)
    grupos = [
        {"nome": g, "descricao": desc_grupo[g], "valor": r2(v), "pct": r2(100 * v / total) if total else 0,
         "por_habitante": r2(v / pop) if pop else None}
        for g, v in sorted(por_grupo.items(), key=lambda kv: -kv[1])
    ]
    return {
        "ano": ano,
        "total": r2(total),
        "intra_orcamentaria_excluida": r2(intra),
        "total_por_habitante": r2(total / pop) if pop else None,
        "por_grupo": grupos,
        "por_mes": [r2(por_mes.get(m, 0)) for m in range(1, 13)],
        "por_orgao": [{"nome": k, "valor": r2(v)} for k, v in sorted(por_orgao.items(), key=lambda kv: -kv[1])],
    }


MODALIDADE_CURTA = {
    "OUTROS/NÃO APLICÁVEL": "", "PREGÃO ELETRÔNICO": "Pregão eletrônico", "PREGÃO PRESENCIAL": "Pregão presencial",
    "INEXIGÍVEL": "Inexigibilidade", "DISPENSA DE LICITAÇÃO": "Dispensa", "CONCORRÊNCIA": "Concorrência",
    "TOMADA DE PREÇOS": "Tomada de preços", "CONCURSO": "Concurso", "CONVITE": "Convite", "LEILÃO": "Leilão",
}


def rotulo_elemento(s):
    """'33903009 - MATERIAL FARMACOLÓGICO' -> ('33903009', 'Material farmacológico')."""
    cod = codigo(s)
    desc = re.sub(r"^\s*\d+\s*-\s*", "", s or "").strip()
    desc = desc[:1].upper() + desc[1:].lower() if desc else cod
    desc = re.sub(r"\b(rpps|rgps|inss|fgts|ofss|pis|pasep|cip|sus|fundeb|pj|pf|tic|ti|gps|pnae|pnate)\b",
                  lambda m: m.group(1).upper(), desc)
    return cod, desc


def gerar_detalhe(ano):
    """Gera data/detalhe_{ano}.js: hierarquia área -> subfunção -> tipo de gasto (elemento)
    -> fornecedor -> empenhos, só com valores pagos. Carregado sob demanda pelo painel."""
    caminho = achar(f"despesas_paulinia_{ano}.csv")
    if not caminho:
        return None
    # arvore[func][sub][elem][forn] = {"t": total, "e": {nr_empenho: [data, valor, historico, modalidade, orgao]}}
    arvore = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"t": 0.0, "e": {}}))))
    nomes_forn = {}
    grupo_elem = {}
    for r in ler(caminho):
        if r["tp_despesa"] != "Valor Pago":
            continue
        v = val(r["vl_despesa"])
        func = rotulo_funcao(r["ds_funcao_governo"])[0]
        sub = r["ds_subfuncao_governo"].strip().capitalize()
        cod, elem = rotulo_elemento(r["ds_elemento"])
        grupo_elem[elem] = NATUREZA.get(cod[:2], ("Outros", ""))[0]
        ident = r["nr_identificador_despesa"].strip()
        nome = " ".join(r["ds_despesa"].split())
        chave = ident or nome
        nomes_forn[chave] = (nome, ident)
        no = arvore[func][sub][elem][chave]
        no["t"] += v
        nr = r["nr_empenho"].strip()
        emp = no["e"].get(nr)
        hist = " ".join(r["historico_despesa"].split())[:300]
        if emp:
            emp[1] += v
            if not emp[2] and hist:
                emp[2] = hist
        else:
            no["e"][nr] = [r["dt_emissao_despesa"], v, hist, MODALIDADE_CURTA.get(r["ds_modalidade_lic"].strip(), r["ds_modalidade_lic"].strip().capitalize()),
                           r["ds_orgao"].strip().title()]

    def forn_out(d):
        out = []
        for chave, no in sorted(d.items(), key=lambda kv: -kv[1]["t"]):
            nome, ident = nomes_forn[chave]
            emps = sorted(no["e"].items(), key=lambda kv: -kv[1][1])
            out.append({"n": nome, "i": ident, "t": r2(no["t"]), "q": len(emps),
                        "e": [[nr, e[0], r2(e[1]), e[2], e[3], e[4]] for nr, e in emps]})
        return out

    saida = {}
    for func, subs in arvore.items():
        fs = {}
        for sub, elems in subs.items():
            es = {}
            for elem, forns in elems.items():
                fo = forn_out(forns)
                es[elem] = {"t": r2(sum(f["t"] for f in fo)), "g": grupo_elem[elem], "f": fo}
            fs[sub] = {"t": r2(sum(e["t"] for e in es.values())),
                       "e": dict(sorted(es.items(), key=lambda kv: -kv[1]["t"]))}
        saida[func] = {"t": r2(sum(s["t"] for s in fs.values())),
                       "s": dict(sorted(fs.items(), key=lambda kv: -kv[1]["t"]))}
    saida = dict(sorted(saida.items(), key=lambda kv: -kv[1]["t"]))
    destino = BASE / "data" / f"detalhe_{ano}.js"
    js = json.dumps(saida, ensure_ascii=False, separators=(",", ":")).replace("</script", "<\\/script")
    destino.write_text(f"window.DETALHE=window.DETALHE||{{}};window.DETALHE[{ano}]={js};", encoding="utf-8")
    return destino


# ---------------------------------------------------------------------------
# Servidores (portal da prefeitura / SMARAPD) — data/raw/servidores_{ano}.csv.gz
# ---------------------------------------------------------------------------
TIPO_FOLHA = {"9": "Folha mensal (bruto, já inclui o adiantamento)", "8": "Adiantamento (incluído na mensal)", "3": "Férias (folha de janeiro)", "5": "Abono de férias (1/3)",
              "6": "13º salário", "1": "Complementar", "10": "Rescisão", "14": "Complementar", "2": "Outros"}
APOSENTADOS = ("Inativo", "Pensionista")


def vinculo(cargo):
    c = cargo or ""
    if c.startswith(APOSENTADOS):
        return "Aposentados e pensionistas"
    if "(CTD)" in c:
        return "Temporários"
    if "LC 6" in c or c.startswith("Guarda Civil") or c.startswith("Guarda Patrimonial"):
        return "Efetivos"
    if c.startswith(("Prefeito", "Vice Prefeito", "Secretario", "Conselheiro Tutelar")):
        return "Agentes políticos e conselheiros"
    return "Comissionados"


def cargo_limpo(cargo):
    c = re.sub(r"\s*-\s*LC \d+/\d{4}$", "", cargo or "").strip()
    c = re.sub(r"\s*\(CTD\)$", "", c).strip()
    return c


def secretaria_curta(s):
    s = (s or "").replace("Secretaria Municipal de ", "").replace("Secretaria Municipal da ", "").strip()
    return {"Encargos Gerais do Município": "Encargos gerais (aposentados)",
            "Chefia de Gabinete do Prefeito": "Gabinete do Prefeito",
            "Procuradoria Geral do Municipio": "Procuradoria"}.get(s, s)


def processar_servidores(ano):
    caminho = achar(f"servidores_{ano}.csv")
    if not caminho:
        return None
    linhas = []
    with (gzip.open if str(caminho).endswith(".gz") else open)(caminho, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            r["v"] = float(r["vencimentos"] or 0)
            r["l"] = float(r["liquido"] or 0)
            r["mes"] = int(r["mes"] or 0)
            linhas.append(r)
    # mês de referência: último mês com folha mensal (tipo 9) "completa"
    por_mes9 = defaultdict(int)
    for r in linhas:
        if r["tipo_folha"] == "9":
            por_mes9[r["mes"]] += 1
    maximo = max(por_mes9.values())
    mes_ref = max(m for m, n in por_mes9.items() if n >= 0.9 * maximo)

    ref = {}  # matricula -> registro da folha mensal do mês de referência (só ativos)
    adiant = defaultdict(float)
    for r in linhas:
        if r["tipo_folha"] == "9" and r["mes"] == mes_ref:
            ref[r["matricula"]] = r
        elif r["tipo_folha"] == "8" and r["mes"] == mes_ref:
            adiant[r["matricula"]] += r["l"]
    for m, r in ref.items():  # líquido efetivamente recebido no mês = folha mensal + adiantamento
        r["l"] = r["l"] + adiant.get(m, 0)
    ativos = {m: r for m, r in ref.items() if vinculo(r["cargo"]) != "Aposentados e pensionistas"}

    # Bruto no ano por matrícula. O adiantamento (tipo 8) já está dentro do bruto da folha mensal
    # (tipo 9) e é descontado dela, então NÃO entra na soma — senão conta duas vezes (~12%).
    total_ano = defaultdict(float)
    cargo_de = {}
    sec_de = {}
    for r in linhas:
        if r["tipo_folha"] != "8":
            total_ano[r["matricula"]] += r["v"]
        cargo_de[r["matricula"]] = r["cargo"]
        sec_de[r["matricula"]] = r["secretaria"]
    bruto_ano_ativos = sum(v for m, v in total_ano.items() if vinculo(cargo_de[m]) != "Aposentados e pensionistas")
    bruto_ano_apos = sum(v for m, v in total_ano.items() if vinculo(cargo_de[m]) == "Aposentados e pensionistas")

    def grupo(chave):
        g = defaultdict(lambda: {"n": 0, "mensal": 0.0, "liq": 0.0, "anual": 0.0, "valores": []})
        for m, r in ativos.items():
            k = chave(r)
            g[k]["n"] += 1
            g[k]["mensal"] += r["v"]
            g[k]["liq"] += r["l"]
            g[k]["anual"] += total_ano[m]
            g[k]["valores"].append(r["v"])
        out = []
        for k, d in g.items():
            vals = sorted(d["valores"])
            out.append({"nome": k, "n": d["n"], "media_mensal": r2(d["mensal"] / d["n"]), "media_liquida": r2(d["liq"] / d["n"]),
                        "mediana_mensal": r2(vals[len(vals) // 2]), "maior_mensal": r2(vals[-1]), "menor_mensal": r2(vals[0]),
                        "custo_medio_mensal": r2(d["anual"] / d["n"] / 12), "total_ano": r2(d["anual"])})
        return sorted(out, key=lambda x: -x["n"])

    por_vinculo = grupo(lambda r: vinculo(r["cargo"]))
    por_secretaria = grupo(lambda r: secretaria_curta(r["secretaria"]))
    por_cargo = [c for c in grupo(lambda r: cargo_limpo(r["cargo"])) if c["n"] >= 3]
    # cargo x secretaria (top) para o detalhe
    cargo_sec = defaultdict(lambda: defaultdict(list))
    for r in ativos.values():
        cargo_sec[secretaria_curta(r["secretaria"])][cargo_limpo(r["cargo"])].append(r["v"])
    for sec in por_secretaria:
        top = sorted(cargo_sec[sec["nome"]].items(), key=lambda kv: -len(kv[1]))[:8]
        sec["cargos"] = [{"nome": k, "n": len(v), "media_mensal": r2(sum(v) / len(v))} for k, v in top]

    faixas = [(0, 3000, "até R$ 3 mil"), (3000, 5000, "R$ 3–5 mil"), (5000, 8000, "R$ 5–8 mil"),
              (8000, 12000, "R$ 8–12 mil"), (12000, 16000, "R$ 12–16 mil"), (16000, 20000, "R$ 16–20 mil"),
              (20000, 30000, "R$ 20–30 mil"), (30000, 1e12, "acima de R$ 30 mil")]
    dist = [{"faixa": lab, "n": sum(1 for r in ativos.values() if lo <= r["v"] < hi)} for lo, hi, lab in faixas]
    vals = sorted(r["v"] for r in ativos.values())
    liqs = sorted(r["l"] for r in ativos.values())
    n = len(vals)

    admitidos = {r["matricula"] for r in linhas if r["data_admissao"].startswith(str(ano))}
    desligados = {r["matricula"] for r in linhas if r["data_rescisao"].startswith(str(ano))}

    meses_completos = sorted(m for m, c in por_mes9.items() if c >= 0.9 * maximo)
    folha_mensal = {m: 0.0 for m in range(1, 13)}
    for r in linhas:
        if r["tipo_folha"] != "8" and vinculo(r["cargo"]) != "Aposentados e pensionistas":
            folha_mensal[r["mes"]] = folha_mensal.get(r["mes"], 0) + r["v"]

    return {
        "fonte": "Portal da Transparência da Prefeitura de Paulínia (SMARAPD) – Pagamentos a Servidores",
        "mes_referencia": mes_ref,
        "meses_com_folha_mensal": meses_completos,
        "servidores_ativos": n,
        "aposentados_na_folha": len(ref) - n,
        "admitidos_no_ano": len(admitidos),
        "desligados_no_ano": len(desligados),
        "bruto_ano_ativos": r2(bruto_ano_ativos),
        "bruto_ano_aposentados": r2(bruto_ano_apos),
        "media_mensal": r2(sum(vals) / n) if n else 0,
        "mediana_mensal": r2(vals[n // 2]) if n else 0,
        "mediana_liquida": r2(liqs[n // 2]) if n else 0,
        "media_liquida": r2(sum(liqs) / n) if n else 0,
        "p90_mensal": r2(vals[int(n * 0.9)]) if n else 0,
        "custo_medio_mensal": r2(bruto_ano_ativos / n / 12) if n else 0,
        "por_vinculo": por_vinculo,
        "por_secretaria": por_secretaria,
        "por_cargo": por_cargo,
        "distribuicao": dist,
        "folha_mensal_bruta": [r2(folha_mensal.get(m, 0)) for m in range(1, 13)],
        "tipos_folha": TIPO_FOLHA,
    }


TOP20 = {}


def gerar_servidores_detalhe(ano):
    """data/servidores_{ano}.js: secretaria -> vínculo -> cargo -> lista de servidores SEM nome
    nem matrícula: [ano de admissão, bruto do mês de referência, total no ano (sem adiantamento),
    13º, férias, meses com folha mensal, saiu no ano?, média da folha mensal (bruta) nos meses trabalhados, média líquida]."""
    caminho = achar(f"servidores_{ano}.csv")
    if not caminho:
        return None
    por_mat = {}
    por_mes9 = defaultdict(int)
    with (gzip.open if str(caminho).endswith(".gz") else open)(caminho, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            v = float(r["vencimentos"] or 0); mes = int(r["mes"] or 0); t = r["tipo_folha"]
            m = por_mat.setdefault(r["matricula"], {"cargo": r["cargo"], "sec": r["secretaria"], "adm": r["data_admissao"][:4],
                                                    "res": r["data_rescisao"], "mensal": {}, "liq": {}, "anual": 0.0, "d13": 0.0,
                                                    "ferias": 0.0, "meses": set()})
            m["cargo"] = r["cargo"] or m["cargo"]; m["sec"] = r["secretaria"] or m["sec"]
            if r["data_rescisao"]:
                m["res"] = r["data_rescisao"]
            if t == "9":
                m["mensal"][mes] = m["mensal"].get(mes, 0) + v; m["meses"].add(mes); por_mes9[mes] += 1
            if t in ("9", "8"):  # líquido recebido no mês = folha mensal + adiantamento (já descontado da mensal)
                m["liq"][mes] = m["liq"].get(mes, 0) + float(r["liquido"] or 0)
            if t != "8":
                m["anual"] += v
            if t == "6":          # 13º (dezembro)
                m["d13"] += v
            if t in ("3", "5"):   # férias: tipo 3 = folha de férias (janeiro, professores) / tipo 5 = abono de férias (junho)
                m["ferias"] += v
    maximo = max(por_mes9.values())
    mes_ref = max(mm for mm, n in por_mes9.items() if n >= 0.9 * maximo)
    arvore = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for m in por_mat.values():
        arvore[secretaria_curta(m["sec"])][vinculo(m["cargo"])][cargo_limpo(m["cargo"])].append(
            [int(m["adm"]) if m["adm"].isdigit() else None, r2(m["mensal"].get(mes_ref, 0)), r2(m["anual"]),
             r2(m["d13"]), r2(m["ferias"]), len(m["meses"]), 1 if m["res"].startswith(str(ano)) else 0,
             r2(sum(m["mensal"].values()) / len(m["meses"])) if m["meses"] else 0,
             r2(sum(m["liq"][k] for k in m["meses"]) / len(m["meses"])) if m["meses"] else 0])

    def no(lista):
        return {"n": len(lista), "t": r2(sum(x[2] for x in lista)),
                "m": r2(sum(x[1] for x in lista if x[1]) / max(1, sum(1 for x in lista if x[1])))}

    saida = {}
    for sec, vincs in arvore.items():
        vs = {}
        for vinc, cargos in vincs.items():
            cs = {}
            for cargo, lst in cargos.items():
                lst.sort(key=lambda x: -x[2])
                cs[cargo] = {**no(lst), "s": lst}
            todos = [x for c in cargos.values() for x in c]
            vs[vinc] = {**no(todos), "c": dict(sorted(cs.items(), key=lambda kv: -kv[1]["n"]))}
        todos = [x for c in vincs.values() for l in c.values() for x in l]
        saida[sec] = {**no(todos), "v": dict(sorted(vs.items(), key=lambda kv: -kv[1]["n"]))}
    saida = dict(sorted(saida.items(), key=lambda kv: -kv[1]["n"]))
    # 20 maiores remunerações médias mensais (só quem teve folha mensal em pelo menos 3 meses)
    todos = []
    for sec, vincs in arvore.items():
        for vinc, cargos in vincs.items():
            for cargo, lst in cargos.items():
                if vinc == "Aposentados e pensionistas":
                    continue
                for x in lst:
                    if x[5] >= 3 and x[7] > 0:
                        todos.append({"cargo": cargo, "secretaria": sec, "vinculo": vinc, "admissao": x[0],
                                      "media_mensal": x[7], "media_liquida": x[8], "mes_ref": x[1], "total_ano": x[2], "meses": x[5]})
    todos.sort(key=lambda x: -x["media_mensal"])
    global TOP20
    TOP20[ano] = todos[:20]
    destino = BASE / "data" / f"servidores_{ano}.js"
    js = json.dumps({"mes_ref": mes_ref, "sec": saida}, ensure_ascii=False, separators=(",", ":")).replace("</script", "<\\/script")
    destino.write_text(f"window.SERVIDORES=window.SERVIDORES||{{}};window.SERVIDORES[{ano}]={js};", encoding="utf-8")
    return destino


def main():
    anos = sorted({int(re.search(r"(\d{4})", p.name).group(1)) for p in RAW.glob("despesas_paulinia_*.csv*")})
    saida = {
        "municipio": "Paulínia",
        "uf": "SP",
        "ibge": "3536505",
        "fonte": "TCE-SP – Portal da Transparência Municipal (dados AUDESP enviados pela Prefeitura)",
        "fonte_url": "https://transparencia.tce.sp.gov.br/municipio/paulinia",
        "gerado_em": __import__("datetime").date.today().isoformat(),
        "meses": MESES,
        "anos": anos,
        "despesas": {},
        "receitas": {},
    }
    for ano in anos:
        d = processar_despesas(ano)
        if d:
            saida["despesas"][str(ano)] = d
            print(f"{ano}: {d['registros']:,} registros | pago R$ {d['totais']['pago']:,.0f} | "
                  f"empenhado líquido R$ {d['totais']['empenhado_liquido']:,.0f} | {d['total_fornecedores']} fornecedores")
        sv = processar_servidores(ano)
        if sv and d:
            d["servidores"] = sv
            # custo médio na folha do TCE = gasto com ativos (TCE) / servidores ativos (portal)
            d["folha"]["servidores_total"] = sv["servidores_ativos"]
            d["folha"]["custo_medio_mensal"] = r2(d["folha"]["ativos"] / sv["servidores_ativos"] / 12)
            print(f"      servidores: {sv['servidores_ativos']:,} ativos (ref. mês {sv['mes_referencia']}), "
                  f"média mensal R$ {sv['media_mensal']:,.0f}, custo médio R$ {sv['custo_medio_mensal']:,.0f}")
        sd = gerar_servidores_detalhe(ano)
        if sd:
            if d and d.get("servidores"):
                d["servidores"]["top20"] = TOP20.get(ano, [])
            print(f"      servidores detalhe -> {sd.name} ({sd.stat().st_size/1024:.0f} KB)")
        det = gerar_detalhe(ano)
        if det:
            print(f"      detalhe -> {det.name} ({det.stat().st_size/1024/1024:.1f} MB)")
        rc = processar_receitas(ano)
        if rc:
            saida["receitas"][str(ano)] = rc
            print(f"      receitas R$ {rc['total']:,.0f} (excluídas intra R$ {rc['intra_orcamentaria_excluida']:,.0f})")
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"-> {SAIDA} ({SAIDA.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
