from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(); pg.goto('file:///w/handbook.html'); pg.wait_for_timeout(1500)
    pg.pdf(path='/w/Home-Deck-Studio-handbook.pdf', format='A4', print_background=True, display_header_footer=True,
           header_template='<span></span>', footer_template='<div style="font-size:8px;width:100%;text-align:center;color:#94a3b8">Home Deck Studio · <span class="pageNumber"></span>/<span class="totalPages"></span></div>',
           margin={'top': '16mm', 'bottom': '18mm', 'left': '16mm', 'right': '16mm'})
    b.close()
