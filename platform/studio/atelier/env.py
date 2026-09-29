"""Load API keys from the ignored repository-root `.env` into the environment. Never prints values."""
import os

from .paths import REPO

KEYS = ('OPENAI_API_KEY', 'AI_GATEWAY_API_KEY', 'TRIPO_API_KEY')


def load(path=None, override=False):
    """Read KEY=value lines; existing environment variables win unless `override`. Returns the names loaded."""
    path = path or REPO / '.env'
    loaded = []
    if not os.path.exists(path):
        return loaded
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if not value:
                continue
            if override or key not in os.environ:
                os.environ[key] = value
                loaded.append(key)
    return loaded


def require(key):
    """The value of `key`, loading .env first; raises with a clear message (never the value) if it is missing."""
    load()
    value = os.environ.get(key)
    if not value:
        raise SystemExit(f'{key} is not set: add it to .env at the repository root (see .env.example)')
    return value
