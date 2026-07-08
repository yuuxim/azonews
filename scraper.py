#!/usr/bin/env python3
"""
AZONEWS Scraper v2
通过分类页面抓取 Azone International 产品数据，更新 products.json
主页产品是 AJAX 动态加载的，改为直接抓各分类页面
"""

import json, re, time, os
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

PRODUCTS_FILE = os.path.join(os.path.dirname(__file__), "products.json")

# 从官网侧边栏提取的所有分类 ID 及名称
CATEGORIES = [
    (103,  "orig",    "アゾンオリジナルドール"),
    (1198, "dreamin", "からふるDreamin'"),
    (101,  "excute",  "えっくす☆きゅーと"),
    (1129, "dreamin", "ルミナスストリート"),
    (377,  "alva",    "サアラズ ア・ラ・モード"),
    (715,  "alva",    "アルヴァスタリア"),
    (549,  "kikipop", "KIKIPOP"),
    (1520, "sugar",   "ビキニメイツ"),
    (1497, "sugar",   "ディアス"),
    (1078, "sugar",   "シュガーカップス"),
    (486,  "sugar",   "リルフェアリー"),
    (877,  "sugar",   "ミミーガーデン"),
    (953,  "iris",    "アイリスコレクトプチ"),
    (721,  "iris",    "アイリスコレクト"),
    (498,  "iris",    "ハピネスクローバー"),
]

BASE = "https://www.azone-int.co.jp/azonet"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,zh-CN;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 状态关键词（日文 → 英文）
STATUS_MAP = [
    ("在庫あり",     "stock"),
    ("受注受付中",   "pre"),
    ("予約受付中",   "pre"),
    ("近日予約開始", "prep"),
    ("準備中",       "prep"),
    ("受注終了",     "closed"),
    ("予約終了",     "closed"),
    ("SOLDOUT",      "sold"),
    ("完売",         "sold"),
    ("売り切れ",     "sold"),
]

def fetch(url):
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=20) as r:
            raw = r.read()
            # 检测编码
            for enc in ("utf-8", "cp932", "euc-jp"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    [fetch error] {url}: {e}")
        return None

def parse_status(html):
    for jp, en in STATUS_MAP:
        if jp in html:
            return en
    return "closed"

def scrape_category(cat_id, cat_key, cat_name):
    """抓取一个分类的所有页面，返回产品列表"""
    products = []
    page = 1
    while True:
        url = f"{BASE}/category/all/{cat_id}" if page == 1 else f"{BASE}/category/all/{cat_id}?page={page}"
        print(f"  [{cat_name}] page {page} → {url}")
        html = fetch(url)
        if not html:
            break

        # 提取产品条目：找所有指向 /item/{barcode} 的链接
        items = re.findall(
            r'<a[^>]+href="[^"]*?/item/(\d{7,13})"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )

        # 也直接从 img src 提取 barcode
        img_barcodes = set(re.findall(r'/image/(\d{7,13})_', html))

        found = {}

        # 从链接中提取产品信息
        for barcode, inner in items:
            if barcode in found:
                continue
            # 尝试从 inner HTML 找图片和名称
            img_m = re.search(r'<img[^>]+src="[^"]*?/image/(\d{7,13})_', inner)
            name_m = re.search(r'alt="([^"]{5,})"', inner)
            img_code = img_m.group(1) if img_m else barcode
            name = name_m.group(1) if name_m else ""
            found[barcode] = {"img": img_code, "name": name}

        # 补充从 img 直接找到的 barcode
        for bc in img_barcodes:
            if bc not in found:
                found[bc] = {"img": bc, "name": ""}

        # 如果啥都没找到，跳出
        if not found:
            # 尝试备用选择器：提取所有产品卡片
            # Azone 产品卡通常在 <div class="col-xs-..."> 里包含图片链接
            alt_items = re.findall(r'alt="([^"]{5,})"[^>]*>.*?href="[^"]*?/item/(\d{7,13})"', html)
            for name, barcode in alt_items:
                if barcode not in found:
                    found[barcode] = {"img": barcode, "name": name}

        if not found:
            print(f"    → 0 products (end or parsing failed)")
            break

        # 判断是否有下一页
        has_next = (f"page={page+1}" in html or f"page%3D{page+1}" in html)

        for barcode, info in found.items():
            products.append({
                "img": info["img"],
                "name": info["name"],
                "category": cat_key,
                "series": cat_name,
            })

        print(f"    → {len(found)} products found")

        if not has_next:
            break
        page += 1
        time.sleep(1.2)

    return products

def check_product_status(barcode, existing_status):
    """访问单个产品页面，获取最新库存状态"""
    url = f"{BASE}/item/{barcode}"
    html = fetch(url)
    if not html:
        return existing_status
    return parse_status(html)

def run():
    print("=== AZONEWS Scraper v2 ===\n")

    # 加载现有数据
    existing = []
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
    existing_map = {p["img"]: p for p in existing}
    print(f"Existing products: {len(existing)}\n")

    # 第一步：从分类页抓取产品列表
    all_scraped = {}
    for cat_id, cat_key, cat_name in CATEGORIES:
        items = scrape_category(cat_id, cat_key, cat_name)
        for item in items:
            bc = item["img"]
            if bc not in all_scraped:
                all_scraped[bc] = item
        time.sleep(1.5)

    print(f"\nTotal unique products from categories: {len(all_scraped)}")

    if not all_scraped:
        print("WARNING: Category scraping returned 0 products.")
        print("Falling back to checking status of existing products individually...\n")

        # 备用方案：逐一检查现有产品的状态页面
        updated = 0
        for p in existing:
            old_st = p.get("status", "closed")
            new_st = check_product_status(p["img"], old_st)
            if new_st != old_st:
                print(f"  Status changed: {p['img']} {old_st} → {new_st}")
                p["status"] = new_st
                updated += 1
            time.sleep(0.8)

        if updated > 0:
            with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            print(f"\n✓ Updated {updated} product statuses in products.json")
        else:
            print("\nNo status changes detected. products.json unchanged.")
        return

    # 第二步：合并新抓取数据与现有数据
    merged = {}

    # 先放入现有数据
    for p in existing:
        merged[p["img"]] = dict(p)

    # 更新/添加从分类页抓到的产品
    for bc, scraped in all_scraped.items():
        if bc in merged:
            # 已有产品：更新名称（如果抓到了更好的）
            if scraped.get("name") and not merged[bc].get("name"):
                merged[bc]["name"] = scraped["name"]
        else:
            # 新产品：加入
            merged[bc] = {
                "id": 0,
                "name": scraped.get("name", ""),
                "series": scraped.get("series", ""),
                "category": scraped.get("category", "orig"),
                "scale": "1/6",
                "price": 0,
                "status": "closed",
                "img": bc,
            }

    # 第三步：逐一检查在售产品的状态（仅检查 stock/prep/pre 的，节省请求数）
    active = [p for p in merged.values() if p.get("status") in ("stock", "prep", "pre", "closed")]
    print(f"\nChecking status for {len(active)} active products...")
    for i, p in enumerate(active[:50], 1):  # 每次最多检查50个，避免太慢
        new_st = check_product_status(p["img"], p["status"])
        if new_st != p["status"]:
            print(f"  [{i}] {p['img']}: {p['status']} → {new_st}")
            merged[p["img"]]["status"] = new_st
        time.sleep(0.8)

    # 重新编号并排序
    final = sorted(merged.values(), key=lambda x: x.get("id") or 9999)
    for i, p in enumerate(final, 1):
        p["id"] = i

    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    from collections import Counter
    status_counts = Counter(p["status"] for p in final)
    print(f"\n✓ Saved {len(final)} products to products.json")
    print("Status:", dict(status_counts))

if __name__ == "__main__":
    run()
