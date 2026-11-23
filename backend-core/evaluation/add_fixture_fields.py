"""Add to the frozen evaluation fixtures facility columns that were created after they were frozen,
leaving every other value as it was, so earlier results stay comparable.

    python3 backend-core/evaluation/add_fixture_fields.py obitos_sus obitos_esperados mortalidade_faixa
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

import psycopg2

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "database" / "seeders"))
from seed import read_env  # noqa: E402


def plain(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def main():
    columns = sys.argv[1:]
    if not columns:
        raise SystemExit(__doc__)
    paths = sorted((HERE / "fixtures").glob("*.json")) + sorted((HERE / "fixtures_need").glob("*.json"))
    codes = [int(p.name.split("_")[0]) for p in paths]
    quoted = ", ".join(f'"{c}"' for c in columns)
    with psycopg2.connect(read_env(ROOT / ".env")["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(f'select "CO_CNES", {quoted} from infraestrutura_saude where "CO_CNES" = any(%s)', (codes,))
        values = {row[0]: dict(zip(columns, map(plain, row[1:]))) for row in cur.fetchall()}
    changed = 0
    for path, code in zip(paths, codes):
        payload = json.loads(path.read_text())
        before = json.dumps(payload["facility"], sort_keys=True)
        payload["facility"].update(values.get(code, {c: None for c in columns}))
        if json.dumps(payload["facility"], sort_keys=True) != before:
            changed += 1
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    with_values = sum(1 for v in values.values() if any(x is not None for x in v.values()))
    print(f"{len(paths)} fixtures, {changed} changed, {with_values} with values")


if __name__ == "__main__":
    main()
