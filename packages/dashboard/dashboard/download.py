"""The download: CSV text, and one zip of everything the page is built from."""
import csv
import io
import zipfile
from pathlib import Path


def csv_text(columns, rows):
    """-> the CSV: a header line, then one line per row (a list in column order)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return out.getvalue()


def bundle(out, members):
    """Write the zip at `out`. `members` is [(name in the zip, content)], kept
    in order; content is text or bytes to store, or a Path to a file. -> the
    zip's member names."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, content in members:
            if isinstance(content, (str, bytes)):
                z.writestr(name, content)
            else:
                z.write(content, name)
        return z.namelist()
