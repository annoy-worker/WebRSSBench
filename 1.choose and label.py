"""
integrated_analyze_and_label.py
────────────────────────────────────────────────────────────────────────────
① 复刻 1about image 12（old）.py 的选框逻辑（video / image / text_block /
   form_table / button / nav_bar / divider 七大类选择器 + 空 div 过滤）
② 额外随机裁剪 ≤8 个非纯黑块
③ 计算两两空间关系（inside / contain / overlap / 左上右下 8 向）
④ 全部结果写入固定路径
   ├─ layout.png                    # 干净全页
   ├─ layout_with_boxes.png         # 红框编号图
   ├─ random_crops\crop_*.png       # 随机小图
   ├─ analysis_result.json          # 所有块 + 随机块
   ├─ random_crops_info.json        # 随机块信息
   └─ relations.json                # 随机块两两关系
"""

import os, io, json, random, traceback, logging
from tkinter import Tk, filedialog, messagebox
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from tqdm import tqdm

# ───────────────────────── 固定输出目录 ──────────────────────────
OUTPUT_ROOT = r"F:\output\position\？"
os.makedirs(OUTPUT_ROOT, exist_ok=True)

# ───────────────────────── 基础几何工具 ─────────────────────────
def boxes_adjacent(box1, box2, align_tolerance: int = 8, adj_tolerance: int = 4) -> bool:
    """判断两个矩形是否“相邻且大致同一行 / 列”，逻辑与旧脚本保持一致"""
    vc1 = box1["y"] + box1["height"] / 2
    vc2 = box2["y"] + box2["height"] / 2
    hc1 = box1["x"] + box1["width"]  / 2
    hc2 = box2["x"] + box2["width"]  / 2

    vertically_aligned   = abs(vc1 - vc2) <= align_tolerance
    horizontally_adjacent = (
        (box1["x"] + box1["width"]  + adj_tolerance >= box2["x"] and box1["x"] < box2["x"]) or
        (box2["x"] + box2["width"]  + adj_tolerance >= box1["x"] and box2["x"] < box1["x"])
    )

    horizontally_aligned = abs(hc1 - hc2) <= align_tolerance
    vertically_adjacent   = (
        (box1["y"] + box1["height"] + adj_tolerance >= box2["y"] and box1["y"] < box2["y"]) or
        (box2["y"] + box2["height"] + adj_tolerance >= box1["y"] and box2["y"] < box1["y"])
    )

    return (vertically_aligned and horizontally_adjacent) or \
           (horizontally_aligned and vertically_adjacent)


def merge_boxes(box1, box2):
    x1 = min(box1["x"], box2["x"])
    y1 = min(box1["y"], box2["y"])
    x2 = max(box1["x"] + box1["width"],  box2["x"] + box2["width"])
    y2 = max(box1["y"] + box1["height"], box2["y"] + box2["height"])
    return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}

# ───────────────────────── 关系标注工具 ─────────────────────────
def _is_inside(a, b):
    return (a["x"] >= b["x"] and a["y"] >= b["y"] and
            a["x"] + a["width"]  <= b["x"] + b["width"] and
            a["y"] + a["height"] <= b["y"] + b["height"])

def _is_overlap(a, b):
    return not (a["x"] + a["width"]  <= b["x"] or
                b["x"] + b["width"]  <= a["x"] or
                a["y"] + a["height"] <= b["y"] or
                b["y"] + b["height"] <= a["y"])

def _precise_dir(a, b):
    cx1, cy1 = a["x"] + a["width"]/2,  a["y"] + a["height"]/2
    cx2, cy2 = b["x"] + b["width"]/2,  b["y"] + b["height"]/2
    dx, dy, thr = cx1 - cx2, cy1 - cy2, 0.01
    if abs(dx) < thr and abs(dy) < thr: return "overlap"
    if abs(dx) < thr:                   return "top"    if dy < 0 else "bottom"
    if abs(dy) < thr:                   return "left"   if dx < 0 else "right"
    if dx < 0 and dy < 0: return "top-left"
    if dx > 0 and dy < 0: return "top-right"
    if dx < 0 and dy > 0: return "bottom-left"
    return "bottom-right"

def build_relations(blocks):
    relations = []
    for i in range(len(blocks)):
        for j in range(len(blocks)):
            if i == j: continue
            a, b = blocks[i], blocks[j]
            if _is_inside(a["box"], b["box"]):  rel = "inside"
            elif _is_inside(b["box"], a["box"]): rel = "contain"
            elif _is_overlap(a["box"], b["box"]): rel = "overlap"
            else: rel = _precise_dir(a["box"], b["box"])
            relations.append({"id": a["id"], "vs": b["id"], "relation": f"A {rel} B"})
    return relations

# ───────────────────── 视觉组件提取（完整逻辑） ──────────────────
def extract_visual_components(path_or_url: str, crop_dir: str, max_random: int = 8):
    # 1) 处理 file://
    url = "file://" + os.path.abspath(path_or_url) if os.path.exists(path_or_url) else path_or_url

    # 2) Playwright 抓取
    with sync_playwright() as p:
        page = p.chromium.launch().new_page()
        page.goto(url, timeout=60000)

        W = page.evaluate("() => document.documentElement.scrollWidth")
        H = page.evaluate("() => document.documentElement.scrollHeight")

        # 3) 七大类选择器（与旧脚本一致）
        selectors = {
            "video":      "video",
            "image":      "img",
            "text_block": ("p, span, a, strong, h1, h2, h3, h4, h5, h6, li, th, td, "
                           "label, code, pre, div"),
            "form_table": "form, table, div.form",
            "button":     ("button, input[type='button'], input[type='submit'], "
                           "[role='button'], input[type='reset'], input[type='image'], input"),
            "nav_bar":    ("nav, [role='navigation'], .navbar, [class*='nav'], "
                           "[id='menu'], [id='nav'], [id='navigation'], [id='navbar']"),
            "divider":    ("hr, [class*='separator'], [class*='divider'], "
                           "[id='separator'], [id='divider'], [role='separator']"),
        }

        # 4) 抽取元素
        elements = []
        for css in selectors.values():
            for el in page.query_selector_all(css):
                if not el.is_visible():
                    continue
                box = el.bounding_box()
                if not box or box["width"] <= 0 or box["height"] <= 0:
                    continue
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                is_direct_text = el.evaluate("""(e) => Array.from(e.childNodes)
                    .some(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim() !== '')""")
                if tag == "div" and not is_direct_text:
                    continue
                txt = (el.text_content() or "").strip()
                elements.append({"box": box, "text": txt})

        # 5) 合并相邻文本块
        elements.sort(key=lambda b: (b["box"]["y"], b["box"]["x"]))
        merged = []
        while elements:
            cur = elements.pop(0)
            i = 0
            while i < len(elements):
                if boxes_adjacent(cur["box"], elements[i]["box"]):
                    cur["text"] += " " + elements[i]["text"]
                    cur["box"]   = merge_boxes(cur["box"], elements[i]["box"])
                    del elements[i]
                else:
                    i += 1
            merged.append(cur)

        # 6) 全页截图 + 编号红框
        img_bytes = page.screenshot(full_page=True, animations="disabled")
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        os.makedirs(crop_dir, exist_ok=True)
        img.save(os.path.join(crop_dir, "layout.png"))

        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        for idx, blk in enumerate(merged, 1):
            x, y, w, h = blk["box"].values()
            draw.rectangle([(x, y), (x + w, y + h)], outline="red", width=2)
            draw.text((x, y), str(idx), fill="red", font=font)
            blk["id"] = str(idx)
        img.save(os.path.join(crop_dir, "layout_with_boxes.png"))

        # 7) 随机 ≤ max_random 块裁剪（避纯黑）
        selected = []
        tries, max_tries = 0, 50
        while len(selected) < min(max_random, len(merged)) and tries < max_tries:
            blk = random.choice(merged);  tries += 1
            if blk in selected:
                continue
            x, y, w, h = map(int, (blk["box"]["x"], blk["box"]["y"],
                                   blk["box"]["width"], blk["box"]["height"]))
            crop = img.crop((x, y, x + w, y + h))
            if not crop.getbbox():   # 纯黑
                continue
            crop.save(os.path.join(crop_dir, f"crop_{blk['id']}.png"))
            selected.append(blk)

        # 8) 归一化坐标
        def norm(b):  # → 0~1
            return {"x": b["x"]/W, "y": b["y"]/H, "width": b["width"]/W, "height": b["height"]/H}

        all_blocks     = [{"id": blk["id"], "box": norm(blk["box"])} for blk in merged]
        selected_info  = [{"id": blk["id"], "text": blk["text"], "box": norm(blk["box"])}
                          for blk in selected]

        return all_blocks, selected_info

# ───────────────────────── 主单文件分析 ─────────────────────────
def analyze_html_file(html_path: str):
    name = os.path.splitext(os.path.basename(html_path))[0]
    target_dir = os.path.join(OUTPUT_ROOT, name)
    crops_dir  = os.path.join(target_dir, "random_crops")
    os.makedirs(target_dir, exist_ok=True)

    # 抽取 + 随机截块
    all_blocks, selected = extract_visual_components(html_path, crops_dir)

    # 写 JSON
    with open(os.path.join(target_dir, "analysis_result.json"), "w", encoding="utf-8") as f:
        json.dump({"html_file": html_path, "elements": {
            "all_blocks": all_blocks,
            "selected_blocks": selected}}, f, indent=2, ensure_ascii=False)

    with open(os.path.join(target_dir, "random_crops_info.json"), "w", encoding="utf-8") as f:
        json.dump(selected, f, indent=2, ensure_ascii=False)

    # 关系标注
    if len(selected) >= 2:
        rels = build_relations(selected)
        with open(os.path.join(target_dir, "relations.json"), "w", encoding="utf-8") as f:
            json.dump(rels, f, indent=2, ensure_ascii=False)

    return True

# ────────────────────────── 批量入口 ───────────────────────────
def main():
    logging.basicConfig(filename=os.path.join(OUTPUT_ROOT, "analysis.log"),
                        level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")

    # 选 HTML 根目录
    root = Tk(); root.withdraw()
    html_root = filedialog.askdirectory(title="请选择包含 HTML 文件的文件夹")
    if not html_root:
        messagebox.showerror("Error", "未选择 HTML 文件夹"); return

    html_files = [os.path.join(r, f)
                  for r, _, fs in os.walk(html_root)
                  for f in fs if f.lower().endswith(('.html', '.htm'))]
    if not html_files:
        messagebox.showerror("Error", "未找到任何 HTML 文件"); return

    ok = 0
    with tqdm(html_files, desc="Analyzing") as bar:
        for f in bar:
            bar.set_postfix(file=os.path.basename(f))
            try:
                if analyze_html_file(f): ok += 1
            except Exception as e:
                logging.error("%s\n%s", str(e), traceback.format_exc())

    messagebox.showinfo("完成",
        f"成功分析 {ok}/{len(html_files)} 个文件\n结果已保存至：\n{OUTPUT_ROOT}")

if __name__ == "__main__":
    main()
