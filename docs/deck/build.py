# Render the deck to docs/deck/closeguard-deck.pdf and the cover to docs/deck/cover.png (needs Playwright, system python).
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 720})
    pg.goto((HERE / "deck.html").as_uri())
    pg.wait_for_load_state("networkidle")
    pg.pdf(path=str(HERE / "closeguard-deck.pdf"), width="1280px", height="720px", print_background=True)
    pg = b.new_page(viewport={"width": 1200, "height": 630})
    pg.goto((HERE / "cover.html").as_uri())
    pg.wait_for_load_state("networkidle")
    pg.screenshot(path=str(HERE / "cover.png"))
    b.close()
print("wrote closeguard-deck.pdf and cover.png")
