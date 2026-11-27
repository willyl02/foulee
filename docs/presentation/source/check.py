"""Vérifie qu'aucun contenu ne passe sous le pied de page."""
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright
html = Path(sys.argv[1]).resolve()
with sync_playwright() as pw:
    b = pw.chromium.launch(); p = b.new_page(viewport={"width": 794, "height": 1123})
    p.goto(html.as_uri()); p.wait_for_load_state("networkidle")
    r = p.evaluate("""() => [...document.querySelectorAll('section.page')].map((s, i) => {
        const f = s.querySelector('.foot'); if (!f) return null;
        const top = f.getBoundingClientRect().top;
        let low = 0;
        s.querySelectorAll('.content *, .dv-body *').forEach(e => { const r = e.getBoundingClientRect(); if (r.height) low = Math.max(low, r.bottom); });
        return [i + 1, Math.round(top - low), (s.querySelector('h1') || {}).textContent];
    }).filter(x => x && x[1] < 3)""")
    print("pages qui touchent le pied de page :", r or "aucune")
    b.close()
