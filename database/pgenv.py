"""Print shell exports of the libpq variables (PGHOST, PGUSER, PGPASSWORD...) for the DATABASE_URL
in .env, so psql can run without the connection string, and its password, on the command line
(where any process listing would show it).

Usage: eval "$(python3 -I database/pgenv.py)" && psql -X ...
"""
import shlex
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]

url = next(line.split('=', 1)[1].strip().strip('\'"') for line in (ROOT / '.env').read_text().splitlines()
           if line.startswith('DATABASE_URL='))
parts = urlparse(url)
values = {'PGHOST': parts.hostname, 'PGPORT': parts.port or 5432, 'PGUSER': unquote(parts.username or ''),
          'PGPASSWORD': unquote(parts.password or ''), 'PGDATABASE': parts.path.lstrip('/') or 'postgres'}
print(' '.join(f'export {k}={shlex.quote(str(v))};' for k, v in values.items()))
