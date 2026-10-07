"""Render slides/E-presentation.html to E-presentation.pdf (one 1280x720 page per slide).
Usage: python3 slides/build_pdf.py   (needs: pip install playwright && playwright install chromium)"""
import pathlib
from playwright.sync_api import sync_playwright
root = pathlib.Path(__file__).resolve().parent
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 720})
    pg.goto((root / "E-presentation.html").as_uri())
    pg.wait_for_timeout(300)
    pg.pdf(path=str(root.parent / "E-presentation.pdf"), width="1280px", height="720px",
           print_background=True, prefer_css_page_size=True)
    # overflow check: each slide's content must fit its box
    over = pg.evaluate("""[...document.querySelectorAll('.slide')].map((s,i)=>{
        const foot=s.querySelector('.foot').getBoundingClientRect().top;
        let maxb=0; s.querySelectorAll('*').forEach(e=>{ if(!e.closest('.foot')) { const r=e.getBoundingClientRect(); if(r.height) maxb=Math.max(maxb,r.bottom);} });
        return [i+1, Math.round(maxb), Math.round(foot)] })""")
    print("slide, content bottom, footer top:", over)
    b.close()
