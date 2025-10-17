import os
import io
import json
import traceback
import logging
from datetime import datetime
from tkinter import filedialog, Tk
from tkinter import messagebox
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from tqdm import tqdm
import random

def boxes_adjacent(box1, box2, align_tolerance=8, adj_tolerance=4):
    vertical_center1 = box1['y'] + box1['height'] / 2
    vertical_center2 = box2['y'] + box2['height'] / 2

    horizontal_center1 = box1['x'] + box1['width'] / 2
    horizontal_center2 = box2['x'] + box2['width'] / 2
    vertically_aligned = abs(vertical_center1 - vertical_center2) <= align_tolerance


    horizontally_adjacent = (box1['x'] + box1['width'] + adj_tolerance >= box2['x'] and box1['x'] < box2['x']) or \
                            (box2['x'] + box2['width'] + adj_tolerance >= box1['x'] and box2['x'] < box1['x'])


    horizontally_aligned = abs(horizontal_center1 - horizontal_center2) <= align_tolerance
    vertically_adjacent = (box1['y'] + box1['height'] + adj_tolerance >= box2['y'] and box1['y'] < box2['y']) or \
                          (box2['y'] + box2['height'] + adj_tolerance >= box1['y'] and box2['y'] < box1['y'])

    return (vertically_aligned and horizontally_adjacent) or (horizontally_aligned and vertically_adjacent)


def merge_boxes(box1, box2):
    x1 = min(box1['x'], box2['x'])
    y1 = min(box1['y'], box2['y'])
    x2 = max(box1['x'] + box1['width'], box2['x'] + box2['width'])
    y2 = max(box1['y'] + box1['height'], box2['y'] + box2['height'])
    return {
        'x': x1,
        'y': y1,
        'width': x2 - x1,
        'height': y2 - y1
    }


def is_within(box1, box2):
    return (box1['x'] >= box2['x'] and
            box1['y'] >= box2['y'] and
            box1['x'] + box1['width'] <= box2['x'] + box2['width'] and
            box1['y'] + box1['height'] <= box2['y'] + box2['height'])

def setup_logging(output_folder):
    logging.basicConfig(
        filename=os.path.join(output_folder, "analysis.log"),
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger().addHandler(console)


def create_unique_output_folder(base_path=None, prefix="layout_analysis"):
    if base_path is None:
        base_path = os.path.join(os.path.expanduser("~"), "Desktop")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{prefix}_{timestamp}"
    output_path = os.path.join(base_path, folder_name)
    counter = 1
    while os.path.exists(output_path):
        output_path = os.path.join(base_path, f"{folder_name}_{counter}")
        counter += 1
    os.makedirs(output_path, exist_ok=True)
    return output_path


def select_folder(title="Select folder"):
    root = Tk()
    root.withdraw()
    folder_path = filedialog.askdirectory(title=title)
    return folder_path


def find_html_files(folder_path):
    html_files = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(('.html', '.htm')):
                html_files.append(os.path.join(root, file))
    return html_files


def boxes_adjacent(box1, box2, align_tolerance=8, adj_tolerance=4):
    vertical_center1 = box1['y'] + box1['height'] / 2
    vertical_center2 = box2['y'] + box2['height'] / 2
    horizontal_center1 = box1['x'] + box1['width'] / 2
    horizontal_center2 = box2['x'] + box2['width'] / 2
    vertically_aligned = abs(vertical_center1 - vertical_center2) <= align_tolerance
    horizontally_adjacent = (box1['x'] + box1['width'] + adj_tolerance >= box2['x'] and box1['x'] < box2['x']) or \
                            (box2['x'] + box2['width'] + adj_tolerance >= box1['x'] and box2['x'] < box1['x'])
    horizontally_aligned = abs(horizontal_center1 - horizontal_center2) <= align_tolerance
    vertically_adjacent = (box1['y'] + box1['height'] + adj_tolerance >= box2['y'] and box1['y'] < box2['y']) or \
                          (box2['y'] + box2['height'] + adj_tolerance >= box1['y'] and box2['y'] < box1['y'])
    return (vertically_aligned and horizontally_adjacent) or (horizontally_aligned and vertically_adjacent)


def merge_boxes(box1, box2):
    x1 = min(box1['x'], box2['x'])
    y1 = min(box1['y'], box2['y'])
    x2 = max(box1['x'] + box1['width'], box2['x'] + box2['width'])
    y2 = max(box1['y'] + box1['height'], box2['y'] + box2['height'])
    return {'x': x1, 'y': y1, 'width': x2 - x1, 'height': y2 - y1}


def is_within(box1, box2):
    return (box1['x'] >= box2['x'] and
            box1['y'] >= box2['y'] and
            box1['x'] + box1['width'] <= box2['x'] + box2['width'] and
            box1['y'] + box1['height'] <= box2['y'] + box2['height'])

import os

def extract(blocks, url, min_width=30, min_height=30):
    # 处理本地路径
    if os.path.exists(url):
        url = "file://" + os.path.abspath(url)

    # 提取视觉组件
    visual_components = []
    for block in blocks:
        left = block.get("left", 0)
        top = block.get("top", 0)
        width = block.get("width", 0)
        height = block.get("height", 0)

        # 跳过太小的块
        if width < min_width or height < min_height:
            continue

        visual_components.append({
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "text": block.get("text", "")
        })

    return visual_components

def extract_visual_components(url, crop_folder=None):
    """Extract visual components from a webpage, save original full screenshot, and avoid black crops."""
    if os.path.exists(url):
        url = "file://" + os.path.abspath(url)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, timeout=60000)

            total_width = page.evaluate("() => document.documentElement.scrollWidth")
            total_height = page.evaluate("() => document.documentElement.scrollHeight")

            selectors = {
                'video': 'video',
                'image': 'img',
                'text_block': 'p, span, a, strong, h1, h2, h3, h4, h5, h6, li, th, td, label, code, pre, div',
                'form_table': 'form, table, div.form',
                'button': 'button, input[type="button"], input[type="submit"], [role="button"], input',
                'nav_bar': 'nav, [role="navigation"], .navbar, [class~="nav"], [class~="navigation"], [class~="menu"], [class~="navbar"], [id="menu"], [id="nav"], [id="navigation"], [id="navbar"]',
                'divider': 'hr, [class*="separator"], [class*="divider"], [id="separator"], [id="divider"], [role="separator"]',
            }

            all_elements = []
            for selector in selectors.values():
                for element in page.query_selector_all(selector):
                    if not element.is_visible():
                        continue
                    box = element.bounding_box()
                    if not box or box['width'] <= 0 or box['height'] <= 0:
                        continue
                    tag_name = element.evaluate("el => el.tagName.toLowerCase()")
                    is_direct_text = element.evaluate(""" 
                        (el) => Array.from(el.childNodes).some(node => 
                            node.nodeType === Node.TEXT_NODE && node.textContent.trim() !== '')
                    """)
                    if tag_name == 'div' and not is_direct_text:
                        continue
                    text_content = element.text_content().strip() if element.evaluate("el => el.innerText") else None
                    all_elements.append({
                        'box': box,
                        'text': text_content or ""
                    })

            # Merge text blocks
            all_elements.sort(key=lambda b: (b['box']['y'], b['box']['x']))
            merged_elements = []
            while all_elements:
                current = all_elements.pop(0)
                index = 0
                while index < len(all_elements):
                    if boxes_adjacent(current['box'], all_elements[index]['box']):
                        current['text'] += " " + all_elements[index]['text']
                        current['box'] = merge_boxes(current['box'], all_elements[index]['box'])
                        del all_elements[index]
                    else:
                        index += 1
                merged_elements.append(current)

            # 给每个块编号
            for idx, block in enumerate(merged_elements):
                block['id'] = str(idx + 1)

            # Clean full screenshot
            image_bytes = page.screenshot(full_page=True, animations="disabled", timeout=60000)
            clean_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

            if crop_folder:
                os.makedirs(crop_folder, exist_ok=True)
                clean_image.save(os.path.join(crop_folder, "original.png"))

            # 随机选择 8 个块
            selected_blocks_output = []
            selected = []
            tries = 0
            max_attempts = 50
            while len(selected) < min(4, len(merged_elements)) and tries < max_attempts:
                block = random.choice(merged_elements)
                if block in selected:
                    tries += 1
                    continue

                x, y, w, h = map(int, (block['box']['x'], block['box']['y'], block['box']['width'], block['box']['height']))
                crop = clean_image.crop((x, y, x + w, y + h))
                if not crop.getbbox():  # Entirely black
                    tries += 1
                    continue

                crop_path = os.path.join(crop_folder, f"crop_{block['id']}.png")
                crop.save(crop_path)
                selected.append(block)

                selected_blocks_output.append({
                    "id": block['id'],
                    "text": block['text'],
                    "box": {
                        'x': block['box']['x'] / total_width,
                        'y': block['box']['y'] / total_height,
                        'width': block['box']['width'] / total_width,
                        'height': block['box']['height'] / total_height
                    }
                })

            # 画出随机选择的那几个块
            if crop_folder:
                screenshot_image = clean_image.copy()
                draw = ImageDraw.Draw(screenshot_image)
                font = ImageFont.load_default()
                for block in selected:
                    box = block['box']
                    x, y, w, h = box['x'], box['y'], box['width'], box['height']
                    draw.rectangle([(x, y), (x + w, y + h)], outline="red", width=2)
                    draw.text((x, y), block['id'], fill="red", font=font)

                screenshot_image.save(os.path.join(crop_folder, "layout_with_boxes.png"))

            # All block info
            output_data = []
            for block in merged_elements:
                b = block['box']
                output_data.append({
                    "id": block['id'],
                    "box": {
                        'x': b['x'] / total_width,
                        'y': b['y'] / total_height,
                        'width': b['width'] / total_width,
                        'height': b['height'] / total_height
                    }
                })

            browser.close()
            return {
                "all_blocks": output_data,
                "selected_blocks": selected_blocks_output,
                "visual_components": extract(merged_elements, url)  # Return extracted visual components
            }

    except Exception as e:
        logging.error(f"Error during extraction: {str(e)}")
        logging.error(traceback.format_exc())
        return {
            "all_blocks": [],
            "selected_blocks": [],
            "visual_components": []
        }

def save_results(output_folder, results):
    try:
        results_path = os.path.join(output_folder, "results.json")
        with open(results_path, 'w') as f:
            json.dump(results, f, indent=4)
        logging.info(f"Results saved to {results_path}")
    except Exception as e:
        logging.error(f"Failed to save results: {str(e)}")
        raise


def analyze_html_file(html_file, output_folder):
    try:
        file_name = os.path.splitext(os.path.basename(html_file))[0]
        file_output_folder = os.path.join(output_folder, file_name)
        os.makedirs(file_output_folder, exist_ok=True)

        screenshot_path = os.path.join(file_output_folder, "layout.png")
        crop_folder = os.path.join(file_output_folder, "random_crops")

        logging.info(f"Analyzing {html_file}...")
        elements = extract_visual_components(html_file, crop_folder)

        result = {
            "html_file": html_file,
            "elements": elements,
            "screenshot": screenshot_path
        }

        with open(os.path.join(file_output_folder, "analysis_result.json"), 'w') as f:
            json.dump(result, f, indent=2)

        # 保存 random crop 的位置信息
        random_crops_path = os.path.join(file_output_folder, "random_crops_info.json")
        with open(random_crops_path, 'w') as f:
            json.dump(elements.get("selected_blocks", []), f, indent=2)

        logging.info(f"Analysis completed for {html_file}")
        return True
    except Exception as e:
        logging.error(f"Failed to analyze {html_file}: {str(e)}")
        logging.error(traceback.format_exc())
        return False

def main():
    try:
        output_folder = create_unique_output_folder()
        setup_logging(output_folder)
        logging.info(f"Output will be saved to: {output_folder}")

        logging.info("Please select the folder containing HTML files")
        html_folder = select_folder("Select Folder with HTML Files")
        if not html_folder:
            logging.error("No folder selected")
            return

        html_files = find_html_files(html_folder)
        if not html_files:
            logging.error("No HTML files found in the selected folder")
            messagebox.showerror("Error", "No HTML files found in the selected folder")
            return

        logging.info(f"Found {len(html_files)} HTML files to analyze")

        success_count = 0
        with tqdm(html_files, desc="Analyzing HTML files") as pbar:
            for html_file in pbar:
                pbar.set_postfix(file=os.path.basename(html_file))
                if analyze_html_file(html_file, output_folder):
                    success_count += 1

        logging.info(f"\nAnalysis completed. Successfully analyzed {success_count}/{len(html_files)} files.")
        messagebox.showinfo("Analysis Complete",
                            f"Analysis completed.\nSuccessfully analyzed {success_count}/{len(html_files)} files.\nResults saved to: {output_folder}")

    except Exception as e:
        logging.error(f"An error occurred during analysis: {str(e)}")
        logging.error(traceback.format_exc())
        messagebox.showerror("Error", f"An error occurred: {str(e)}")


if __name__ == "__main__":
    main()
