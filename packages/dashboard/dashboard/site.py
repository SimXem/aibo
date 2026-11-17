"""A site is one folder: index.html, the files beside it (the download), and the
assets the page links to. Nothing in it is a symlink."""
import hashlib
import json
import shutil
from pathlib import Path

from . import page


def write_site(out, html, assets=None):
    """Write the folder `out`: the page as index.html, and each of `assets`
    ({path in the site: source directory}) copied in; a source that is not
    there is skipped (licensed fonts a checkout may not have). -> out."""
    out = Path(out)
    for target, source in (assets or {}).items():
        if Path(source).is_dir():
            shutil.copytree(source, out / target, dirs_exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    return out


def verify(site, required=()):
    """Raise RuntimeError unless the site has a page, each required file with
    something in it, and no symlinks."""
    site = Path(site)
    for name in ('index.html', *required):
        if not (site / name).is_file() or (site / name).stat().st_size == 0:
            raise RuntimeError('Incomplete publication: ' + name)
    if '<html' not in (site / 'index.html').read_text().lower():
        raise RuntimeError('Publication has no HTML document')
    if any(p.is_symlink() for p in site.rglob('*')):
        raise RuntimeError('Publication must not contain symlinks')


def snapshot(site, files=()):
    """What the site publishes, hashed: each data block in the page and each of
    `files` that is there. -> {"blocks": {...}, "files": {...}, "sha256": of both}."""
    site = Path(site)
    blocks = {name: hashlib.sha256(block).hexdigest()
              for name, block in page.blocks((site / 'index.html').read_bytes()).items()}
    hashed = {}
    for name in files:
        path = site / name
        if path.exists():
            with path.open('rb') as f:
                hashed[name] = hashlib.file_digest(f, 'sha256').hexdigest()
    manifest = {'blocks': blocks, 'files': hashed}
    return {**manifest, 'sha256': hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()}
