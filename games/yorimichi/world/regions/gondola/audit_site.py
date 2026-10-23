"""Run the original complete fitted-site gates from selected raw mesh queries."""
from pathlib import Path
import sys

GAME = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(GAME),str(GAME / 'world')]
import yori  # noqa: E402
from gondola_site_products import Prepared  # noqa: E402
from regions.gondola.site_sources import site_module  # noqa: E402


if __name__ == '__main__':
    site_module().main(prepared=Prepared(yori.OUT))
