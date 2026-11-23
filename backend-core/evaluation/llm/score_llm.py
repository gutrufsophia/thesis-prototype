"""Score the LLM texts of run_llm.py with the same verifier the templates pass.

rewrite  the answer still carries {fact.field} tokens and goes to the verifier as it is. A text that
         fails would not be served: the page falls back to the template.
free     the answer has literal numbers. Each one is aligned with the slot it most plausibly
         renders, resolving ambiguity in the model's favour:
           - a number counts as a slot's value when it is that value correctly rounded at the
             precision written ("cerca de 28 mil" for 28.414; the annotation guide accepts it too);
           - among several such slots, the one of a fact already aligned in the sentence, then the
             one whose scale is named in the sentence, then the closest;
           - a number that is in the data the model received but in no slot (a census tract count,
             say) is set aside, not counted as invented.
         The aligned text then goes to the verifier. Two checks are read differently: V1 counts
         numbers traced to nothing the model received, and V4 is replaced by a looser check, the
         caveat's marker anywhere in the text, since a free text cannot be expected to copy a
         disclosure word for word. V5 needs the verifier's scale words ("raio", "município"...),
         which the prompt lists; a scale named otherwise counts as missing, so V5 is an upper bound
         to be read with the human annotation.

    STORYTELLER=path/to/storyteller python3 backend-core/evaluation/llm/score_llm.py [MODEL_DIR]
"""

import itertools
import json
import math
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
sys.path.insert(0, str(EVAL / "annotation"))
sys.path.insert(0, str(HERE))
import build_tasks  # noqa: E402
from run_llm import Facility, fixture  # noqa: E402

PT = json.loads((EVAL.parent / "config" / "pt.json").read_text())
NUMBER = re.compile(r"(R\$\s?)?(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)(\s?%|\s(?:mil|milhões|milhão)\b|\s?km\b|\s?m\b|[ªº])?")
RANK = re.compile(r"\b(?:N|\d+[ªº]) (?:maior|menor)\b", re.I)  # a position: "a 6ª menor e a 91ª maior taxa"
MARKUP = re.compile(r"\[AVISO\]|\*\*|^\s*#|^\s*[-*•] ", re.M)
SCOPE_WORDS = {scope: [re.compile(p, re.I) for p in patterns] for scope, patterns in PT["scope_markers"].items()}
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-Ú0-9{«“\"(])")


def parse(match):
    """Value of a written number and the rounding step its precision implies."""
    digits, suffix = match.group(2), (match.group(3) or "").strip()
    integer, _, decimals = digits.replace(".", "").partition(",")
    value = float(f"{integer}.{decimals}" if decimals else integer)
    if decimals:
        step = 10 ** -len(decimals)
    else:
        zeros = len(integer) - len(integer.rstrip("0")) if integer.strip("0") else 0
        step = 10 ** zeros
    scale = {"mil": 1e3, "milhão": 1e6, "milhões": 1e6, "km": 1e3}.get(suffix, 1)
    return value * scale, step * scale, suffix


def clean(response):
    """Paragraphs of sentences, without Markdown emphasis or headings (tokens keep their underscores)."""
    text = re.sub(r"\*\*|__|`", "", response)
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M).strip()
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    return [SENTENCE_END.split(p) for p in paragraphs if p]


class Catalog:
    """Slots of the planned facts, the constants, and every number the model was given."""

    def __init__(self, body, prompt, aliases=None, blocks=None):
        planned = {fid for p in body["plan"] for fid in p}
        self.values, self.texts, self.inside = [], [], []
        with_values = set()
        for fact in body["facts"]:
            if fact["id"] not in planned:
                continue
            for field, slot in fact["slots"].items():
                entry = {"token": f"{{{fact['id']}.{field}}}", "fact": fact["id"], "text": slot["text"],
                         "scope": slot.get("scope")}
                m = NUMBER.search(slot["text"])
                if m and m.group(0).strip() == slot["text"].strip():
                    entry["shown"], _, entry["suffix"] = parse(m)
                    entry["value"] = slot.get("value", entry["shown"])  # an estimate is shown rounded
                    self.values.append(entry)
                    with_values.add(fact["id"])
                elif len(slot["text"]) >= 4:
                    self.texts.append(entry)
                    # a period or name with a year, rephrased: its years still point to the slot
                    self.inside += [{**entry, "value": float(n)} for n in re.findall(r"\d{4}", slot["text"])]
        self.textual_facts = planned - with_values  # told only in words, like the unit's profile
        # the same facts in the words of the data the model received (the CNES type, the unit's name)
        for fid, names in (aliases or {}).items():
            token = next((e["token"] for e in self.texts if e["fact"] == fid), None)
            if fid in self.textual_facts and token:
                self.texts += [{"token": token, "fact": fid, "text": w, "scope": None} for w in names if len(w) >= 8]
        self.scopes = {e["token"]: e["scope"] for e in self.values if e["scope"] not in (None, "unit")}
        self.constants = {v: f"{{k.{k}}}" for k, v in PT["constants"].items()}
        self.given = [parse(m) for m in NUMBER.finditer(prompt)]
        # each fact's data box as the model received it: its words, to tell apart facts that share a
        # value, and its numbers, which are not all slots
        self.words, self.box_numbers = {}, []
        for fid, (title, rows) in (blocks or {}).items():
            text = " ".join([title] + [f"{label} {value}" for label, value in rows])
            self.words[fid] = words(text)
            self.box_numbers += [{"fact": fid, "value": parse(m)[0], "suffix": parse(m)[2]} for m in NUMBER.finditer(text)]

    def value_candidates(self, value, step, suffix, written):
        if suffix in ("ª", "º"):  # a position in a ranking, never a slot value
            return []
        close = lambda v: abs(v - value) <= step / 2 + 1e-9 * max(1, abs(value))  # noqa: E731
        return [s for s in self.values if (s["suffix"] == "%") == (suffix == "%")
                and (s["text"] == written or close(s["value"]) or close(s["shown"]))]

    def box_candidates(self, value, step, suffix):
        return [{"fact": b["fact"], "aside": True} for b in self.box_numbers
                if (b["suffix"] == "%") == (suffix == "%") and abs(b["value"] - value) <= step / 2 + 1e-9 * max(1, abs(value))]

    def given_number(self, value, step):
        return any(abs(v - value) <= step / 2 + 1e-9 * max(1, abs(value)) for v, _, _ in self.given)


def words(text):
    return {w for w in re.findall(r"[a-zà-ú]{4,}", text.lower())}


def align(sentence, catalog):
    """The sentence with each number, and each verbatim text slot of a fact it tells, replaced by the
    slot's token; then how many numbers were aligned, how many set aside, and the untraced ones."""
    spans, taken = [], []

    def free(a, b):
        return all(b <= x or a >= y for x, y in taken)

    lower = sentence.lower()
    for entry in sorted(catalog.texts, key=lambda e: -len(e["text"])):
        for m in re.finditer(re.escape(entry["text"].lower()), lower):
            if free(m.start(), m.end()):
                spans.append({"start": m.start(), "end": m.end(), "kind": "text", "text": entry["text"]})
                taken.append((m.start(), m.end()))
    for m in NUMBER.finditer(sentence):
        if not free(m.start(), m.end()):
            continue
        written = m.group(0).strip()
        value, step, suffix = parse(m)
        options = catalog.value_candidates(value, step, suffix, written)
        exact = any(o["text"] == written for o in options)
        if written in catalog.constants and not exact:
            spans.append({"start": m.start(), "end": m.end(), "kind": "constant", "token": catalog.constants[written]})
        else:
            near = words(sentence[max(0, m.start() - 80):m.end() + 80])
            options += catalog.box_candidates(value, step, suffix)
            spans.append({"start": m.start(), "end": m.end(), "kind": "number", "written": written,
                          "value": value, "step": step, "options": options,
                          "overlap": {o["fact"]: len(near & catalog.words.get(o["fact"], set())) for o in options}})
        taken.append((m.start(), m.end()))

    scopes = {scope for scope, patterns in SCOPE_WORDS.items() if any(p.search(sentence) for p in patterns)}
    facts = {o["fact"] for s in spans if s["kind"] == "number" and len({o["fact"] for o in s["options"]}) == 1
             for o in s["options"]}
    told = set()  # facts with a slot value in the sentence: only their words become tokens
    for s in spans:  # values first: the fact whose data box shares most words with the context
        if s["kind"] == "number" and s["options"]:
            s["options"].sort(key=lambda o: (-s["overlap"][o["fact"]], o["fact"] not in facts, o.get("aside", False),
                                             o.get("text") != s["written"], not (o.get("scope") and o["scope"] in scopes),
                                             abs(o.get("value", s["value"]) - s["value"])))
            best = s["options"][0]
            s["token"] = "N" if best.get("aside") else best["token"]
            facts.add(best["fact"])
            if not best.get("aside"):
                told.add(best["fact"])
    untraced, set_aside, aligned = [], 0, 0
    for s in spans:  # then words and rephrased years, only for facts the sentence tells
        if s.get("token") == "N":
            set_aside += 1
        elif s["kind"] == "text":
            options = [e for e in catalog.texts if e["text"] == s["text"]
                       and (e["fact"] in told or e["fact"] in catalog.textual_facts)]
            s["token"] = options[0]["token"] if options else None
        elif s["kind"] == "number" and not s["options"]:
            inside = [e for e in catalog.inside if e["value"] == s["value"] and e["fact"] in told]
            if inside:
                s["token"] = inside[0]["token"]
            elif catalog.given_number(s["value"], s["step"]):
                s["token"], set_aside = "N", set_aside + 1
            else:
                s["token"] = None
                untraced.append(s["written"])
        if s["kind"] == "number" and s.get("token") and s["token"] != "N":
            aligned += 1
    out, last = [], 0
    for s in sorted(spans, key=lambda x: x["start"]):
        out.append(sentence[last:s["start"]] + (s.get("token") or sentence[s["start"]:s["end"]]))
        last = s["end"]
    out.append(sentence[last:])
    return "".join(out), aligned, set_aside, untraced


def nearest_scale(paragraphs, catalog):
    """V5 read loosely: the scale word right before a value or the one right after it, in its
    sentence, must be the value's own scale. The verifier asks for it inside the value's clause,
    which a free text need not follow ("No raio de 1 km, 3% dos domicílios..."). Looser than the
    verifier: of two values whose scales are swapped, it may catch only one."""
    issues = []
    for pi, paragraph in enumerate(paragraphs):
        for si, sentence in enumerate(paragraph):
            markers = [(m.start(), scope) for scope, patterns in SCOPE_WORDS.items()
                       for p in patterns for m in p.finditer(sentence)]
            for m in re.finditer(r"\{\w+\.\w+\}", sentence):
                scope = catalog.scopes.get(m.group(0))
                if not scope:
                    continue
                if not markers:
                    issues.append({"check": "V5", "paragraph": pi, "sentence": si, "detail": f"{m.group(0)} has no scale word"})
                    continue
                before = [sc for pos, sc in sorted(markers) if pos < m.start()]
                after = [sc for pos, sc in sorted(markers) if pos > m.start()]
                neighbours = ([before[-1]] if before else []) + ([after[0]] if after else [])
                if scope not in neighbours:
                    issues.append({"check": "V5", "paragraph": pi, "sentence": si,
                                   "detail": f"{m.group(0)} ({scope}) between {'/'.join(neighbours)} words"})
    return issues


def verify(cnes, paragraphs):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(paragraphs, f, ensure_ascii=False)
    exe = build_tasks.os.environ.get("STORYTELLER", "storyteller")
    env = {**build_tasks.os.environ, "STORY_CONFIG_DIR": str(EVAL.parent / "config")}
    result = subprocess.run([exe, "verify", str(fixture(cnes)), "pt", f.name], capture_output=True, text=True, env=env, check=True)
    Path(f.name).unlink()
    return json.loads(result.stdout)


def score(record, cache):
    cnes = record["cnes"]
    if cnes not in cache:
        cache[cnes] = Facility(fixture(cnes), *REFERENCE)
    facility = cache[cnes]
    body, caveats = facility.body, facility.caveats
    paragraphs = clean(record["response"])
    plain = " ".join(s for p in paragraphs for s in p)
    out = {"cnes": cnes, "condition": record["condition"], "seed": record["seed"], "stats": record["stats"],
           "paragraphs": len(paragraphs), "template_paragraphs": len(body["slotted"]),
           # instructions left in the text, or Markdown, which the page would show as is
           "markup": bool(MARKUP.search(record["response"]))}
    if record["condition"] == "rewrite":
        result = verify(cnes, paragraphs)
        # the verifier gates what is served; the loose V5 tells strict rejections from scale errors
        loose = [i for i in result["issues"] if i["check"] != "V5"]
        loose += nearest_scale(paragraphs, Catalog(body, record["user"]))
        out["verified_loose_v5"] = not loose
        template = {s for p in body["slotted"] for s in p}
        sentences = [s for p in paragraphs for s in p]
        out["unchanged_sentences"] = round(sum(s in template for s in sentences) / max(1, len(sentences)), 3)
        out["literal_numbers"] = sum(len(NUMBER.findall(re.sub(r"\{[^}]*\}", "", s))) for s in sentences)
    else:
        catalog = Catalog(body, record["user"], facility.aliases(), facility.blocks())
        aligned_paragraphs, counts = [], Counter()
        # "a 5ª menor e a 92ª maior taxa" is a position, not a comparison word for V6
        untraced = []
        for p in paragraphs:
            row = []
            for s in p:
                text, a, n, u = align(s, catalog)
                row.append(RANK.sub("N posição", text))
                counts["aligned"] += a
                counts["set_aside"] += n
                untraced += u
            aligned_paragraphs.append(row)
        result = verify(cnes, aligned_paragraphs)
        out["strict_v5"] = sum(1 for i in result["issues"] if i["check"] == "V5")
        result["issues"] = [i for i in result["issues"] if i["check"] not in ("V4", "V5")]
        result["issues"] += nearest_scale(aligned_paragraphs, catalog)
        missing = [c["rule"] for c in caveats if not re.search(c["marker"], plain, re.I)]
        result["issues"] += [{"check": "V4", "detail": f"caveat {r}: marker not found"} for r in missing]
        result["verified"] = not result["issues"]
        out.update(numbers=counts["aligned"] + counts["set_aside"] + len(untraced), aligned=counts["aligned"],
                   set_aside=counts["set_aside"], untraced=untraced, aligned_text=aligned_paragraphs)
    out["words"] = result["words"]
    out["verified"] = result["verified"]
    out["issues"] = result["issues"]
    return out


def summary(scored):
    texts = len(scored)
    if not texts:
        return None
    checks = Counter()
    for s in scored:
        for c in {i["check"] for i in s["issues"]}:
            checks[c] += 1
    out = {"texts": texts, "verified": sum(s["verified"] for s in scored),
           "with_markup": sum(s["markup"] for s in scored),
           "texts_with_issue": dict(sorted(checks.items())),
           "issues": dict(sorted(Counter(i["check"] for s in scored for i in s["issues"]).items())),
           "words_mean": round(sum(s["words"] for s in scored) / texts, 1),
           "over_length": sum(1 for s in scored if s["words"] > PT["max_words"]),
           "paragraphs_differ": sum(1 for s in scored if s["paragraphs"] != s["template_paragraphs"]),
           "seconds_mean": round(sum(s["stats"]["total_s"] for s in scored) / texts, 1)}
    if "numbers" in scored[0]:
        numbers = sum(s["numbers"] for s in scored)
        out.update(numbers=numbers, untraced=sum(len(s["untraced"]) for s in scored),
                   untraced_per_100_numbers=round(100 * sum(len(s["untraced"]) for s in scored) / max(1, numbers), 2),
                   set_aside=sum(s["set_aside"] for s in scored), strict_v5=sum(s["strict_v5"] for s in scored))
    else:
        out.update(verified_loose_v5=sum(s["verified_loose_v5"] for s in scored),
                   unchanged_sentences_mean=round(sum(s["unchanged_sentences"] for s in scored) / texts, 3),
                   texts_with_literal_numbers=sum(1 for s in scored if s["literal_numbers"]))
    return out


def variation(scored):
    """Same facility, sampled decoding, different seeds: how much the text and its issues change."""
    by_unit = defaultdict(list)
    for s in scored:
        if s["condition"] == "free" and s["seed"] > 0:
            by_unit[s["cnes"]].append(s)
    rows = {}
    for cnes, runs in sorted(by_unit.items()):
        words = [set(re.findall(r"\w+", " ".join(x for p in r["aligned_text"] for x in p).lower())) for r in runs]
        rows[cnes] = {"runs": len(runs), "verified": sum(r["verified"] for r in runs),
                      "issues": [len(r["issues"]) for r in runs],
                      "word_jaccard_mean": round(sum(len(a & b) / len(a | b) for a, b in itertools.combinations(words, 2))
                                                 / max(1, math.comb(len(words), 2)), 3)}
    return rows


REFERENCE = ()


def main():
    global REFERENCE
    REFERENCE = (build_tasks.load_reference(), build_tasks.admissions_labels())
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else EVAL / "results" / "llm" / "gemma4_e4b"
    records = [json.loads(p.read_text()) for p in sorted(folder.glob("*_s*.json"))]
    cache, scored = {}, []
    for r in records:
        scored.append(score(r, cache))
    greedy = [s for s in scored if s["seed"] == 0]
    template = []
    for cnes in sorted({s["cnes"] for s in greedy}):
        result = verify(cnes, cache[cnes].body["slotted"])
        template.append({"verified": result["verified"], "words": result["words"]})
    out = {"model": records[0]["model"] if records else None, "digest": records[0].get("digest") if records else None,
           "template": {"texts": len(template), "verified": sum(t["verified"] for t in template),
                        "words_mean": round(sum(t["words"] for t in template) / max(1, len(template)), 1)},
           "free": summary([s for s in greedy if s["condition"] == "free"]),
           "rewrite": summary([s for s in greedy if s["condition"] == "rewrite"]),
           "variation": variation(scored), "texts": scored}
    (folder / "scores.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "texts"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
