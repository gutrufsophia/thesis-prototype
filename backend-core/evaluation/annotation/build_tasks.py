"""Build the annotation tasks for E1 (caveats), E2 (content selection) and E4 (text accuracy).

For each facility of the held-out sample (sample.csv) it writes, in tasks.js:
- a data sheet recomputed here from the frozen payload with the indicator definitions documented in
  public/js/territory.js, independently of the C++ code, so E4 also checks the computations;
- the candidate statements for E2, one per extracted fact, in a per-facility shuffled order that does
  not reveal which ones the system chose;
- the Portuguese text, split into sentences, shown only after E1 and E2 are locked.

The system's answers go to system.json, which the annotation page never loads: the caveat rules the
data trigger with every fact told (storyteller triggers), the planned facts and the lead.

    STORYTELLER=path/to/storyteller python3 backend-core/evaluation/annotation/build_tasks.py
"""

import csv
import hashlib
import json
import os
import random
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
BACKEND = EVAL.parent
SINAN_YEARS = ["2022", "2023", "2024", "2025"]
ILL_DEFINED = "xviii"
CAUSES = {"ix": "aparelho circulatório", "ii": "neoplasias (câncer)", "x": "aparelho respiratório",
          "xx": "causas externas", "xi": "aparelho digestivo", "i": "infecciosas e parasitárias"}
FLOW = {
    "Atendimento de Demanda Espontânea": "demanda espontânea",
    "Atendimento de Demanda Referenciada": "demanda referenciada (encaminhamento)",
    "Atendimento de Demanda Espontânea e Referenciada": "demanda espontânea e referenciada",
}
POSITION = {
    "cnes": "coordenada do próprio CNES",
    "cnefe_address": "endereço encontrado no CNEFE (o CNES não tinha coordenada utilizável)",
    "cnefe_corrected": "coordenada do CNES substituída pelo endereço no CNEFE",
    "cnefe_street": "centro da rua no CNEFE (aproximada)",
    "cnefe_cep": "centro do CEP no CNEFE (aproximada)",
}
TERRITORY = {1: "borda rural com saneamento precário", 2: "periferia urbana adensada, de renda mais baixa",
             3: "área urbana consolidada, de renda alta"}
PEER_LABELS = {
    "deprived": "moradores em setores com alguma privação", "precarious": "domicílios com esgoto precário",
    "off_network": "domicílios fora da rede de esgoto", "no_garbage": "domicílios sem coleta de lixo",
    "crowded": "moradores em setores adensados", "far_primary": "moradores a mais de 1 km de UBS pública",
    "income": "renda média do responsável",
}

# E1 checklist: the conditional caveat rules, described as a careful writer's cautions. Rules that
# always accompany a figure (estimate wording, straight-line distance...) are not judged.
CHECKLIST = [
    ("R01", ["C01"], "Hospital de referência",
     "A unidade, ou um hospital grande no raio, atende pacientes de toda a região: taxas por morador do entorno não descrevem o alcance dessa capacidade."),
    ("R03b", ["C03b"], "Estimativa do raio imprecisa",
     "Os setores censitários são grandes e o raio cobre só uma parte deles, então moradores e domicílios do raio são estimativas frágeis."),
    ("R04", ["C04"], "Destino do esgoto fora da rede",
     "Há uma parcela relevante de domicílios fora da rede de esgoto, e é preciso dizer quanto disso é destino precário (fossa rudimentar, vala, rio) e não fossa séptica."),
    ("R05", ["C05"], "Posição da unidade aproximada ou corrigida",
     "A localização no mapa não é a coordenada original do cadastro, e isso afeta distâncias e o raio."),
    ("R06", ["C06"], "Muitos serviços privados sem SUS no raio",
     "Boa parte das unidades no raio é privada e sem vínculo com o SUS, então a contagem de serviços superestima o que a população SUS tem por perto."),
    ("R08b", ["C08b"], "Permanência longa não é qualidade",
     "A permanência média é longa e isso reflete o tipo de caso atendido, não a qualidade do cuidado."),
    ("R12", ["C12"], "Ano de epidemia de dengue",
     "Um dos anos tem taxa de dengue muito acima dos outros, e isso precisa ser dito ao comparar anos."),
    ("R14", ["C14"], "Não falar em moradores longe da atenção básica",
     "A unidade é ela mesma uma UBS pública; a parcela de moradores 'longe da atenção básica' vem de setores que passam do raio e contradiz a presença da unidade."),
    ("R14b", ["C14b"], "Longe da rede pública, mas com muitos serviços privados",
     "Muitos moradores estão longe de UBS pública, mas o raio tem muitos serviços privados: estar longe da rede pública não indica, sozinho, falta de atendimento."),
    ("R15", ["C15"], "Contagens pequenas",
     "Um desfecho tem tão poucos casos que a taxa oscila muito; é melhor dar a contagem e não comparar a taxa."),
    ("R17", ["C17"], "Fontes de distrito e de município diferentes",
     "Há dados do distrito (sistemas da prefeitura de São Paulo) e do município (DATASUS), que não são diretamente comparáveis."),
    ("R18b", ["C18b"], "Muitos óbitos sem causa definida",
     "Uma parcela grande dos óbitos do município não tem causa definida, o que torna o perfil de causas pouco confiável."),
    ("R19", ["C19"], "Diferença em relação ao esperado não é causa",
     "Um desfecho do distrito está fora do intervalo que o modelo (renda, moradia, saneamento) espera; isso aponta fatores não medidos, não uma causa."),
    ("R21b", ["C21b"], "Área de atendimento perto do limite da região",
     "A unidade fica perto do limite da região metropolitana, e moradores de municípios vizinhos de fora da região não entram na conta da área de atendimento."),
    ("R22", ["C22"], "Distância até a unidade",
     "As pessoas da área de atendimento moram, em média, longe da unidade, e isso pesa no acesso mesmo que haja poucas pessoas por equipe."),
]


def br(value, digits=0):
    """Number in Brazilian format."""
    if value is None:
        return "–"
    text = f"{value:,.{digits}f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def pct(part, whole, digits=1):
    return br(100 * part / whole, digits) + "%" if whole else "–"


def per100k(cases, population, digits=1):
    return br(cases / population * 100_000, digits) if population else "–"


def years_sum(row, prefix):
    return sum(row.get(f"{prefix}_{y}") or 0 for y in SINAN_YEARS)


def distance(metres):
    return f"{br(metres)} m" if metres < 1000 else f"{br(metres / 1000, 1)} km"


def unit_section(f, stays):
    beds = f.get("LEITOS_EXISTENTES") or 0
    rows = [
        ("Nome", (f.get("NO_FANTASIA") or f.get("NO_RAZAO_SOCIAL") or "").strip()),
        ("Tipo (CNES)", f.get("tipo_equipamento")),
        ("Rede pública ou com vínculo SUS", "sim" if f.get("rede_sus") else "não"),
        ("Fluxo de clientela", FLOW.get(str(f.get("Fluxo_Clientela") or ""), "não informado")),
        ("Leitos existentes (SUS)", f"{br(beds)} ({br(f.get('LEITOS_SUS') or 0)})"),
        ("Leitos de UTI", br(f.get("UTI_TOTAL_EXIST") or 0)),
        ("Vínculos de médicos / enfermeiros", f"{br(f.get('total_medicos') or 0)} / {br(f.get('total_enfermeiros') or 0)}"),
        ("Internações SUS, jan/2025 a jul/2026", br(f.get("internacoes_total") or 0)),
    ]
    stay = f.get("media_dias_permanencia")
    if (f.get("internacoes_total") or 0) > 0 and stay is not None:
        below = sum(1 for s in stays if s < stay)
        rows.append(("Permanência média", f"{br(stay, 1)} dias (maior que em {round(100 * below / len(stays))}% dos {len(stays)} hospitais com internação)"))
    source = f.get("coord_source") or "cnes"
    position = POSITION.get(source, source)
    if source == "cnefe_corrected":
        position += f"; deslocamento de {distance(f.get('coord_shift_m') or 0)}"
    if source in ("cnefe_street", "cnefe_cep"):
        position += f"; incerteza de cerca de {distance(f.get('coord_precision_m') or 0)}"
    rows.append(("Posição no mapa", position))
    return {"title": "Unidade", "source": "CNES, competência de agosto de 2026; SIH/SUS", "rows": rows}


def radius_section(s):
    c = s["census"]
    r, m, g = c["radius"], c.get("municipality") or {}, c.get("region") or {}
    tracts = s.get("tracts") or []
    total_pop = sum(t.get("population") or 0 for t in tracts)
    inside = sum((t.get("population") or 0) * (t.get("share_inside") or 0) for t in tracts)
    name = (s.get("location") or {}).get("municipality", "município")

    def three(key, transform=lambda v: v, unit="%", digits=1):
        vals = [transform(x.get(key)) if x.get(key) is not None else None for x in (r, m, g)]
        txt = [br(v, digits) + unit if v is not None else "–" for v in vals]
        return f"{txt[0]} (município de {name}: {txt[1]}; região: {txt[2]})"

    others = s.get("facilities") or []
    private = sum(1 for o in others if not o.get("sus_network"))
    hubs = [o for o in others if (o.get("beds") or 0) >= 50 and "Hospital" in (o.get("type") or "")]
    rows = [
        ("Moradores (estimativa)", br(r.get("population"))),
        ("Domicílios (estimativa)", br(r.get("households"))),
        ("Setores censitários tocados pelo raio", br(r.get("tracts"))),
        ("Parte da população desses setores que fica dentro do raio", pct(inside, total_pop, 0)),
        ("Domicílios fora da rede de esgoto", three("sewage_pct", lambda v: 100 - v)),
        ("Domicílios com esgoto precário (fossa rudimentar, vala, rio...)", three("precarious_pct")),
        ("Domicílios sem coleta de lixo", three("garbage_pct", lambda v: 100 - v)),
        ("Moradores por domicílio", three("residents_per_household", unit="", digits=2)),
        (f"Moradores em setores adensados ({br(s.get('crowding_threshold') or 3.1, 1)} ou mais por domicílio)", three("crowded_pct")),
        ("Renda média do responsável (R$)", three("income", unit="", digits=0)),
        ("Moradores a mais de 1 km de UBS pública", three("far_primary_pct")),
        ("Outras unidades de saúde no raio", f"{len(others)}, das quais {private} privadas sem vínculo SUS"),
        ("Hospitais com 50 leitos ou mais no raio", ", ".join(f"{o['name']} ({br(o['beds'])} leitos)" for o in hubs) or "nenhum"),
    ]
    return {"title": f"Raio de {distance(s.get('radius_m') or 1000)}", "source": "Censo Demográfico 2022 (estimativas por área), CNES",
            "rows": rows}


def reference_section(ctx):
    if not ctx:
        return None
    v, p = ctx.get("values", {}), ctx.get("percentiles", {})
    rows = [("Tipo de território", f"{TERRITORY.get(ctx.get('territory_type'), '–')} ({br(ctx.get('type_size'))} de {br(ctx.get('facilities'))} unidades)")]
    for key, label in PEER_LABELS.items():
        if key in p:
            value = f"R$ {br(v[key])}" if key == "income" else br(v[key], 1) + "%"
            rows.append((label.capitalize(), f"{value}; maior que em {round(100 * p[key])}% das {br(ctx.get('group_size'))} unidades do mesmo grupo"))
    out = [{"title": "Comparação com unidades do mesmo grupo (raio de 1 km)", "source": "Censo 2022; cálculo de referência do sistema",
            "rows": rows}]
    if ctx.get("supply_measure") == "catchment":
        crows = [
            ("Pessoas na área de atendimento estimada", br(v.get("served"))),
            ("Delas, em setores com alguma privação", br(v.get("served_deprived"), 1) + "%"),
            ("Posição da privação entre as UBS públicas", f"maior que em {round(100 * ctx['need_percentile'])}% das {br(ctx.get('public_primary_size'))}"),
        ]
        if ctx.get("team_equivalents"):
            crows += [
                ("Equipes de atenção básica (equivalentes de eSF)", br(ctx["team_equivalents"], 2)),
                ("Pessoas por equipe", f"{br(v.get('served_per_team'))} (PNAB 2017: 2.000 a 3.500 por equipe)"),
            ]
        else:
            crows += [("Equipes de Saúde da Família ou de Atenção Primária", "nenhuma registrada no CNES"),
                      ("Posição em pessoas por unidade", f"maior que em {round(100 * ctx['load_percentile'])}% das UBS públicas")]
        if v.get("served_mean_distance") is not None:
            crows.append(("Distância média dessas pessoas até a unidade (linha reta)", distance(v["served_mean_distance"])))
            crows.append(("Dessas pessoas, a mais de 2 km", br(v.get("served_far"), 1) + "%"))
        crows.append(("Distância da unidade até o limite da região metropolitana", distance(ctx.get("edge_m") or 0)))
        crows.append(("Raio médio de busca dessas pessoas", distance(ctx.get("mean_catchment_m") or 0)))
        out.append({"title": "Área de atendimento estimada (UBS públicas)",
                    "source": "CNEFE 2022, Censo 2022, CNES; modelo de Huff com captação variável", "rows": crows})
    return out


def district_section(d, city, expected):
    if not d:
        return None
    tb = years_sum(d, "tb")
    rows = [
        ("Distrito", d.get("nm_dist")),
        ("Tuberculose, casos por 100 mil hab. por ano (2022–2025)",
         f"{per100k(tb / 4, d.get('populacao_total'))} ({br(tb)} casos; cidade: {per100k(years_sum(city, 'tb') / 4, city.get('populacao_total'))})"),
        ("Nascidos vivos de mães com menos de 20 anos (2022–2024)",
         f"{pct(d.get('nasc_mae_menor_20') or 0, d.get('nasc_idade_conhecida'))} ({br(d.get('nasc_mae_menor_20'))} nascimentos; cidade: {pct(city.get('nasc_mae_menor_20') or 0, city.get('nasc_idade_conhecida'))})"),
        ("Nascidos vivos prematuros (2022–2024)",
         f"{pct(d.get('nasc_pretermo') or 0, d.get('nasc_gestacao_conhecida'))} (cidade: {pct(city.get('nasc_pretermo') or 0, city.get('nasc_gestacao_conhecida'))})"),
    ]
    for e in expected:
        if e.get("scale") != "district":
            continue
        label = {"tb": "Tuberculose", "teen": "Mães com menos de 20 anos"}.get(e["outcome"], e["outcome"])
        flag = {"above": "acima do intervalo", "below": "abaixo do intervalo"}.get(e.get("flag"), "dentro do intervalo ou sem sinalização")
        rows.append((f"{label}: observado e esperado pelo modelo",
                     f"{br(e['observed'])} observados; {br(e['expected'], 1)} esperados (intervalo {br(e['lower'], 1)} a {br(e['upper'], 1)}); {flag}"))
    return {"title": "Distrito da capital", "source": "SMS-SP (TBWEB, SINASC e SIM municipais); modelo quasi-Poisson", "rows": rows}


def municipality_section(m, region):
    name = m.get("nome")
    rows = []
    for y in SINAN_YEARS:
        rows.append((f"Dengue {y}, casos prováveis por 100 mil hab.",
                     f"{per100k(m.get(f'dengue_{y}') or 0, m.get('populacao'), 0)} ({br(m.get(f'dengue_{y}'))} casos; região: {per100k(region.get(f'dengue_{y}') or 0, region.get('populacao'), 0)})"))
    lepto = years_sum(m, "lepto")
    rows.append(("Leptospirose, casos por 100 mil hab. por ano (2022–2025)",
                 f"{per100k(lepto / 4, m.get('populacao'), 2)} ({br(lepto)} casos; região: {per100k(years_sum(region, 'lepto') / 4, region.get('populacao'), 2)})"))
    tb = years_sum(m, "tuberculose")
    rows.append(("Tuberculose, casos por 100 mil hab. por ano (2022–2025)",
                 f"{per100k(tb / 4, m.get('populacao'))} ({br(tb)} casos; região: {per100k(years_sum(region, 'tuberculose') / 4, region.get('populacao'))})"))
    rows.append(("Nascidos vivos de mães com menos de 20 anos (2022–2024)",
                 f"{pct(m.get('nasc_mae_menor_20') or 0, m.get('nasc_idade_conhecida'))} ({br(m.get('nasc_mae_menor_20'))}; região: {pct(region.get('nasc_mae_menor_20') or 0, region.get('nasc_idade_conhecida'))})"))
    rows.append(("Nascidos vivos prematuros (2022–2024)",
                 f"{pct(m.get('nasc_pretermo') or 0, m.get('nasc_gestacao_conhecida'))} (região: {pct(region.get('nasc_pretermo') or 0, region.get('nasc_gestacao_conhecida'))})"))
    total = m.get("obitos_total") or 0
    ill = m.get(f"obitos_cap_{ILL_DEFINED}") or 0
    defined = total - ill
    rows.append(("Óbitos de 30 a 69 anos sem causa definida (2022–2024)", f"{pct(ill, total)} de {br(total)}"))
    region_defined = (region.get("obitos_total") or 0) - (region.get(f"obitos_cap_{ILL_DEFINED}") or 0)
    for chapter, label in CAUSES.items():
        rows.append((f"Óbitos por {label}, entre os de causa definida",
                     f"{pct(m.get(f'obitos_cap_{chapter}') or 0, defined)} (região: {pct(region.get(f'obitos_cap_{chapter}') or 0, region_defined)})"))
    return {"title": f"Município: {name}", "source": "SINAN, SINASC e SIM (DATASUS); população do Censo 2022", "rows": rows}


def statement(fact):
    """One E2 candidate: the fact's figures in plain words, without the system's sentence."""
    s = {k: v.get("text") for k, v in fact["slots"].items()}
    i = fact["id"]
    known = {
        "profile": lambda: f"Perfil da unidade: {s.get('type')}, {s.get('network')}, atendimento {s.get('flow')}.",
        "beds": lambda: f"Leitos da unidade: {s.get('unit')} ({s.get('sus_unit')} SUS; {s.get('icu_unit')} de UTI).",
        "staff": lambda: f"Profissionais da unidade: {s.get('physicians_unit')} vínculos de médicos e {s.get('nurses_unit')} de enfermeiros.",
        "admissions": lambda: f"Internações: {s.get('total_unit')}; a causa mais frequente é {s.get('chapter')} ({s.get('share_unit')}).",
        "stay": lambda: "Permanência média de internação da unidade em comparação com outros hospitais.",
        "position": lambda: "A posição da unidade no mapa é aproximada ou foi corrigida pelo endereço.",
        "residents": lambda: f"Moradores no raio: cerca de {s.get('radius')} em {s.get('households_radius')} domicílios.",
        "territory": lambda: f"Tipo de território do raio de 1 km: {s.get('type')}.",
        "peer": lambda: f"Entre as {s.get('count_group')} unidades de {s.get('group')}, o raio está entre os {s.get('rank')} com {s.get('indicator')}.",
        "need_supply": lambda: "Necessidade (privação) e oferta (pessoas por equipe ou por unidade) na área de atendimento estimada.",
        "network": lambda: f"Outras unidades de saúde no raio: {s.get('count_radius')} ({s.get('public_radius')} públicas ou SUS, {s.get('private_radius')} privadas sem SUS).",
        "access": lambda: f"Moradores do raio a mais de 1 km de UBS pública: {s.get('radius')} (município {s.get('municipality')}).",
        "sewage": lambda: f"Domicílios do raio fora da rede de esgoto: {s.get('radius')} (município {s.get('municipality')}).",
        "precarious": lambda: f"Domicílios do raio com esgoto precário: {s.get('radius')} (município {s.get('municipality')}).",
        "garbage": lambda: f"Domicílios do raio sem coleta de lixo: {s.get('radius')} (município {s.get('municipality')}).",
        "crowding": lambda: f"Moradores por domicílio no raio: {s.get('radius')} (município {s.get('municipality')}).",
        "crowded": lambda: f"Moradores do raio em setores adensados: {s.get('radius')} (município {s.get('municipality')}).",
        "tb_district": lambda: f"Tuberculose no distrito {s.get('district_name')}: {s.get('district')} por 100 mil hab. por ano (cidade {s.get('city')}).",
        "tb": lambda: f"Tuberculose no município: {s.get('municipality')} por 100 mil hab. por ano (região {s.get('region')}).",
        "dengue": lambda: f"Dengue no município em {s.get('year')}: {s.get('municipality')} por 100 mil hab. (região {s.get('region')}).",
        "lepto": lambda: f"Leptospirose no município: {s.get('municipality')} por 100 mil hab. por ano ({s.get('count_municipality')} casos).",
        "teen_district": lambda: f"Mães com menos de 20 anos no distrito {s.get('district_name')}: {s.get('district')} dos nascimentos (cidade {s.get('city')}).",
        "teen": lambda: f"Mães com menos de 20 anos no município: {s.get('municipality')} dos nascimentos (região {s.get('region')}).",
        "preterm": lambda: f"Nascimentos prematuros no município: {s.get('municipality')} (região {s.get('region')}).",
        "mortality": lambda: f"Principal causa de óbito de 30 a 69 anos no município: {s.get('cause')} ({s.get('municipality')}).",
        "surprise_tb": lambda: "Tuberculose no distrito fora do intervalo esperado pelo modelo de renda, moradia e saneamento.",
        "surprise_teen": lambda: "Mães com menos de 20 anos no distrito fora do intervalo esperado pelo modelo.",
    }
    return known[i]() if i in known else f"{i}: " + "; ".join(f"{k} {v}" for k, v in s.items() if v)


def sentences(body):
    out = []
    for pi, paragraph in enumerate(body["paragraphs"]):
        for si, sentence in enumerate(paragraph):
            text = "".join(seg["text"] for seg in sentence["segments"]).strip()
            # claims: every number written in the sentence, years and percentages included
            claims = len(re.findall(r"\d[\d.]*(?:,\d+)?", text))
            out.append({"id": f"p{pi}s{si}", "paragraph": pi, "text": text, "claims": claims})
    return out


def storyteller(*args):
    exe = os.environ.get("STORYTELLER", "storyteller")
    env = {**os.environ, "STORY_CONFIG_DIR": str(BACKEND / "config")}
    return json.loads(subprocess.run([exe, *args], check=True, capture_output=True, text=True, env=env).stdout)


def main():
    sample = list(csv.DictReader(open(EVAL / "sample.csv")))
    fixtures = [EVAL / "fixtures" / f"{row['cnes']}_1000.json" for row in sample]
    triggers = {Path(t["fixture"]).name: t for t in storyteller("triggers", *map(str, fixtures))}
    units, system = [], {}
    for row, path in zip(sample, fixtures):
        payload = json.loads(path.read_text())
        body = storyteller("narrate", str(path), "pt")
        uid = "u" + hashlib.sha1(row["cnes"].encode()).hexdigest()[:6]
        facts = body["facts"]
        rng = random.Random(f"statements:{uid}")
        order = list(range(len(facts)))
        rng.shuffle(order)
        statements = [{"id": f"f{n}", "text": statement(facts[k])} for n, k in enumerate(order)]
        fact_of = {f"f{n}": facts[k]["id"] for n, k in enumerate(order)}
        ctx = payload.get("context") or {}
        sheet = [unit_section(payload["facility"], payload.get("hospital_stays") or []),
                 radius_section(payload["surroundings"])]
        sheet += reference_section(ctx) or []
        if payload.get("district"):
            sheet.append(district_section(payload["district"], payload.get("city") or {}, payload.get("expected") or []))
        if payload.get("municipality"):
            sheet.append(municipality_section(payload["municipality"], payload.get("region") or {}))
        units.append({"id": uid, "sheet": sheet, "statements": statements, "sentences": sentences(body)})
        fired = {r["rule"] for r in triggers[path.name]["rules"]}
        system[uid] = {
            "cnes": row["cnes"], "stratum": row["stratum"],
            "rules": {item: any(rule in fired for rule in rules) for item, rules, _, _ in CHECKLIST},
            "planned": sorted({fid for fid, fact in fact_of.items()
                               if any(fact == p for para in body["plan"] for p in para)}),
            "lead": next((fid for fid, fact in fact_of.items() if body["plan"][0] and fact == body["plan"][0][0]), None),
            "statement_fact": fact_of,
            "verified": body["verified"],
        }
    tasks = {"version": body["version"], "checklist": [{"id": i, "title": t, "description": d} for i, _, t, d in CHECKLIST],
             "units": units}
    (HERE / "tasks.js").write_text("window.ANNOTATION_TASKS = " + json.dumps(tasks, ensure_ascii=False) + ";\n")
    (HERE / "system.json").write_text(json.dumps(system, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(units)} units, {sum(len(u['sentences']) for u in units)} sentences, "
          f"{sum(s['claims'] for u in units for s in u['sentences'])} claims")


if __name__ == "__main__":
    main()
