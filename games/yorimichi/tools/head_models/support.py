"""Pinned source identities shared by the local head model experiments."""
from pathlib import Path
import subprocess

SOURCES = {
    'pixal3d-mac': ('https://github.com/pawel-mazurkiewicz/Pixal3D-mac.git',
                    '0be9e69a729432323dfb60a418801e5e9e7a1437'),
    'naf': ('https://github.com/valeoai/NAF.git', '37f2dfc180f2de53d98bd601109c0da0dd6b0f43'),
    'trellis2mlx': ('https://github.com/lyonsno/trellis2mlx.git',
                   'c0e66f782ac86f86212e049cf029478602b0e8d2'),
}


def verify_source(root, backend):
    """@cc [owner:fontanierh,label:correctness] local-head-source-identity
    Inference MUST use the pinned source commits. The only tracked Pixal changes
    MAY be the published MPS attention/Clang patch; TRELLIS and NAF MUST be clean.
    """
    for name in (('pixal3d-mac', 'naf') if backend == 'native' else ('trellis2mlx',)):
        repo = root/name
        actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != SOURCES[name][1]:
            raise ValueError('Unreviewed source revision: '+name)
        diff = subprocess.check_output(['git', '-C', str(repo), 'diff', '--unified=0', 'HEAD'], text=True)
        expected = Path(__file__).with_name('pixal-mps.patch').read_text() if name == 'pixal3d-mac' else ''
        if diff != expected:
            raise ValueError('Unexpected source changes: '+name)
