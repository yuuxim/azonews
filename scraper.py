#!/usr/bin/env python3
"""
AZONEWS Scraper
自动抓取 Azone International 官方商店的产品数据，更新 products.json
"""

import json
import re
import time
import os
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

BASE_URL = "https://www.azone-int.co.jp/azonet/"
PRODUCTS_FILE = os.path.join(os.path.dirname(__file__), "products.json")
MAX_PAGES = 20  # 最多抓取页数

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,zh-CN;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 系列名到分类的映射
SERIES_TO_CAT = {
    "からふるDreamin": "dreamin", "ルミナス": "dreamin",
    "えっくす☆きゅーと": "excute", "Melty": "excute", "ピコえっくす": "excute",
    "Alvastaria": "alva", "サアラズ": "alva",
    "SugarCups": "sugar", "Lil'Fairy": "sugar", "DIAS": "sugar",
    "LilFairy": "sugar", "ミミーガーデン": "sugar", "Bikini Mates": "sugar",
    "Honey Bear": "sugar", "ハニーベア": "sugar",
    "Iris Collect": "iris", "アイリスコレクト": "iris",
    "Poe-Poe": "iris", "s*t*j": "iris",
    "KIKIPOP": "kikipop",
}

# 库存状态关键词映射
STATUS_KEYWORDS = {
    "在庫あり": "stock",
    "受注受付中": "pre",
    "予約受付中": "pre",
    "近日予約開始": "prep",
    "準備中": "prep",
    "受注終了": "closed",
    "予約終了": "closed",
    "完売": "sold",
    "売り切れ": "sold",
    "SOLDOUT": "sold",
}


def guess_cat(series_name):
    for key, cat in SERIES_TO_CAT.items():
        if key in series_name:
            return cat
    return "orig"


def parse_status(text):
    for jp, en in STATUS_KEYWORDS.items():
        if jp in text:
            return en
    return "closed"


def fetch(url):
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=15) as resp:
            charset = "utf-8"
            ct = resp.headers.get("Content-Type", "")
            m = re.search(r"charset=([^\s;]+)", ct)
            if m:
                charset = m.group(1).lower().replace("shift_jis", "cp932")
            return resp.read().decode(charset, errors="replace")
    except (HTTPError, URLError) as e:
        print(f"  [ERROR] {url}: {e}")
        return None


class AzoneParser(HTMLParser):
    """解析 Azone 商店列表页，提取产品信息"""

    def __init__(self):
        super().__init__()
        self.products = []
        self._in_item = False
        self._in_name = False
        self._in_price = False
        self._in_status = False
        self._cur = {}
        self._depth = 0
        self._item_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        self._depth += 1

        # 产品卡片容器（根据实际 HTML 可能需要调整）
        if tag == "div" and any(k in cls for k in ["item_block", "item-block", "product_item", "product-item", "itemBox"]):
            self._in_item = True
            self._item_depth = self._depth
            self._cur = {}

        if not self._in_item:
            return

        # 产品图片（含 barcode）
        if tag == "img":
            src = attrs.get("src", "")
            m = re.search(r"/image/(\d{13})_", src)
            if m:
                self._cur["img"] = m.group(1)
            # alt 作为名称备用
            if not self._cur.get("name") and attrs.get("alt"):
                self._cur["name"] = attrs["alt"].strip()

        # 产品链接（含 barcode）
        if tag == "a":
            href = attrs.get("href", "")
            m = re.search(r"/item/(\d{13})", href)
            if m and not self._cur.get("img"):
                self._cur["img"] = m.group(1)

        # 价格
        if tag in ("span", "p", "div") and any(k in cls for k in ["price", "item_price"]):
            self._in_price = True

        # 状态
        if tag in ("span", "p", "div") and any(k in cls for k in ["status", "stock", "item_status", "label"]):
            self._in_status = True

        # 名称
        if tag in ("h3", "h4", "p", "span") and any(k in cls for k in ["name", "item_name", "title", "item_title"]):
            self._in_name = True

    def handle_endtag(self, tag):
        if self._in_item and self._depth == self._item_depth:
            # 结束一个产品块
            if self._cur.get("img") and self._cur.get("name"):
                self.products.append(dict(self._cur))
            self._in_item = False
            self._cur = {}
        self._depth -= 1
        self._in_name = False
        self._in_price = False
        self._in_status = False

    def handle_data(self, data):
        data = data.strip()
        if not data or not self._in_item:
            return
        if self._in_name and not self._cur.get("name"):
            self._cur["name"] = data
        if self._in_price:
            m = re.search(r"[\d,]+", data)
            if m:
                try:
                    self._cur["price"] = int(m.group().replace(",", ""))
                except ValueError:
                    pass
        if self._in_status:
            s = parse_status(data)
            if s != "closed" or not self._cur.get("status"):
                self._cur["status"] = s


def scrape_page(page_num):
    """抓取一页产品列表"""
    url = BASE_URL if page_num == 1 else f"{BASE_URL}?p={page_num}"
    print(f"  Fetching page {page_num}: {url}")
    html = fetch(url)
    if not html:
        return [], False

    # 检查是否有下一页
    has_next = f"?p={page_num + 1}" in html or f"page={page_num + 1}" in html

    parser = AzoneParser()
    parser.feed(html)

    # 从 img src 中直接提取 barcode（更可靠的补充方法）
    barcodes = re.findall(r'/image/(\d{13})_0\.jpg', html)
    names_raw = re.findall(r'alt="([^"]{10,})"', html)

    # 尝试提取价格和状态
    prices = [int(p.replace(",", "")) for p in re.findall(r'([\d,]+)円', html)]
    statuses_raw = []
    for jp, en in STATUS_KEYWORDS.items():
        if jp in html:
            statuses_raw.append(en)

    products = parser.products

    # 如果 HTML parser 没抓到，退回 regex 方法
    if not products and barcodes:
        print(f"    Fallback to regex extraction: {len(barcodes)} barcodes found")
        for i, bc in enumerate(barcodes):
            name = names_raw[i] if i < len(names_raw) else f"Product {bc}"
            price = prices[i] if i < len(prices) else 0
            products.append({
                "img": bc,
                "name": name,
                "price": price,
                "status": "closed",
            })

    print(f"    Found {len(products)} products on page {page_num}")
    return products, has_next


def enrich_product(p, existing_map):
    """补全产品信息（系列、分类等）"""
    img = p.get("img", "")
    existing = existing_map.get(img, {})

    # 系列：优先用已有数据
    series = existing.get("series") or p.get("series", "")
    category = existing.get("category") or guess_cat(series) or "orig"

    # 尝试从名称猜系列
    name = p.get("name", "")
    if not series:
        for key in SERIES_TO_CAT:
            if key in name:
                series = key
                break

    return {
        "id": existing.get("id") or 0,
        "name": name or existing.get("name", ""),
        "series": series or existing.get("series", ""),
        "category": category,
        "scale": existing.get("scale", "1/6"),
        "price": p.get("price") or existing.get("price", 0),
        "status": p.get("status") or existing.get("status", "closed"),
        "img": img,
    }


def run():
    print("=== AZONEWS Scraper ===")

    # 加载现有数据（作为备用和补充）
    existing_products = []
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            existing_products = json.load(f)
        print(f"Loaded {len(existing_products)} existing products")
    existing_map = {p["img"]: p for p in existing_products}

    all_raw = []
    for page in range(1, MAX_PAGES + 1):
        items, has_next = scrape_page(page)
        all_raw.extend(items)
        if not has_next or not items:
            print(f"  No more pages after page {page}")
            break
        time.sleep(1.5)  # 礼貌性延迟，避免频繁请求

    print(f"\nTotal raw products scraped: {len(all_raw)}")

    if not all_raw:
        print("WARNING: Scraping returned 0 products. Keeping existing data unchanged.")
        return

    # 去重（按 img barcode）
    seen = {}
    for p in all_raw:
        if p.get("img") and p["img"] not in seen:
            seen[p["img"]] = p

    # 补全信息
    products = []
    for i, (img, p) in enumerate(seen.items(), 1):
        enriched = enrich_product(p, existing_map)
        enriched["id"] = i
        products.append(enriched)

    # 保存
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Saved {len(products)} products to products.json")

    # 统计
    from collections import Counter
    status_counts = Counter(p["status"] for p in products)
    print("Status breakdown:", dict(status_counts))


if __name__ == "__main__":
    run()
