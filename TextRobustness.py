# -*- coding: utf-8 -*-
"""
perturb_two_buttons.py  —  2025-07-23
-------------------------------------
需求：
1) 遍历 INPUT_ROOT 下 easy/medium/hard/数字.html
2) 每页随机选 2 个“可扰动”的按钮并确保文本确实被修改，否则整页记为失败
3) 截图前后各一张：original.png / disturbed.png
4) 输出目录镜像输入结构：OUTPUT_ROOT/easy/数字/...
5) 失败页记录到 failed_pages.csv（含难度、page_id、原因）

依赖：
    pip install playwright tqdm pillow
    playwright install chromium
"""

import os
import csv
import json
import random
import logging
import traceback
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm

# ─── CONFIG ────────────────────────────────────────────────────────────────
INPUT_ROOT   = r"C:\Users\18446\Desktop\easy medium hard新版"     # ← 你的输入根目录
OUTPUT_ROOT  = r"C:\Users\18446\Desktop\rob-txt备用版" # ← 你的输出根目录
LOG_FILE     = "run.log"
FAILED_CSV   = "failed_pages.csv"

NEED_BTN_NUM = 1       # 必须扰动的按钮数量=1
RANDOM_SEED  = None    # 固定随机种子可设 int；None 用系统熵
SAVE_JSON    = True    # 是否保存每页元信息 JSON

# ─── 文本扰动 ───────────────────────────────────────────────────────────────
def advanced_perturb_text(text: str) -> str:
    """保证尽量变化；若策略都失败就在末尾加标记。"""
    strategies = [
        lambda s: s.replace('a', '@').replace('e', '3').replace('l', '1').replace('o', '0'),
        lambda s: ''.join(random.sample(s, len(s))) if len(s) > 3 else s,
        lambda s: s[::-1],
        lambda s: ' '.join(list(s)),
        lambda s: 'Submit' if 'order' in s.lower() else s,
        lambda s: s + '!' if not s.endswith('!') else s + '·',
    ]
    original = text
    tried = set()
    for _ in range(len(strategies)):
        strat = random.choice(strategies)
        if strat in tried:
            continue
        tried.add(strat)
        perturbed = strat(original)
        if perturbed != original:
            return perturbed
    return original + '·'

# ─── 工具函数 ───────────────────────────────────────────────────────────────
def setup_logging(out_root: Path):
    out_root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=out_root / LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger().addHandler(console)


def find_html_files(root: Path):
    """返回 [(diff, page_id, html_path), ...]"""
    triples = []
    for diff in ["easy", "medium", "hard"]:
        diff_dir = root / diff
        if not diff_dir.exists():
            continue
        for f in diff_dir.glob("*.html"):
            triples.append((diff, f.stem, f))
    return triples


def draw_boxes(image_path: Path, boxes, save_path: Path):
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except:
        font = ImageFont.load_default()
    for b in boxes:
        x, y, w, h = map(int, b["bbox"])
        if w <= 0 or h <= 0:
            continue
        draw.rectangle([x, y, x + w, y + h], outline="red", width=3)
        draw.text((x, max(0, y - 20)), str(b["id"]), fill="red", font=font)
    img.save(save_path)


# ─── 核心处理 ───────────────────────────────────────────────────────────────
def process_one_html(diff: str, page_id: str, html_path: Path, out_root: Path) -> bool:
    page_out_dir = out_root / diff / page_id
    page_out_dir.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page    = browser.new_page()
            page.goto(f"file://{html_path.resolve()}")

            # 整页截图尺寸
            width  = page.evaluate("() => document.documentElement.scrollWidth")
            height = page.evaluate("() => document.documentElement.scrollHeight")
            page.set_viewport_size({"width": width, "height": height})

            # 采集按钮
            elements = page.evaluate("""
                () => {
                    const data = [];
                    document.querySelectorAll('button').forEach((btn, idx) => {
                        const rect = btn.getBoundingClientRect();
                        const plain = btn.childElementCount === 0;
                        const text  = btn.innerText.trim();
                        btn.setAttribute('data-btn-idx', idx);
                        data.push({
                            idx,
                            text,
                            is_plain: plain,
                            bbox: [rect.x, rect.y, rect.width, rect.height]
                        });
                    });
                    return data;
                }
            """)

            candidates = [b for b in elements if b["is_plain"] and b["text"]]
            if len(candidates) < NEED_BTN_NUM:
                raise RuntimeError(f"plain-text buttons < {NEED_BTN_NUM}")

            selected = random.sample(candidates, NEED_BTN_NUM)
            selected.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
            for i, b in enumerate(selected, 1):
                b["id"] = i

            # 截 BEFORE (只用来画框，稍后删)
            tmp_before = page_out_dir / "_tmp_before.png"
            page.screenshot(path=str(tmp_before), full_page=True)

            annotated_before = page_out_dir / "annotated_before.png"
            draw_boxes(tmp_before, selected, annotated_before)

            # 扰动并确保变化
            for b in selected:
                perturbed = advanced_perturb_text(b["text"])
                if perturbed == b["text"]:
                    raise RuntimeError("perturbation failed (no change)")
                b["perturbed_text"] = perturbed

            page.evaluate("""
                sel => {
                    sel.forEach(s => {
                        const btn = document.querySelector(`button[data-btn-idx="${s.idx}"]`);
                        if (btn) btn.innerText = s.perturbed_text;
                    });
                }
            """, selected)

            # AFTER
            tmp_after = page_out_dir / "_tmp_after.png"
            page.screenshot(path=str(tmp_after), full_page=True)

            annotated_after = page_out_dir / "annotated_after.png"
            draw_boxes(tmp_after, selected, annotated_after)

            browser.close()

        # 删除临时原图
        try:
            tmp_before.unlink()
            tmp_after.unlink()
        except Exception:
            pass

        if SAVE_JSON:
            meta = {
                "difficulty": diff,
                "page_id": page_id,
                "html_file": str(html_path),
                "annotated_before": str(annotated_before),
                "annotated_after": str(annotated_after),
                "selected_buttons": [
                    {
                        "id": b["id"],
                        "idx": b["idx"],
                        "original_text": b["text"],
                        "perturbed_text": b["perturbed_text"],
                        "bounding_box": list(map(int, b["bbox"]))
                    } for b in selected
                ]
            }
            with open(page_out_dir / "analysis_result.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

        logging.info(f"✓ {diff}/{page_id} done")
        return True

    except Exception as e:
        logging.error(f"✗ {diff}/{page_id} failed: {e}")
        logging.error(traceback.format_exc())
        # 清理半成品
        try:
            for f in page_out_dir.glob("*"):
                f.unlink()
            page_out_dir.rmdir()
        except Exception:
            pass
        return False


def main():
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)

    out_root = Path(OUTPUT_ROOT)
    setup_logging(out_root)

    triples = find_html_files(Path(INPUT_ROOT))
    if not triples:
        logging.error("No HTML files found. Check INPUT_ROOT.")
        return

    failed_csv_path = out_root / FAILED_CSV
    write_header = not failed_csv_path.exists()
    failed_f = failed_csv_path.open("a", newline="", encoding="utf-8-sig")
    failed_writer = csv.writer(failed_f)
    if write_header:
        failed_writer.writerow(["difficulty", "page_id", "html_path", "reason"])
        failed_f.flush()

    ok = 0
    with tqdm(triples, desc="HTML pages", unit="page") as bar:
        for diff, page_id, html_path in bar:
            bar.set_postfix_str(page_id)
            if process_one_html(diff, page_id, html_path, out_root):
                ok += 1
            else:
                failed_writer.writerow([diff, page_id, str(html_path), "perturb_fail_or_exception"])
                failed_f.flush()

    failed_f.close()
    logging.info(f"Completed: {ok}/{len(triples)} succeed. Failed list -> {failed_csv_path}")
    print(f"✔ Done. Success {ok}/{len(triples)}. Failed CSV: {failed_csv_path}")


if __name__ == "__main__":
    main()