"""Build the annotation tasks for E2 (content selection) and E4 (text accuracy).

10 of the 40 held-out facilities (sample.csv), drawn with fixed seeds: first 20, 2 or 3 per stratum,
on which the LLM comparison runs (../llm); then the 10 annotated, one per stratum and 2 more, so that
the annotation takes about 45 minutes. For each:
- the Portuguese text, split into sentences; for every sentence the annotator also chooses "relevant"
  or "could be left out" (E2b, the precision of the selection);
- after the text, up to 6 facts the text left out, drawn at random when there are more, each with
  its figures; the annotator ticks those that should have been told, or "none" (E2, the recall of the
  selection). It replaces a blind choice of the 3 most important facts among 10, made before the
  text, which the author found too hard to answer when every fact seems important.
Next to each sentence, the
  data it uses, recomputed here from the frozen payload and the reference files with the definitions
  of public/js/territory.js and backend-core/src/payload.cpp, independently of the C++ code, and
  written the way the text expresses them (E4). The data of every planned fact are also shown
  together, for the whole unit.

For 2 of the 10, from 2 strata, the E4 text is the free LLM text of ../llm (run_llm.py, greedy
decoding) instead of the template's; it tells the same planned facts, and each of its sentences gets
the data of the facts its numbers align with (score_llm.py). The page does not say which is which.

The system's answers go to system.json, which the annotation page never loads: the planned facts, the
fact behind each left-out statement, and the facts and caveats each sentence tells.

    STORYTELLER=path/to/storyteller python3 backend-core/evaluation/annotation/build_tasks.py
"""

import csv
import hashlib
import json
import math
import os
import random
import re
import subprocess
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
BACKEND = EVAL.parent
ROOT = BACKEND.parent
SEED = 20261116
LLM_TEXTS = EVAL / "results" / "llm" / "gemma4_e4b"
UNITS = 20  # the LLM comparison (../llm)
LLM_UNITS = 4
ANNOTATED = 10  # the human annotation: a subset of the 20, about 45 minutes per annotator
ANNOTATED_LLM = 2
OMITTED = 6  # facts left out of the text, shown for E2 (all of them when there are fewer)
SINAN_YEARS = ["2022", "2023", "2024", "2025"]
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
GROUPS = {
    "Centro de Saúde/UBS": "atenção básica", "Posto de Saúde": "atenção básica", "Polo Academia da Saúde": "atenção básica",
    "Hospital Geral": "internação (hospitais)", "Hospital Especializado": "internação (hospitais)", "Unidade Mista": "internação (hospitais)",
    "Pronto Atendimento (UPA)": "urgência e emergência", "Pronto Socorro Geral": "urgência e emergência",
    "Pronto Socorro Especializado": "urgência e emergência", "Policlínica": "atenção especializada e saúde mental",
    "Clínica/Centro de Especialidade": "atenção especializada e saúde mental",
    "Centro de Atenção Psicossocial (CAPS)": "atenção especializada e saúde mental",
    "Unidade de Apoio Diagnose e Terapia (SADT Isolado)": "diagnose e terapia",
}
PRIMARY = {"Centro de Saúde/UBS", "Posto de Saúde"}
PEER = {  # indicator key of the peer fact -> label, value from a reference row
    "deprived": ("moradores em setores com alguma privação", lambda r: 100 * (r["deprived_population"] or 0) / r["population"]),
    "precarious": ("domicílios com esgoto precário", lambda r: r["precarious_pct"]),
    "off_network": ("domicílios fora da rede de esgoto", lambda r: 100 - r["sewage_pct"]),
    "no_garbage": ("domicílios sem coleta de lixo", lambda r: 100 - r["garbage_pct"]),
    "crowded": ("moradores em setores adensados", lambda r: r["crowded_pct"]),
    "far_primary": ("moradores a mais de 1 km de UBS pública", lambda r: r["far_primary_pct"]),
    "income": ("renda média do responsável", lambda r: r["income"]),
}


def br(value, digits=0):
    if value is None:
        return "–"
    text = f"{value:,.{digits}f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def pct(part, whole, digits=1):
    return br(100 * part / whole, digits) + "%" if whole else "–"


def per100k(cases, population, digits=1):
    return br(cases / population * 100_000, digits) if population else "–"


def years(row, prefix):
    return sum(row.get(f"{prefix}_{y}") or 0 for y in SINAN_YEARS)


def distance(metres):
    return f"{br(metres)} m" if metres < 1000 else f"{br(metres / 1000, 1)} km"


def share_below(values, value):
    """Share of values below `value`, ties counted half, as payload.cpp ranks peers."""
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return (below + equal / 2) / len(values)


def position(values, value, count_label):
    p = 100 * share_below(values, value)
    return f"maior que em {br(p, 1)}% e menor que em {br(100 - p, 1)}% das {br(len(values))} {count_label}"


def load_reference():
    numeric = lambda v: float(v) if v not in ("", None) else None  # noqa: E731
    rows = []
    for r in csv.DictReader(open(ROOT / "data" / "surroundings_1000.csv")):
        rows.append({k: (numeric(v) if k not in ("tipo_equipamento", "rede_sus") else v) for k, v in r.items()})
    types = {int(r["cnes"]): int(r["territory_type"]) for r in csv.DictReader(open(ROOT / "data" / "surroundings_types.csv"))}
    catchment = [{k: (v if k == "near_edge" else numeric(v)) for k, v in r.items()}
                 for r in csv.DictReader(open(ROOT / "data" / "catchment_units.csv"))]
    return rows, types, catchment


def admissions_labels():
    text = (ROOT / "public" / "js" / "fields.js").read_text()
    return dict(re.findall(r"(internacoes_\w+): \{ pt: '([^']+)'", text))


class Evidence:
    """Data each fact rests on, recomputed from the payload and the reference files."""

    def __init__(self, payload, reference, adm_labels):
        self.p = payload
        self.rows, self.types, self.catchment = reference
        self.adm = adm_labels
        self.f = payload["facility"]
        self.s = payload["surroundings"]
        self.census = self.s["census"]
        self.place = (self.s.get("location") or {}).get("municipality", "município")
        self.own = next((r for r in self.rows if int(r["cnes"]) == int(self.f["CO_CNES"])), None)

    def three(self, key, transform=lambda v: v, unit="%", digits=1):
        out = []
        for label, scope in ((f"Raio de {distance(self.s.get('radius_m') or 1000)}", "radius"),
                             (f"município de {self.place}", "municipality"), ("região metropolitana", "region")):
            v = (self.census.get(scope) or {}).get(key)
            out.append((label, br(transform(v), digits) + unit if v is not None else "–"))
        return out

    def get(self, fid):
        method = getattr(self, f"e_{fid}", None)
        return method() if method else None

    def e_profile(self):
        f = self.f
        return ("Perfil da unidade", [("Tipo (CNES)", f.get("tipo_equipamento")),
                                      ("Rede pública ou com vínculo SUS", "sim" if f.get("rede_sus") else "não"),
                                      ("Fluxo de clientela", FLOW.get(f.get("Fluxo_Clientela"), "não informado"))])

    def e_beds(self):
        f = self.f
        return ("Leitos da unidade", [("Leitos existentes (UTI incluída)", br(f.get("LEITOS_EXISTENTES") or 0)),
                                      ("Leitos SUS", br(f.get("LEITOS_SUS") or 0)),
                                      ("Leitos de UTI", br(f.get("UTI_TOTAL_EXIST") or 0))])

    def e_staff(self):
        return ("Profissionais da unidade", [("Vínculos de médicos", br(self.f.get("total_medicos") or 0)),
                                             ("Vínculos de enfermeiros", br(self.f.get("total_enfermeiros") or 0))])

    def e_admissions(self):
        total = self.f.get("internacoes_total") or 0
        top = max(self.adm, key=lambda c: self.f.get(c) or 0)
        return ("Internações SUS, jan/2025 a jul/2026",
                [("Total", br(total)), ("Causa mais frequente", f"{self.adm[top]}: {pct(self.f.get(top) or 0, total)}")])

    def e_deaths(self):
        f = self.f
        admissions, deaths, expected = f.get("internacoes_total") or 0, f.get("obitos_sus"), f.get("obitos_esperados")
        if not admissions or deaths is None or not expected:
            return None
        band = {"within": "dentro da variação observada (limites de 99,8%)",
                "above": "acima da variação observada (limites de 99,8%)",
                "below": "abaixo da variação observada (limites de 99,8%)"}.get(f.get("mortalidade_faixa"), "–")
        return ("Óbitos nas internações pelo SUS, jan/2025 a jul/2026",
                [("Internações", br(admissions)), ("Óbitos", f"{br(deaths)} ({pct(deaths, admissions)})"),
                 ("Esperados pelo perfil dos pacientes (diagnóstico, idade, caráter)", f"{br(expected)} ({pct(expected, admissions)})"),
                 ("Entre os hospitais da região", band)])

    def e_casemix(self):
        mix = self.f.get("mortalidade_perfil")
        if not isinstance(mix, dict):
            return None
        parts = mix.get("shapley_pp") or {}
        signed = {k: ("+" if (parts.get(k) or 0) > 0 else "") + br(parts.get(k), 1) for k in ("diagnostico", "idade", "carater")}
        rate = mix.get("capitulo_taxa_regiao") or 0
        chapter = self.adm.get(mix.get("capitulo"), mix.get("capitulo") or "–")
        return ("Perfil dos pacientes contra os hospitais da região metropolitana",
                [("Mortalidade média dos hospitais da região", br(mix.get("taxa_regiao"), 1) + "%"),
                 ("Quanto cada fator afasta o esperado da média (pontos percentuais)",
                  f"diagnósticos {signed['diagnostico']}; idade {signed['idade']}; caráter {signed['carater']}"),
                 (f"Internações por {chapter.lower()}",
                  f"{br(mix.get('capitulo_pct'), 1)}% (região: {br(mix.get('capitulo_regiao_pct'), 1)}%, "
                  f"mortalidade de {br(rate, 2 if rate < 1 else 1)}%)"),
                 ("Internações de pessoas com 70 anos ou mais",
                  f"{br(mix.get('idosos_pct'), 1)}% (região: {br(mix.get('idosos_regiao_pct'), 1)}%)"),
                 ("Internações de urgência",
                  f"{br(mix.get('urgencia_pct'), 1)}% (região: {br(mix.get('urgencia_regiao_pct'), 1)}%)"),
                 ("Eletivas", f"{br(100 - (mix.get('urgencia_pct') or 0), 1)}%"),
                 ("Fluxo de clientela", FLOW.get(self.f.get("Fluxo_Clientela"), "não informado"))])

    def e_stay(self):
        stays = self.p.get("hospital_stays") or []
        stay = self.f.get("media_dias_permanencia") or 0
        return ("Permanência média", [("Dias", br(stay, 1)),
                                      ("Comparação", position(stays, stay, "unidades com internação SUS"))])

    def e_position(self):
        f = self.f
        rows = [("Posição no mapa", POSITION.get(f.get("coord_source"), f.get("coord_source")))]
        if f.get("coord_shift_m"):
            rows.append(("Distância entre a coordenada do CNES e o endereço", distance(f["coord_shift_m"])))
        if f.get("coord_precision_m") and f.get("coord_source") in ("cnefe_street", "cnefe_cep"):
            rows.append(("Incerteza da posição", distance(f["coord_precision_m"])))
        return ("Posição da unidade", rows)

    def e_residents(self):
        r = self.census["radius"]
        tracts = self.s.get("tracts") or []
        total = sum(t.get("population") or 0 for t in tracts)
        inside = sum((t.get("population") or 0) * (t.get("share_inside") or 0) for t in tracts)
        return ("Moradores do raio (Censo 2022)", [("Moradores", br(r.get("population"))), ("Domicílios", br(r.get("households"))),
                                                   ("Setores tocados pelo raio", br(r.get("tracts"))),
                                                   ("Parte da população desses setores dentro do raio", pct(inside, total, 0))])

    def e_sewage(self):
        return ("Domicílios fora da rede de esgoto", self.three("sewage_pct", lambda v: 100 - v)
                + [("Raio: com esgoto precário (fossa rudimentar, vala, rio…)", br(self.census["radius"].get("precarious_pct"), 1) + "%")])

    def e_precarious(self):
        return ("Domicílios com esgoto precário", self.three("precarious_pct"))

    def e_garbage(self):
        return ("Domicílios sem coleta de lixo", self.three("garbage_pct", lambda v: 100 - v))

    def e_crowding(self):
        return ("Moradores por domicílio", self.three("residents_per_household", unit="", digits=2))

    def e_crowded(self):
        return (f"Moradores em setores entre os 10% mais adensados ({br(self.s.get('crowding_threshold') or 3.1, 1)} ou mais por domicílio)",
                self.three("crowded_pct"))

    def e_access(self):
        return ("Moradores a mais de 1 km de UBS pública (em linha reta)", self.three("far_primary_pct"))

    def e_network(self):
        others = self.s.get("facilities") or []
        public = sum(1 for o in others if o.get("sus_network"))
        hubs = [o for o in others if (o.get("beds") or 0) >= 50 and "Hospital" in (o.get("type") or "")]
        return ("Outras unidades de saúde no raio", [("Total", br(len(others))), ("Públicas ou com vínculo SUS", br(public)),
                                                     ("Privadas sem vínculo SUS", br(len(others) - public)),
                                                     ("Hospitais com 50 leitos ou mais", br(len(hubs)))])

    def e_territory(self):
        own_type = self.types.get(int(self.f["CO_CNES"]))
        same = sum(1 for t in self.types.values() if t == own_type)
        return ("Tipo de território (raio de 1 km)", [("Tipo", TERRITORY.get(own_type, "–")),
                                                      ("Unidades do mesmo tipo", f"{br(same)} de {br(len(self.rows))} mapeadas")])

    def e_peer(self, key=None):
        if not self.own:
            return None
        group = GROUPS.get(self.f.get("tipo_equipamento"))
        peers = [r for r in self.rows if GROUPS.get(r["tipo_equipamento"]) == group and r["population"]]
        rows = []
        def safe(value, r):
            try:
                return value(r)
            except TypeError:  # a missing census value
                return None

        for k, (label, value) in PEER.items():
            if key and k != key:
                continue
            values = [v for v in (safe(value, r) for r in peers) if v is not None]
            mine = safe(value, self.own)
            if mine is None:
                continue
            shown = f"R$ {br(mine)}" if k == "income" else br(mine, 1) + "%"
            rows.append((label.capitalize(), f"{shown}; {position(values, mine, f'unidades de {group}')}"))
        return ("Comparação com unidades do mesmo grupo (raio de 1 km)", rows)

    def e_need_supply(self):
        units = [u for u in self.catchment if (u["served_population"] or 0) > 0]
        own = next((u for u in units if int(u["cnes"]) == int(self.f["CO_CNES"])), None)
        if not own:
            return None
        need = position([u["served_deprived_pct"] for u in units], own["served_deprived_pct"], "UBS públicas")
        rows = [("Pessoas na área de atendimento estimada", br(own["served_population"])),
                ("Delas, em setores com alguma privação", f"{br(own['served_deprived_pct'], 1)}%; {need}")]
        if own.get("team_equivalents"):
            rows += [("Equipes (equivalentes de Saúde da Família)", br(own["team_equivalents"], 2)),
                     ("Pessoas por equipe", f"{br(own['served_per_team'])} (faixa da PNAB: 2.000 a 3.500)")]
        else:
            rows += [("Equipes de Saúde da Família ou de Atenção Primária", "nenhuma registrada"),
                     ("Pessoas por unidade", position([u["served_population"] for u in units], own["served_population"], "UBS públicas"))]
        rows += [("Distância média dessas pessoas até a unidade (linha reta)", distance(own["served_mean_distance_m"])),
                 ("Dessas pessoas, a mais de 2 km", br(own["served_far_pct"], 1) + "%"),
                 ("Distância da unidade ao limite da região metropolitana", distance(own["edge_m"]))]
        return ("Área de atendimento estimada", rows)

    def district_rows(self):
        return self.p.get("districts") or []

    def e_tb_district(self):
        d, city = self.p.get("district"), self.p.get("city") or {}
        if not d:
            return None
        rate = lambda r: years(r, "tb") / 4 / r["populacao_total"] * 100_000 if r.get("populacao_total") else None  # noqa: E731
        rates = sorted(v for v in map(rate, self.district_rows()) if v is not None)
        own = rate(d)
        low = sum(1 for v in rates if v < own) + 1
        high = sum(1 for v in rates if v > own) + 1
        return (f"Tuberculose no distrito {d.get('nm_dist')} (SMS-SP, 2022–2025)",
                [("Casos por 100 mil hab. por ano", per100k(years(d, "tb") / 4, d.get("populacao_total"))),
                 ("Casos no período", br(years(d, "tb"))),
                 ("Cidade de São Paulo", per100k(years(city, "tb") / 4, city.get("populacao_total"))),
                 ("Posição entre os distritos", f"{low}ª menor e {high}ª maior taxa entre {len(rates)}")])

    def e_tb(self):
        m, g = self.p.get("municipality") or {}, self.p.get("region") or {}
        return (f"Tuberculose no município de {m.get('nome')} (2022–2025)",
                [("Casos por 100 mil hab. por ano", per100k(years(m, "tuberculose") / 4, m.get("populacao"))),
                 ("Casos no período", br(years(m, "tuberculose"))),
                 ("Região metropolitana", per100k(years(g, "tuberculose") / 4, g.get("populacao")))])

    def e_dengue(self):
        m, g = self.p.get("municipality") or {}, self.p.get("region") or {}
        return (f"Dengue no município de {m.get('nome')}, casos prováveis por 100 mil hab.",
                [(y, f"{per100k(m.get(f'dengue_{y}') or 0, m.get('populacao'), 0)} ({br(m.get(f'dengue_{y}'))} casos; região: "
                     f"{per100k(g.get(f'dengue_{y}') or 0, g.get('populacao'), 0)})") for y in reversed(SINAN_YEARS)])

    def e_lepto(self):
        m, g = self.p.get("municipality") or {}, self.p.get("region") or {}
        return (f"Leptospirose no município de {m.get('nome')} (2022–2025)",
                [("Casos por 100 mil hab. por ano", per100k(years(m, "lepto") / 4, m.get("populacao"), 2)),
                 ("Casos no período", br(years(m, "lepto"))),
                 ("Região metropolitana", per100k(years(g, "lepto") / 4, g.get("populacao"), 2))])

    def births(self, row, compare, compare_label):
        return [("Mães com menos de 20 anos", f"{pct(row.get('nasc_mae_menor_20') or 0, row.get('nasc_idade_conhecida'))} "
                 f"({br(row.get('nasc_mae_menor_20'))} nascimentos)"),
                (f"{compare_label}: mães com menos de 20 anos", pct(compare.get("nasc_mae_menor_20") or 0, compare.get("nasc_idade_conhecida"))),
                ("Prematuros (menos de 37 semanas)", pct(row.get("nasc_pretermo") or 0, row.get("nasc_gestacao_conhecida"))),
                (f"{compare_label}: prematuros", pct(compare.get("nasc_pretermo") or 0, compare.get("nasc_gestacao_conhecida")))]

    def e_teen_district(self):
        d = self.p.get("district")
        return (f"Nascimentos no distrito {d.get('nm_dist')} (SMS-SP, 2022–2024)", self.births(d, self.p.get("city") or {}, "Cidade de São Paulo")) if d else None

    def e_teen(self):
        m = self.p.get("municipality") or {}
        return (f"Nascimentos no município de {m.get('nome')} (2022–2024)", self.births(m, self.p.get("region") or {}, "Região metropolitana"))

    e_preterm = e_teen

    def e_mortality(self):
        m, g = self.p.get("municipality") or {}, self.p.get("region") or {}
        defined = lambda r: (r.get("obitos_total") or 0) - (r.get("obitos_cap_xviii") or 0)  # noqa: E731
        top = max(CAUSES, key=lambda c: m.get(f"obitos_cap_{c}") or 0)
        return (f"Óbitos de 30 a 69 anos no município de {m.get('nome')} (2022–2024)",
                [("Óbitos com causa definida", br(defined(m))),
                 ("Causa mais frequente entre os de causa definida", f"{CAUSES[top]}: {pct(m.get(f'obitos_cap_{top}') or 0, defined(m))}"),
                 ("Região metropolitana, mesma causa", pct(g.get(f"obitos_cap_{top}") or 0, defined(g))),
                 ("Óbitos sem causa definida", pct(m.get("obitos_cap_xviii") or 0, m.get("obitos_total")))])

    def surprise(self, outcome, label, period):
        row = next((e for e in self.p.get("expected") or [] if e.get("scale") == "district" and e.get("outcome") == outcome), None)
        if not row:
            return None
        return (f"{label} no distrito {row['name']}: observado e esperado pelo modelo ({period})",
                [("Observados", br(row["observed"])), ("Esperados pelo modelo", br(row["expected"], 1)),
                 ("Faixa de previsão de 95%", f"{br(row['lower'], 1)} a {br(row['upper'], 1)}")])

    def e_surprise_tb(self):
        return self.surprise("tb", "Tuberculose", "2022–2025")

    def e_surprise_teen(self):
        return self.surprise("teen", "Nascimentos de mães com menos de 20 anos", "2022–2024")


def statement(title, rows):
    """One E2 candidate: the fact's topic and its first figures."""
    return f"{title}: " + "; ".join(f"{label}: {value}" for label, value in rows[:3])


def storyteller(*args):
    exe = os.environ.get("STORYTELLER", "storyteller")
    env = {**os.environ, "STORY_CONFIG_DIR": str(BACKEND / "config")}
    return json.loads(subprocess.run([exe, *args], check=True, capture_output=True, text=True, env=env).stdout)


# What to check in a sentence that is a caveat, not a fact: whether the warning holds for this unit
CAVEAT_CHECK = {
    "C10": "Esta frase é um aviso sobre a escala, sem valor para conferir. Confira se os números das frases "
           "seguintes são mesmo da escala que ela anuncia (distrito ou município): o título dos dados abaixo diz de onde eles são.",
    "C01": "Esta frase é um aviso, sem números. Confira se ele vale para esta unidade: ela é um hospital de grande "
           "porte, ou há um no raio? Os dados abaixo ajudam a conferir.",
    "C14b": "Esta frase é um aviso, sem números. Confira se ele vale: os dados abaixo mostram muitos serviços "
            "privados no raio?",
    "C23": "Esta frase explica como o esperado foi calculado e o que ele deixa de fora, sem números. Confira se ela "
           "é coerente com os dados de óbitos abaixo; os valores são conferidos na frase dos óbitos.",
}
CAVEAT_WITHOUT_NUMBERS = ("Esta frase é um aviso, sem números para conferir. Confira se ele vale para esta unidade e "
                          "para os dados abaixo; os valores são conferidos nas outras frases.")
CAVEAT_WITH_NUMBERS = "Esta frase é um aviso com números: confira os números e se o aviso vale para esta unidade."


# Scale of each left-out fact, shown next to it in step 2
FACT_SCALE = {
    **dict.fromkeys(["profile", "beds", "staff", "admissions", "deaths", "casemix", "stay", "position"], "Unidade"),
    **dict.fromkeys(["residents", "territory", "sewage", "precarious", "garbage", "crowding", "crowded",
                     "access", "network", "peer"], "Raio de 1 km"),
    "need_supply": "Área de atendimento",
    **dict.fromkeys(["tb_district", "teen_district", "surprise_tb", "surprise_teen"], "Distrito"),
    **dict.fromkeys(["tb", "dengue", "lepto", "mortality", "teen", "preterm"], "Município"),
}


def caveat_check(rule, has_numbers):
    if has_numbers:
        return CAVEAT_WITH_NUMBERS
    return CAVEAT_CHECK.get(rule.split(".")[0], CAVEAT_WITHOUT_NUMBERS)


def draw_units():
    """20 of the 40, 2 or 3 per stratum, the strata that get a third one drawn at random."""
    rows = list(csv.DictReader(open(EVAL / "sample.csv")))
    by_stratum = defaultdict(list)
    for row in rows:
        by_stratum[row["stratum"]].append(row)
    rng = random.Random(SEED)
    strata = sorted(by_stratum)
    extra = set(rng.sample(strata, UNITS - 2 * len(strata)))
    chosen = []
    for stratum in strata:
        chosen += rng.sample(sorted(by_stratum[stratum], key=lambda r: r["cnes"]), 3 if stratum in extra else 2)
    return chosen


def draw_llm_units(rows):
    """4 of the 20, from 4 different strata, with a free LLM text (../llm)."""
    rng = random.Random(f"{SEED}:llm")
    by_stratum = defaultdict(list)
    for row in rows:
        by_stratum[row["stratum"]].append(row["cnes"])
    return [rng.choice(sorted(by_stratum[s])) for s in rng.sample(sorted(by_stratum), LLM_UNITS)]


def draw_annotated(rows, llm_units):
    """The 10 annotated units, a subset of the 20: 2 of the LLM units, whose text in E4 is the LLM's,
    then one unit for every other stratum and 2 more from 2 strata drawn at random."""
    rng = random.Random(f"{SEED}:annotated")
    by_cnes = {r["cnes"]: r for r in rows}
    llm = rng.sample(sorted(llm_units), ANNOTATED_LLM)
    chosen = [by_cnes[c] for c in llm]
    covered = {r["stratum"] for r in chosen}
    rest = sorted((r for r in rows if r["cnes"] not in llm_units), key=lambda r: r["cnes"])
    for stratum in sorted({r["stratum"] for r in rows} - covered):
        chosen.append(rng.choice([r for r in rest if r["stratum"] == stratum]))
    left = [r for r in rest if r not in chosen]
    for stratum in rng.sample(sorted({r["stratum"] for r in left}), ANNOTATED - len(chosen)):
        chosen.append(rng.choice([r for r in left if r["stratum"] == stratum]))
    return chosen, set(llm)


def claims(text):
    """Every number written in the sentence, years and percentages included."""
    return len(re.findall(r"\d[\d.]*(?:,\d+)?", text))


def llm_sentences(cnes, body, for_fact):
    import sys  # noqa: PLC0415

    sys.path.insert(0, str(EVAL / "llm"))
    from score_llm import Catalog, align, clean  # noqa: PLC0415 (score_llm imports this module)

    path = LLM_TEXTS / f"{cnes}_free_s0.json"
    if not path.exists():
        raise SystemExit(f"{path.name} is missing: run ../llm/run_llm.py --jobs annotation first")
    record = json.loads(path.read_text())
    catalog = Catalog(body, record["user"], blocks={fid: block for p in body["plan"] for fid in p if (block := for_fact(fid))})
    sentences, told = [], {}
    for pi, paragraph in enumerate(clean(record["response"])):
        for si, text in enumerate(paragraph):
            aligned = align(text, catalog)[0]
            fids = [f for f in dict.fromkeys(re.findall(r"\{(\w+)\.", aligned)) if f != "k"]
            data = [{"title": t, "rows": r} for t, r in filter(None, map(for_fact, fids))]
            sentences.append({"id": f"p{pi}s{si}", "text": text, "data": data, "claims": claims(text)})
            told[f"p{pi}s{si}"] = {"facts": fids, "caveats": []}
    meta = {"model": record["model"], "digest": record["digest"], "llm_file": path.name}
    return sentences, meta, told


def main():
    reference = load_reference()
    adm = admissions_labels()
    units, system = [], {}
    rows, llm_units = draw_annotated(draw_units(), draw_llm_units(draw_units()))
    for row in rows:
        path = EVAL / "fixtures" / f"{row['cnes']}_1000.json"
        payload = json.loads(path.read_text())
        body = storyteller("narrate", str(path), "pt")
        evidence = Evidence(payload, reference, adm)
        uid = "u" + hashlib.sha1(row["cnes"].encode()).hexdigest()[:6]
        facts = [f["id"] for f in body["facts"]]
        peer_key = next((f["slots"]["indicator"]["key"].split(":")[1] for f in body["facts"] if f["id"] == "peer"), None)

        def for_fact(fid):
            return evidence.e_peer(peer_key) if fid == "peer" else evidence.get(fid)

        planned_ids = [fid for para in body["plan"] for fid in para]
        rng = random.Random(f"omitted:{uid}")
        # facts that share one data box (births: mothers under 20 and preterm) are one statement
        left_out, blocks = defaultdict(list), {}
        for fid in facts:
            if fid not in planned_ids and for_fact(fid):
                text = statement(*for_fact(fid))
                left_out[text].append(fid)
                blocks[text] = for_fact(fid)
        shown = rng.sample(sorted(left_out), min(OMITTED, len(left_out)))
        omitted = [{"id": f"o{n}", "title": blocks[text][0], "rows": blocks[text][1],
                    "scale": FACT_SCALE.get(left_out[text][0], "")} for n, text in enumerate(shown)]
        fact_of = {f"o{n}": "+".join(left_out[text]) for n, text in enumerate(shown)}

        caveat_fact = {c["rule"]: c["fact"] for c in body["caveats"]}
        llm = {}
        if row["cnes"] in llm_units:
            sentences, llm, told = llm_sentences(row["cnes"], body, for_fact)
        else:
            sentences, told = [], {}
            for pi, paragraph in enumerate(body["paragraphs"]):
                for si, sentence in enumerate(paragraph):
                    text = "".join(seg["text"] for seg in sentence["segments"]).strip()
                    fids = list(dict.fromkeys(sentence["facts"] + [caveat_fact[r] for r in sentence["caveats"] if r in caveat_fact]))
                    data = [{"title": t, "rows": r} for t, r in filter(None, map(for_fact, fids))]
                    item = {"id": f"p{pi}s{si}", "text": text, "data": data, "claims": claims(text)}
                    if not sentence["facts"] and sentence["caveats"]:
                        item.update(kind="caveat", check=caveat_check(sentence["caveats"][0], item["claims"] > 0))
                    sentences.append(item)
                    told[f"p{pi}s{si}"] = {"facts": sentence["facts"], "caveats": sentence["caveats"]}
        name = (payload["facility"].get("NO_FANTASIA") or payload["facility"].get("NO_RAZAO_SOCIAL") or "").strip()
        units.append({"id": uid, "name": name, "type": payload["facility"].get("tipo_equipamento"),
                      "sentences": sentences, "omitted": omitted,
                      "data": [{"title": t, "rows": r} for t, r in filter(None, map(for_fact, planned_ids))]})
        system[uid] = {
            "cnes": row["cnes"], "stratum": row["stratum"],
            "condition": "llm_free" if llm else "template", **llm,
            "planned": planned_ids,
            "omitted_fact": fact_of,
            "omitted_available": len(left_out),
            # what each sentence tells, for the relevance judgements (E2b); facts aligned by number in LLM texts
            "sentences": told,
            "verified": body["verified"],
        }
    tasks = {"version": body["version"] + "-5", "units": units}
    (HERE / "tasks.js").write_text("window.ANNOTATION_TASKS = " + json.dumps(tasks, ensure_ascii=False) + ";\n")
    (HERE / "system.json").write_text(json.dumps(system, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(units)} units, {sum(len(u['sentences']) for u in units)} sentences, "
          f"{sum(s['claims'] for u in units for s in u['sentences'])} claims, "
          f"{sum(1 for u in units for s in u['sentences'] if not s['data'])} sentences without data")


if __name__ == "__main__":
    main()
