
PARENT_DIR    = r""
OUTPUT_DIR    = r""
DISTURB_LEVEL = "high"
MIN_AREA      = 50

LEVEL_PROB = {"low": 0.10, "medium": 0.30, "high": 0.40}
STRONG_COLORS = [
    "red", "blue", "green", "yellow", "purple", "orange",
    "#00ffff", "#ff00ff", "#ff6600", "#00ff00", "#0099ff"
]

import random, re, pathlib, logging, shutil
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from PIL import Image

prob = LEVEL_PROB[DISTURB_LEVEL]
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def find_all_buttons(soup):
    candidates = []
    for tag in soup.find_all(True):
        if tag.name == "button":
            candidates.append(tag)
        elif tag.name == "input" and tag.get("type", "").lower() in {"button", "submit", "reset"}:
            candidates.append(tag)
        elif "button" in tag.get("class", []):
            candidates.append(tag)
        elif tag.get("role") == "button":
            candidates.append(tag)
    return candidates

def get_button_sizes_and_html(html_path: pathlib.Path, selector_list: list):
    html_url = f"file:///{html_path.as_posix()}"
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page()
        pg.goto(html_url)

        html_source = pg.content()

        buttons_info = pg.evaluate(f"""
            () => Array.from(document.querySelectorAll('{",".join(selector_list)}')).map(btn => {{
                const r = btn.getBoundingClientRect();
                return {{x: r.x, y: r.y, width: r.width, height: r.height}};
            }})
        """)
        br.close()
    return buttons_info, html_source

def recolor_html(html_source: str, sizes: list):
    soup = BeautifulSoup(html_source, "html.parser")
    buttons = find_all_buttons(soup)

    indices = list(range(len(buttons)))
    random.shuffle(indices)

    hits = 0
    for idx in indices:
        btn = buttons[idx]
        size = sizes[idx]
        area = size["width"] * size["height"]
        if area < MIN_AREA:
            continue
        if random.random() <= prob:
            colour = random.choice(STRONG_COLORS)
            style  = btn.get("style", "")
            style  = re.sub(r"background(?:-color)?\s*:\s*[^;]+;?", "", style, flags=re.I)
            if style and not style.strip().endswith(";"):
                style += ";"
            style += f"background-color:{colour};"
            btn["style"] = style
            hits += 1
    return str(soup), hits, len(buttons)

def safe_screenshot(html_path: pathlib.Path, png_path: pathlib.Path, out_dir: pathlib.Path, difficulty: str, html_stem: str) -> bool:
    try:
        html_url = f"file:///{html_path.as_posix()}"
        with sync_playwright() as p:
            br = p.chromium.launch()
            pg = br.new_page()
            pg.goto(html_url)

            w = pg.evaluate("() => document.documentElement.scrollWidth")
            h = pg.evaluate("() => document.documentElement.scrollHeight")

            if h > 5500:
                logging.warning("🚮 页面高度过大，跳过截图并删除: %s/%s (%d px)", difficulty, html_stem, h)
                shutil.rmtree(out_dir)
                br.close()
                return False

            pg.set_viewport_size({"width": w, "height": h})
            pg.screenshot(path=str(png_path), full_page=True)
            br.close()
        return True
    except Exception as e:
        logging.error("❌ 截图失败: %s/%s %s", difficulty, html_stem, str(e))
        shutil.rmtree(out_dir)
        return False

# ─── MAIN ──────────────────────────────────────────────────────────────────

files = [p for p in pathlib.Path(PARENT_DIR).rglob("*.htm*") if p.is_file()]
logging.info("%d html files found", len(files))

failed_pages = []

for html in files:
    relative_path = html.relative_to(PARENT_DIR)
    difficulty = relative_path.parts[0]
    html_stem = html.stem

    out_dir  = pathlib.Path(OUTPUT_DIR) / difficulty / html_stem
    orig_png = out_dir / "original.png"
    dist_png = out_dir / "disturbed.png"
    disturbed_html_path = out_dir / "disturbed.html"

    out_dir.mkdir(parents=True, exist_ok=True)

    selector_list = [
        "button", "input[type=button]", "input[type=submit]", "input[type=reset]",
        "[role=button]", ".button"
    ]
    try:
        sizes, html_source = get_button_sizes_and_html(html, selector_list)

        # 原始截图
        if not safe_screenshot(html, orig_png, out_dir, difficulty, html_stem):
            continue

        # 干扰
        disturbed_html, hits, total = recolor_html(html_source, sizes)
        disturbed_html_path.write_text(disturbed_html, encoding="utf-8")

        if not safe_screenshot(disturbed_html_path, dist_png, out_dir, difficulty, html_stem):
            continue

        if hits == 0:
            failed_pages.append(f"{difficulty}/{html_stem}")
        else:
            logging.info("[%s/%s]: recoloured %d / %d buttons (level %s, min area %d)",
                         difficulty, html_stem, hits, total, DISTURB_LEVEL, MIN_AREA)
    except Exception as e:
        logging.error("❌ 处理失败: %s/%s %s", difficulty, html_stem, str(e))
        shutil.rmtree(out_dir)
        continue

logging.info("✔ All pages processed → %s", OUTPUT_DIR)

if failed_pages:
    logging.warning("⚠️ No buttons disturbed in:")
    for page in failed_pages:
        logging.warning(" - %s", page)
else:
    logging.info("🎉 All pages have at least 1 disturbed button.")
