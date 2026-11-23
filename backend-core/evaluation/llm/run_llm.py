"""Generate the "Leitura do território" texts with a free LLM, for the comparison with the templates.

Both conditions start from the system's content plan (the same facts and caveats the templates
tell), so the comparison is about realisation only:
  free     the model writes the text from the facts' data, as shown to the annotators (the
           "Dados para conferir" boxes of build_tasks.py), and the caveats each fact requires;
  rewrite  the model rewrites the template text, keeping the {fact.field} tokens, so that the
           verifier can check it before any number is filled in (Kasner & Dušek 2022).

Every answer is saved with the prompt, the model digest and the decoding options, one file per
facility, condition and seed, under evaluation/results/llm/. Files already there are skipped, so
the run can be stopped and resumed.

    STORYTELLER=path/to/storyteller python3 backend-core/evaluation/llm/run_llm.py [--jobs annotation|main|variation|all]

Ollama by default (gemma4:e4b on localhost). Any OpenAI-compatible endpoint works with
--provider openai --base-url URL --model NAME and the key in LLM_API_KEY.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
sys.path.insert(0, str(EVAL / "annotation"))
import build_tasks  # noqa: E402

OUT = EVAL / "results" / "llm"
MAX_WORDS = 340
VARIATION_UNITS = 5
VARIATION_SEEDS = [1, 2, 3]

SYSTEM_FREE = """Você escreve a seção “Leitura do território” da página de uma unidade de saúde no CulturaEduca, uma plataforma pública de mapas. O leitor é alguém da comunidade, da educação ou da gestão, sem formação em estatística.

Escreva em português, usando só os dados fornecidos:
- Siga a ordem dos parágrafos dados e escreva um parágrafo para cada um.
- Conte todos os dados listados, e nenhum outro. Não invente números; você pode arredondar.
- Todo número deve dizer, na mesma frase, a que área se refere: o raio em volta da unidade, a área de atendimento, o distrito, a cidade, o município ou a região metropolitana.
- Inclua cada aviso obrigatório junto do dado a que ele se refere.
- Não diga que um fator causa, explica ou contribui para outro: os dados mostram só que as coisas aparecem juntas.
- No máximo {max_words} palavras.
- Responda só com o texto, sem título, sem listas e sem formatação."""

SYSTEM_REWRITE = """Você revisa a seção “Leitura do território” da página de uma unidade de saúde no CulturaEduca, uma plataforma pública de mapas. O texto foi montado com modelos de frase e soa repetitivo. Reescreva-o para ficar mais claro e natural para alguém da comunidade, da educação ou da gestão.

Regras:
- Os números aparecem como marcadores entre chaves, por exemplo {{residents.radius}}. Copie cada marcador exatamente como está e não escreva nenhum número, nem em algarismos nem por extenso.
- Mantenha todos os marcadores e todas as informações; não acrescente informação.
- Mantenha, na mesma frase de cada marcador, a área a que ele se refere (raio, área de atendimento, distrito, cidade, município, região metropolitana).
- Copie sem nenhuma alteração as frases marcadas com [AVISO], tirando só a marca.
- Mantenha as palavras de comparação (acima de, abaixo de, próximo de, vezes) com o mesmo sentido.
- Não diga que um fator causa, explica ou contribui para outro.
- Mantenha a divisão em parágrafos; dentro de um parágrafo, você pode juntar ou reordenar frases.
- No máximo {max_words} palavras, contando cada marcador como uma palavra.
- Responda só com o texto, sem título e sem formatação."""

# Caveats the templates carry inside the fact's own sentence, so they have no statement of their
# own: what the free condition is told to say instead (docs: data-storytelling notes).
QUALIFIERS = {
    "C03": "os números de moradores e domicílios são estimativas a partir do Censo: use “cerca de” ou “estimativa”.",
    "C05": "a posição da unidade no mapa é aproximada ou foi substituída pela do endereço: diga isso.",
    "C07": "os números de médicos e enfermeiros contam vínculos registrados no CNES, não pessoas: use a palavra “vínculos”.",
    "C08": "internações e permanência se referem só ao atendimento pelo SUS: diga “pelo SUS”.",
    "C09": "as distâncias são em linha reta: diga “em linha reta”.",
    "C12.current": "o ano mais recente foi ano de epidemia de dengue: diga isso.",
    "C13": "os casos de tuberculose são contados pelo município de residência: diga que são casos entre os moradores.",
    "C15": "os números de casos são pequenos: dê o número de casos e não use palavras de comparação.",
    "C16": "a taxa do distrito conta só moradores com endereço; pessoas sem residência fixa ficam de fora: diga isso.",
    "C18": "o perfil de causas considera só os óbitos com causa definida: diga “com causa definida”.",
    "C21": "em área esparsa, poucas pessoas por unidade não indica oferta folgada: diga isso.",
}


def key_phrase(c):
    """The words of the statement that the verifier's marker finds, whole."""
    m = re.search(c["marker"], c["statement"], re.I)
    if not m:
        return None
    start = c["statement"].rfind(" ", 0, m.start()) + 1
    end = c["statement"].find(" ", m.end())
    return c["statement"][start:end if end >= 0 else None].strip(".,;:")


def caveat_instruction(c):
    if c["statement"]:
        if c["effect"] == "qualify":
            return f"diga, na mesma frase do dado: “{c['statement']}”"
        where = "antes deste dado" if c["before"] else "junto deste dado"
        phrase = key_phrase(c)
        keep = f", mantendo a expressão “{phrase}”" if phrase else ""
        return f"inclua {where} o aviso a seguir, com estas ou outras palavras{keep}: “{c['statement']}”"
    key = f"{c['rule']}.{c['variant']}" if c["variant"] else c["rule"]
    return QUALIFIERS.get(key) or QUALIFIERS.get(c["rule"])


class Facility:
    """The plan, the template text and the facts' data for one fixture."""

    def __init__(self, path, reference, adm):
        self.path = path
        self.cnes = path.name.split("_")[0]
        self.payload = json.loads(path.read_text())
        self.body = build_tasks.storyteller("narrate", str(path), "pt")
        self.caveats = build_tasks.storyteller("caveats", str(path), "pt")
        self.evidence = build_tasks.Evidence(self.payload, reference, adm)
        f = self.payload["facility"]
        self.name = (f.get("NO_FANTASIA") or f.get("NO_RAZAO_SOCIAL") or "").strip()
        self.peer_key = next((x["slots"]["indicator"]["key"].split(":")[1] for x in self.body["facts"] if x["id"] == "peer"), None)

    def aliases(self):
        """Words of the facts' data, as the model received them, for facts told only in words."""
        out = {"profile": [self.name]}
        for fact in self.body["facts"]:
            block = self.data(fact["id"])
            if block:
                out.setdefault(fact["id"], []).extend(v for _, v in block[1] if isinstance(v, str))
        return out

    def blocks(self):
        """The data box of every planned fact, by fact id."""
        return {fid: block for p in self.body["plan"] for fid in p if (block := self.data(fid))}

    def data(self, fid):
        return self.evidence.e_peer(self.peer_key) if fid == "peer" else self.evidence.get(fid)

    def free_prompt(self):
        lines = [f"Unidade: {self.name} ({self.payload['facility'].get('tipo_equipamento')})"]
        for n, paragraph in enumerate([p for p in self.body["plan"] if p], 1):
            lines += ["", f"Parágrafo {n}"]
            for fid in paragraph:
                block = self.data(fid)
                if block:
                    title, rows = block
                    lines.append(f"Dado: {title}")
                    lines += [f"- {label}: {value}" for label, value in rows]
                for c in self.caveats:
                    if c["fact"] == fid:
                        instruction = caveat_instruction(c)
                        if instruction:
                            lines.append(f"- Aviso obrigatório: {instruction}")
        return SYSTEM_FREE.format(max_words=MAX_WORDS), "\n".join(lines)

    def rewrite_prompt(self):
        lines = []
        for paragraph, rendered in zip(self.body["slotted"], self.body["paragraphs"]):
            if lines:
                lines.append("")
            for text, sentence in zip(paragraph, rendered):
                aviso = not sentence["facts"] and sentence["caveats"]
                lines.append(("[AVISO] " if aviso else "") + text)
        values = []
        for fact in self.body["facts"]:
            if not any(fact["id"] in p for p in self.body["plan"]):
                continue
            for field, slot in fact["slots"].items():
                scope = f" ({slot['scope']})" if slot.get("scope") else ""
                values.append(f"{{{fact['id']}.{field}}} = {slot['text']}{scope}")
        user = "\n".join(lines) + "\n\nValores dos marcadores, só para referência (não os escreva):\n" + "\n".join(values)
        return SYSTEM_REWRITE.format(max_words=MAX_WORDS), user


def post(url, body, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=3600) as response:
        return json.loads(response.read())


def generate(args, system, user, seed, temperature):
    started = time.time()
    if args.provider == "ollama":
        options = {"seed": seed, "temperature": temperature, "num_ctx": args.num_ctx, "num_predict": 900,
                   "num_thread": args.threads}
        if temperature > 0:
            options.update(top_p=0.95, top_k=64)  # Gemma's recommended sampling
        r = post(f"{args.base_url}/api/chat", {"model": args.model, "stream": False, "think": False, "options": options,
                                               "messages": [{"role": "system", "content": system},
                                                            {"role": "user", "content": user}]})
        return r["message"]["content"], options, {
            "prompt_tokens": r.get("prompt_eval_count"), "output_tokens": r.get("eval_count"),
            "prompt_s": round((r.get("prompt_eval_duration") or 0) / 1e9, 1),
            "output_s": round((r.get("eval_duration") or 0) / 1e9, 1), "total_s": round(time.time() - started, 1)}
    options = {"seed": seed, "temperature": temperature, "max_tokens": 900}
    if temperature > 0:
        options["top_p"] = 0.95
    r = post(f"{args.base_url}/chat/completions", {"model": args.model, **options,
                                                   "messages": [{"role": "system", "content": system},
                                                                {"role": "user", "content": user}]},
             os.environ.get("LLM_API_KEY"))
    usage = r.get("usage") or {}
    return r["choices"][0]["message"]["content"], options, {
        "prompt_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
        "total_s": round(time.time() - started, 1), "served_model": r.get("model")}


def model_digest(args):
    if args.provider != "ollama":
        return None
    tags = json.loads(urllib.request.urlopen(f"{args.base_url}/api/tags").read())["models"]
    return next((m["digest"] for m in tags if m["name"] == args.model), None)


def jobs(kind):
    """(cnes, condition, seed, temperature), in the order they are needed."""
    rows = build_tasks.draw_units()
    units = [r["cnes"] for r in rows]
    llm_units = build_tasks.draw_llm_units(rows)
    out = []
    if kind in ("annotation", "main", "all"):
        out += [(c, "free", 0, 0.0) for c in llm_units]
    if kind in ("main", "all"):
        out += [(c, cond, 0, 0.0) for c in units for cond in ("free", "rewrite")]
    if kind in ("variation", "all"):
        out += [(c, "free", s, 1.0) for c in units[:VARIATION_UNITS] for s in VARIATION_SEEDS]
    if kind == "all":
        sample = [p.name.split("_")[0] for p in sorted((EVAL / "fixtures").glob("*.json"))] + \
                 [p.name.split("_")[0] for p in sorted((EVAL / "fixtures_need").glob("*.json"))]
        out += [(c, cond, 0, 0.0) for c in sample if c not in units for cond in ("free", "rewrite")]
    seen, ordered = set(), []
    for job in out:
        if job not in seen:
            seen.add(job)
            ordered.append(job)
    return ordered


def fixture(cnes):
    for folder in ("fixtures", "fixtures_need"):
        path = EVAL / folder / f"{cnes}_1000.json"
        if path.exists():
            return path
    raise FileNotFoundError(cnes)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jobs", default="main", choices=["annotation", "main", "variation", "all"])
    parser.add_argument("--provider", default="ollama", choices=["ollama", "openai"])
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--num-ctx", type=int, default=6144)
    args = parser.parse_args()

    reference, adm = build_tasks.load_reference(), build_tasks.admissions_labels()
    digest = model_digest(args)
    folder = OUT / args.model.replace(":", "_").replace("/", "_")
    folder.mkdir(parents=True, exist_ok=True)
    todo = jobs(args.jobs)
    for n, (cnes, condition, seed, temperature) in enumerate(todo, 1):
        path = folder / f"{cnes}_{condition}_s{seed}.json"
        if path.exists():
            continue
        facility = Facility(fixture(cnes), reference, adm)
        system, user = facility.free_prompt() if condition == "free" else facility.rewrite_prompt()
        text, options, stats = generate(args, system, user, seed, temperature)
        record = {"cnes": cnes, "condition": condition, "seed": seed, "provider": args.provider, "model": args.model,
                  "digest": digest, "options": options, "storyteller_version": facility.body["version"],
                  "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stats": stats,
                  "system": system, "user": user, "response": text}
        path.with_suffix(".tmp").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n")
        path.with_suffix(".tmp").rename(path)
        print(f"[{n}/{len(todo)}] {path.name}: {stats.get('output_tokens')} tokens in {stats['total_s']} s", flush=True)


if __name__ == "__main__":
    main()
