"""Briques du manuel unique de Foulée : présentation, installation et utilisation (A4 portrait).

Un seul document à maintenir d'une version à l'autre : chaque partie vit dans parts/, et build.py les assemble
avec la couverture, le sommaire (numéros de page calculés) et les intercalaires.
"""
import json
import re
import subprocess
from pathlib import Path

import segno
from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
IMG = HERE / "img"
FONTS = HERE.parents[2] / "foulee" / "static" / "fonts"   # les polices de l'appli, dans le dépôt
ICONS = json.loads((HERE / "app-icons.json").read_text())
ICONS.update({
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "watch": '<rect x="6" y="6.5" width="12" height="11" rx="3"/><path d="M8.5 6.5 9.3 3h5.4l.8 3.5M8.5 17.5l.8 3.5h5.4l.8-3.5M12 9.5V12l1.8 1.2"/>',
})

VERSION = "0.8.3"
MOIS = "novembre 2026"
HOST = "relais.foulee-coach.com"
RELEASES = "https://github.com/willyl02/foulee/releases/latest"
KEY_PAGE = "https://connect.garmin.com/app/settings/personalApiToken"


def fr(text: str) -> str:
    """Espaces insécables à la française."""
    text = re.sub(r" ([:;?!»])", "\u00a0\\1", text)
    text = re.sub(r"(\d) (Mo|Go|ans?|heures?|minutes?|min|mois|jours?|km|semaines?|€|h|caractères|mm|pixels|fois)\b", "\\1\u00a0\\2", text)
    return text.replace("« ", "«\u00a0")


def icon(name, size="5mm", sw="1.8"):
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="currentColor" stroke-width="{sw}" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def chip(text):
    return f'<span class="chip">{fr(text)}</span>'


def code(text):
    return f'<span class="code">{text}</span>'


def qr(url):
    return segno.make(url, error="m").svg_inline(dark="#15201b", light="#ffffff", border=1, scale=1, omitsize=True)


def shot(name, markers=(), max_w=168, max_h=120, *, light=False, cap="", cls=""):
    """Une capture, à l'échelle, avec ses pastilles numérotées placées en pourcentage de l'image."""
    path = next(p for p in (IMG / f"{name}.jpg", IMG / f"{name}.png") if p.exists())
    w, h = Image.open(path).size
    ratio = w / h
    width = min(max_w, max_h * ratio)
    height = width / ratio
    marks = "".join(f'<span class="mk" style="left:{x / w * 100:.2f}%;top:{y / h * 100:.2f}%">{n}</span>' for n, x, y in markers)
    caption = f'<p class="cap">{fr(cap)}</p>' if cap else ""
    return (f'<div class="shot{" light" if light else ""} {cls}" style="width:{width:.1f}mm">'
            f'<div style="position:relative;height:{height:.1f}mm"><img src="../img/{path.name}" alt="">{marks}</div>{caption}</div>')


def numbered(markers):
    return [(i, x, y) for i, (x, y) in enumerate(markers, 1)]


def legend(items, cols=False, start=1):
    return (f'<ol class="legend{" cols" if cols else ""}">' + "".join(
        f'<li><span class="num">{i}</span><span>{fr(t)}</span></li>' for i, t in enumerate(items, start)) + "</ol>")


def howto(steps, cls=""):
    return (f'<ol class="howto {cls}">' + "".join(
        f'<li><span class="n">{n}</span><div><b>{fr(t)}</b><p>{d}</p></div></li>' for n, t, d in steps) + "</ol>")


def box(title, body, ic="info", cls=""):
    head = f"<h2>{icon(ic)}{fr(title)}</h2>" if title else ""
    return f'<div class="box {cls}">{head}{body}</div>'


def note(text, ic="info"):
    return f'<p class="note">{icon(ic, "4.4mm")}<span>{fr(text)}</span></p>'


def linkcard(label, url, shown, sub=""):
    return (f'<div class="linkcard"><span class="lc-text"><span class="lc-label">{icon("external", "4mm")}{fr(label)}</span>'
            f'<span class="lc-url">{shown}</span>{f"<span class=lc-note>{fr(sub)}</span>" if sub else ""}</span>'
            f'<span class="lc-qr">{qr(url)}</span></div>')


def ul(items):
    return "<ul>" + "".join(f"<li>{fr(t)}</li>" for t in items) + "</ul>"


def cards(items, cls="three"):
    """Petites cartes titre + texte, en grille."""
    return f'<div class="cards {cls}">' + "".join(
        f'<div class="card">{icon(ic, "5.4mm") if ic else ""}<b>{fr(t)}</b><p>{fr(d)}</p></div>' for t, d, ic in items) + "</div>"


def table(head, rows, cls=""):
    th = "".join(f"<th>{fr(h)}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<table class="t {cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


def term(lines, foot=""):
    body = "".join(f"<code>{c}</code><span>{fr(s)}</span>" for c, s in lines)
    return f'<div class="term">{body}{f"<p class=term-foot>{fr(foot)}</p>" if foot else ""}</div>'


def row(*cols, grow=0):
    inner = "".join(f'<div class="{"grow" if i == grow else ""}">{c}</div>' for i, c in enumerate(cols))
    return f'<div class="row">{inner}</div>'


def two(a, b):
    return f'<div class="two"><div>{a}</div><div>{b}</div></div>'


class Doc:
    """Le manuel : des parties, chacune avec ses pages. Les numéros de page et le sommaire sont calculés à la fin."""

    def __init__(self, version=VERSION):
        self.version = version
        self.blocks = []          # (kind, html, part_no, part_title)
        self.part_no = 0
        self.part_title = ""

    # --- une partie ---------------------------------------------------------
    def part(self, title, lead, items, img=None, *, tone="dark"):
        """Intercalaire : le titre de la partie, ce qu'on y trouve, et une capture en fond de page."""
        self.part_no += 1
        self.part_title = title
        n = self.part_no
        lis = "".join(f'<li>{icon("check", "4.4mm", "2.4")}<span>{fr(t)}</span></li>' for t in items)
        pic = shot(img, max_w=150, max_h=92) if img else ""
        html = f"""
<section class="page divider {tone}">
  {self._top(light=True)}
  <div class="dv-body">
    <span class="dv-no">Partie {n}</span>
    <h1>{fr(title)}</h1>
    <p class="lead">{fr(lead)}</p>
    <ul class="checks">{lis}</ul>
    {pic}
  </div>
  {self._foot()}
</section>"""
        self.blocks.append(("divider", html, n, title))

    # --- une page de contenu ------------------------------------------------
    def page(self, crumb, title, lead, content, *, cls=""):
        html = f"""
<section class="page {cls}">
  {self._top()}
  {f'<span class="kicker">{fr(crumb)}</span>' if crumb else ''}
  <h1>{fr(title)}</h1>
  {f'<p class="lead">{fr(lead)}</p>' if lead else ''}
  <div class="content">{content}</div>
  {self._foot()}
</section>"""
        self.blocks.append(("page", html, self.part_no, self.part_title))

    def view(self, crumb, title, lead, image, markers, items, *, max_w=168, max_h=118, cols=False, after="", light=False):
        """Page type « une vue de l'appli » : la capture, puis sa légende numérotée."""
        body = shot(image, numbered(markers), max_w, max_h, light=light) + legend(items, cols=cols)
        self.page(crumb, title, lead, body + after)

    # --- gabarits internes --------------------------------------------------
    def _top(self, light=False):
        return (f'<header class="top"><span class="brand"><span class="balise"><i></i><i></i></span>Foulée</span>'
                f'<span class="crumb">{fr(self.part_title)}</span></header>')

    def _foot(self):
        return (f'<footer class="foot"><span>{fr(f"Foulée {self.version} · manuel · présentation, installation et utilisation · {MOIS}")}</span>'
                f'<span class="pno">N</span></footer>')

    # --- assemblage ---------------------------------------------------------
    def toc(self):
        """Le sommaire : chaque partie et sa page de début, calculée sur les blocs déjà empilés."""
        out, page_no = [], 2 + 1  # couverture + sommaire
        for kind, _html, n, title in self.blocks:
            if kind == "divider":
                out.append((n, title, page_no))
            page_no += 1
        return out

    def write(self, cover_html, toc_html, path):
        pages = [cover_html, toc_html] + [b[1] for b in self.blocks]
        total = len(pages)
        out = []
        for i, p in enumerate(pages, 1):
            out.append(p.replace('<span class="pno">N</span>', f'<span class="pno">{i} / {total}</span>'))
        faces = "\n".join(
            f'@font-face {{ font-family: "{fam}"; font-weight: {w}; src: url("{(FONTS / f).as_uri()}") format("woff2"); }}'
            for fam, w, f in [("Barlow", 400, "barlow-latin-400-normal.woff2"), ("Barlow", 500, "barlow-latin-500-normal.woff2"),
                              ("Barlow", 600, "barlow-latin-600-normal.woff2"), ("Barlow", 700, "barlow-latin-700-normal.woff2"),
                              ("Barlow Semi Condensed", 500, "barlow-semi-condensed-latin-500-normal.woff2"),
                              ("Barlow Semi Condensed", 600, "barlow-semi-condensed-latin-600-normal.woff2")])
        doc = (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
               f'<title>{fr(f"Foulée {self.version} — manuel : présentation, installation et utilisation")}</title>'
               f'<style>{faces}\n{(HERE / "manuel.css").read_text()}</style></head><body>{"".join(out)}</body></html>')
        Path(path).write_text(doc, encoding="utf-8")
        return total


def render(html_path, pdf_path, review_dir=None, dpi=70):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(Path(html_path).as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.pdf(path=str(pdf_path), width="210mm", height="297mm", print_background=True, prefer_css_page_size=True)
        browser.close()
    if review_dir:
        out = Path(review_dir)
        out.mkdir(parents=True, exist_ok=True)
        for f in out.glob("*.png"):
            f.unlink()
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf_path), str(out / "p")], check=True)
    return Path(pdf_path).stat().st_size // 1024
