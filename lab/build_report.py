"""Builds reports/capstone-report.pdf and an editable .docx from the recorded command logs, configs and screenshots.

usage: python3 lab/build_report.py   (needs Google Chrome for HTML -> PDF, LibreOffice for HTML -> DOCX)
"""
import base64
import html
import re
import struct
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "evidence" / "logs"
SHOTS = ROOT / "evidence" / "screenshots"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
REPO = "https://github.com/ksamirdev/ensp461-devops-capstone"

HEADER = {
    "course": "ENSP461 - DevOps &amp; Automation | Capstone: End-to-End DevOps Automation Platform",
    "name": "Samir Kumar Gupta",
    "roll": "2301730243",
    "env": "OrbStack Kubernetes v1.36 (single node, arm64) on macOS",
}

CSS = """
@page { size: A4; margin: 16mm 15mm; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.45 "Helvetica Neue", Arial, sans-serif; color: #111; margin: 0; }
.meta { border-bottom: 1.5px solid #111; padding-bottom: 6px; margin-bottom: 14px; font-size: 9.5pt; }
.meta .course { font-weight: 700; font-size: 10.5pt; margin-bottom: 3px; }
.meta span { margin-right: 22px; }
h1 { font-size: 15pt; margin: 0 0 8px; }
h2 { font-size: 11.5pt; margin: 18px 0 6px; break-after: avoid; }
h3 { font-size: 10.5pt; margin: 12px 0 4px; break-after: avoid; }
.question { margin: 0 0 10px; }
p, li { margin: 0 0 6px; }
ul { padding-left: 18px; margin: 0 0 6px; }
pre { font: 8.2pt/1.38 Menlo, "DejaVu Sans Mono", monospace; background: #f5f5f4; border: 1px solid #ddd;
      border-radius: 4px; padding: 7px 9px; white-space: pre-wrap; word-break: break-all; margin: 0 0 8px; }
pre .cmd { color: #0b5394; font-weight: 700; }
.label { font-size: 8.5pt; color: #555; margin: 0 0 2px; break-after: avoid; }
figure { margin: 6px 0 12px; break-inside: avoid; }
figure img { display: block; width: auto; max-width: 100%; max-height: 105mm; margin: 0 auto; border: 1px solid #ccc; border-radius: 4px; }
figure.small img { width: 62%; }
figcaption { font-size: 8.5pt; color: #444; margin-top: 3px; text-align: center; }
table { break-inside: auto; border-collapse: collapse; width: 100%; font-size: 9pt; margin: 0 0 10px; }
tr { break-inside: avoid; }
th, td { border: 1px solid #ccc; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #f0f0ef; }
.keep { break-inside: avoid; }
"""

# LibreOffice's HTML import understands only simple CSS, so the DOCX gets its own sheet and plain HTML attributes.
DOCX_CSS = """
body { font-family: Arial; font-size: 10pt; }
h1, h2, h3 { font-family: Arial; } h1 { font-size: 15pt; } h2 { font-size: 12pt; } h3 { font-size: 10.5pt; }
p, li { margin-top: 0; margin-bottom: 4pt; }
pre { font-family: Menlo, monospace; font-size: 8pt; margin: 0; background: #f5f5f4; }
.label { font-size: 8.5pt; color: #555555; margin-bottom: 1pt; }
.cap { font-size: 8.5pt; color: #444444; }
th, td { font-size: 9pt; }
th { background: #f0f0ef; }
"""


def esc(text):
    return html.escape(text, quote=False)


def blocks(log):
    """Split a rec.sh log into (command, output) pairs."""
    out, cmd, body = [], None, []
    for line in (LOGS / log).read_text().splitlines():
        if line.startswith("$ "):
            if cmd is not None:
                out.append((cmd, "\n".join(body).strip("\n")))
            cmd, body = line[2:], []
        else:
            body.append(line)
    if cmd is not None:
        out.append((cmd, "\n".join(body).strip("\n")))
    return out


def term(log, *needles, head=None, tail=None, label=None, pick=None, omit=None):
    """Terminal block with the recorded commands whose text contains any needle.
    pick: a slice selecting which of the matching commands to show, for commands recorded more than once.
    omit: regex; output lines matching it are left out (the log keeps them)."""
    parts = []
    for cmd, output in blocks(log):
        if needles and not any(n in cmd for n in needles):
            continue
        lines = output.splitlines()
        if omit:
            lines = [line for line in lines if not re.search(omit, line)]
        if head and len(lines) > head:
            lines = lines[:head] + ["..."]
        if tail and len(lines) > tail:
            lines = ["..."] + lines[-tail:]
        parts.append(f'<span class="cmd">$ {esc(cmd)}</span>\n' + esc("\n".join(lines)))
    if pick is not None:
        parts = parts[pick]
    caption = f'<p class="label">{esc(label)}</p>' if label else ""
    joined = "\n".join(parts)
    return f"{caption}<pre>{joined}</pre>"


def config(path, label=None, start=None, end=None):
    """File contents, optionally from the line containing start up to (not including) the line containing end."""
    lines = (ROOT / path).read_text().splitlines()
    if start:
        lines = lines[next(i for i, l in enumerate(lines) if start in l):]
    if end:
        lines = lines[: next(i for i, l in enumerate(lines) if end in l)]
    return f'<p class="label">{esc(label or path)}</p><pre>{esc(chr(10).join(lines).strip())}</pre>'


def shot(name, caption, small=False):
    cls = ' class="small"' if small else ""
    src = (SHOTS / f"{name}.png").as_uri()
    return f'<figure{cls}><img src="{src}"><figcaption>{esc(caption)}</figcaption></figure>'


def table(headers, rows):
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def bullets(*items):
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def page(title, intro, body):
    meta = (
        f'<div class="meta"><div class="course">{HEADER["course"]}</div>'
        f'<span>Name: {HEADER["name"]}</span><span>Roll No.: {HEADER["roll"]}</span>'
        f'<span>Environment: {HEADER["env"]}</span></div>'
    )
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{esc(title)}</title>'
        f"<style>{CSS}</style></head><body>{meta}<h1>{esc(title)}</h1>{intro}{body}</body></html>"
    )


def docx_html(doc):
    """Rewrite a report page into HTML that LibreOffice turns into a clean DOCX, with the screenshots embedded."""
    def image(m):
        data = Path(unquote(m[1].removeprefix("file://"))).read_bytes()
        w, h = struct.unpack(">II", data[16:24])  # PNG IHDR width, height
        k = min(1, 620 / w, 400 / h)
        return f'src="data:image/png;base64,{base64.b64encode(data).decode()}" width="{round(w * k)}" height="{round(h * k)}"'

    doc = re.sub(r"<style>.*?</style>", f"<style>{DOCX_CSS}</style>", doc, flags=re.DOTALL)
    doc = re.sub(r'src="(file://[^"]+)"', image, doc)
    doc = re.sub(r"<figure[^>]*>(<img[^>]*>)<figcaption>(.*?)</figcaption></figure>",
                 r'<p align="center">\1</p><p class="cap" align="center">\2</p>', doc)
    doc = doc.replace("<table>", '<table border="1" cellpadding="4" cellspacing="0" width="100%">')
    meta = re.search(r'<div class="meta"><div class="course">(.*?)</div>(.*?)</div>', doc)
    return doc.replace(meta[0], f"<p><b>{meta[1]}</b></p><p>{meta[2].replace('</span><span>', '</span> | <span>')}</p>")


def main():
    from report_content import INTRO, TITLE, body

    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    slug = "capstone-report"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"{slug}.html"
        src.write_text(page(TITLE, INTRO, body()))
        pdf = out_dir / f"{slug}.pdf"
        subprocess.run(
            [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             "--allow-file-access-from-files", f"--print-to-pdf={pdf}", src.as_uri()],
            check=True, capture_output=True,
        )
        print(f"wrote {pdf.relative_to(ROOT)}")
        src.write_text(docx_html(src.read_text()))
        subprocess.run(
            [SOFFICE, "--headless", "--infilter=HTML (StarWriter)", "--convert-to", "docx:MS Word 2007 XML",
             "--outdir", str(out_dir), str(src)],
            check=True, capture_output=True,
        )
        print(f"wrote {out_dir.relative_to(ROOT)}/{slug}.docx")


if __name__ == "__main__":
    main()
