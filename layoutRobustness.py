

import os
import sys
import random
import uuid
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from tqdm import tqdm
from rich.console import Console

# ================== 顶部定义配置 ==================
INPUT_DIR   = Path(r"").resolve()
OUTPUT_DIR  = Path(r"").resolve()
DISTURB_LEVEL = "hard"
CHROME_PATH = None
# ==================================================

console = Console()


def wrapper_injection(soup, depth=3, times=1):
    candidates = [tag for tag in soup.find_all(True) if len(tag.find_parents()) >= depth]
    for _ in range(times):
        if not candidates:
            return
        target = random.choice(candidates)
        wrapper = soup.new_tag("div", **{"class": f"noise-wrap-{uuid.uuid4().hex[:4]}"})
        target.wrap(wrapper)


def role_replacement(soup, times=1):
    buttons = soup.find_all(["button", "input"], attrs={"type": "submit"})
    buttons = buttons * times  # 增加替换数量
    for b in buttons:
        new_div = soup.new_tag("div", role="button")
        new_div.string = b.get_text(strip=True) or b.get("value", "")
        if aria := b.get("aria-label"):
            new_div["aria-label"] = aria
        b.replace_with(new_div)


def redundant_nodes(soup, count=5):
    for _ in range(count):
        hidden = soup.new_tag("div", style="display:none;width:1px;height:1px;", id=f"ghost-{uuid.uuid4().hex[:6]}")
        soup.body.append(hidden)


OPERATORS = {
    "easy": [
        lambda s: redundant_nodes(s, count=3),
    ],
    "medium": [
        lambda s: wrapper_injection(s, depth=3, times=1),
        lambda s: role_replacement(s, times=1),
        lambda s: redundant_nodes(s, count=10),
    ],
    "hard": [
        lambda s: wrapper_injection(s, depth=2, times=3),
        lambda s: role_replacement(s, times=3),
        lambda s: redundant_nodes(s, count=50),
        lambda s: wrapper_injection(s, depth=1, times=3),
    ],
}


def disturb_html(html_path: Path, out_path: Path):
    soup = BeautifulSoup(html_path.read_text("utf-8", errors="ignore"), "lxml")
    for op in OPERATORS[DISTURB_LEVEL]:
        op(soup)
    out_path.write_text(str(soup), "utf-8")


def screenshot_html(playwright, html_file: Path, png_path: Path):
    browser = playwright.chromium.launch(executable_path=CHROME_PATH, headless=True)
    page = browser.new_page()
    page.goto(html_file.as_uri(), wait_until="load", timeout=60000)
    page.screenshot(path=str(png_path), full_page=True)
    browser.close()


def process_single(html_file: Path):
    base = html_file.stem
    subdir = OUTPUT_DIR / base
    subdir.mkdir(parents=True, exist_ok=True)

    disturbed_html = subdir / "disturbed.html"
    original_png = subdir / "original.png"
    disturbed_png = subdir / "disturbed.png"

    disturb_html(html_file, disturbed_html)

    with sync_playwright() as p:
        screenshot_html(p, html_file, original_png)
        screenshot_html(p, disturbed_html, disturbed_png)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    html_files = sorted([p for p in INPUT_DIR.rglob("*.html")])
    if not html_files:
        console.print("[bold red]❌ No HTML files found in input directory.")
        sys.exit(1)

    console.print(f"[bold cyan]▶ Processing {len(html_files)} HTML files at level '{DISTURB_LEVEL}' …[/]")
    for html_path in tqdm(html_files, desc="Disturb", unit="file"):
        try:
            process_single(html_path)
        except Exception as e:
            console.print(f"[red]Error on {html_path}: {e}")

    console.print(f"[bold green]✔ Done. Results saved in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
