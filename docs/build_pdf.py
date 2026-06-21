"""Render PAPER.md to PAPER.pdf (pure-Python: markdown + xhtml2pdf).

Run from the docs/ directory so the relative figure/clock paths resolve:
    python3 build_pdf.py
"""

import os
import markdown
from xhtml2pdf import pisa

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/usr/share/fonts/truetype/dejavu"

CSS = """
@font-face { font-family: "DejaVu"; src: url("__F__/DejaVuSans.ttf"); }
@font-face { font-family: "DejaVu"; font-weight: bold; src: url("__F__/DejaVuSans-Bold.ttf"); }
@font-face { font-family: "DejaVu"; font-style: italic; src: url("__F__/DejaVuSans-Oblique.ttf"); }
@font-face { font-family: "DejaVuMono"; src: url("__F__/DejaVuSansMono.ttf"); }
@page { size: a4; margin: 2cm; }
body { font-family: "DejaVu"; font-size: 10.5px; line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 20px; margin: 0 0 4px 0; }
h2 { font-size: 15px; margin: 18px 0 6px 0; border-bottom: 1px solid #ccc; padding-bottom: 2px; }
h3 { font-size: 12.5px; margin: 14px 0 4px 0; }
p { margin: 6px 0; text-align: justify; }
em { font-style: italic; }
code, pre { font-family: "DejaVuMono"; font-size: 9.5px; background: #f4f4f4; }
pre { padding: 8px; border: 1px solid #ddd; }
a { color: #245; text-decoration: none; }
table { border-collapse: collapse; margin: 8px 0; width: 100%; }
th, td { border: 1px solid #bbb; padding: 3px 6px; font-size: 9.5px; text-align: left; }
th { background: #eee; }
img { max-width: 100%; }
""".replace("__F__", FONT)


def link_callback(uri, rel):
    """Resolve relative figure/clock paths against docs/."""
    if uri.startswith(("http://", "https://", "data:")):
        return uri
    path = uri if os.path.isabs(uri) else os.path.join(HERE, uri)
    return path


def main():
    with open(os.path.join(HERE, "PAPER.md"), encoding="utf-8") as fh:
        body = markdown.markdown(
            fh.read(), extensions=["tables", "fenced_code", "sane_lists"]
        )
    html = "<html><head><style>%s</style></head><body>%s</body></html>" % (CSS, body)
    out = os.path.join(HERE, "PAPER.pdf")
    with open(out, "wb") as fh:
        result = pisa.CreatePDF(html, dest=fh, link_callback=link_callback,
                                encoding="utf-8")
    print("errors:" if result.err else "wrote", "%d" % result.err if result.err else out)


if __name__ == "__main__":
    main()
