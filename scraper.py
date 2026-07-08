#!/usr/bin/env python3
"""
AZONEWS Scraper v3
只抓取 アゾンオリジナルドール（cat 103）和 ピュアニーモボディ（cat 482）两个分类
改进库存状态检测，修复产品名称缺失问题
"""

import json, re, time, os
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

PRODUCTS_FILE = os.path.join(os.path.dirname(__file__), "products.json")

# 只抓取两个目标分类
CATEGORIES = [
    (103,  "doll", "アゾンオリジナルドール"),
    (482,  "body", "ピュアニーモボディ"),
]

BASE = "https://www.azone-int.co.jp/azonet"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,zh-CN;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 状态关键词（日文/英文 → 内部状态）优先级从高到低
# 先检查"结束/售罄"再检查"有货"，防止误判
STATUS_MAP = [
    # 售罄（最高优先级）
    ("SOLDOUT",             "sold"),
    ("完売",                "sold"),
    ("売り切れ",            "sold"),
    ("在庫なし",            "sold"),
    ("品切れ",              "sold"),
    # 预约/受注截止
    ("受注終了",            "closed"),
    ("予約終了",            "closed"),
    ("受付終了",            "closed"),
    ("販売終了",            "closed"),
    # 预约受付中
    ("受注受付中",          "pre"),
    ("予約受付中",          "pre"),
    ("受注受付",            "pre"),
    ("予約受付",            "pre"),
    # 准备中/即将发售
    ("近日予約開始",        "prep"),
    ("準備中",              "prep"),
    ("近日発売",            "prep"),
    ("発売予定",            "prep"),
    # 有货（购物车 = 最可靠标志）
    ("カートに入れる",      "stock"),
    ("買い物カゴに入れる",  "stock"),
    ("cart/add",            "stock"),
    ("addcart",             "stock"),
    ("在庫あり",            "stock"),
    ("在庫：",              "stock"),
    ("在庫数",              "stock"),
    ("ご購入はこちら",      "stock"),
    ("数量",                "stock"),   # 数量输入框 = 可购买
]

def fetch(url):
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=25) as r:
            raw = r.read()
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
    """从产品页面 HTML 判断库存状态"""
    for jp, en in STATUS_MAP:
        if jp in html:
            return en
    # 额外检查：购买表单
    if re.search(r'<form[^>]+(?:cart|purchase|order|buy)', html, re.IGNORECASE):
        return "stock"
    # 提交按钮中包含购买相关词
    if re.search(r'(?:value|>)\s*(?:購入|買う|注文|カゴ|cart)', html, re.IGNORECASE):
        return "stock"
    return "closed"

def parse_name_from_page(html):
    """从产品详情页提取产品名称"""
    # 尝试 h1/h2 标题
    for tag in ('h1', 'h2'):
        m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', html, re.DOTALL)
        if m:
            name = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if len(name) >= 5:
                return name
    # 尝试 og:title
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]{5,})"', html)
    if m:
        return m.group(1).strip()
    # 尝试 title 标签（去掉站点名称）
    m = re.search(r'<title>([^<]{5,})</title>', html)
    if m:
        t = m.group(1).strip()
        # 去掉常见后缀如 " | AZONE ONLINE STORE"
        t = re.sub(r'\s*[|\-–]\s*.{3,}$', '', t)
        if len(t) >= 5:
            return t
    return ""

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

        found = {}

        # 方法1：找所有指向 /item/{barcode} 的链接，捕获内部 HTML
        items = re.findall(
            r'<a[^>]+href="[^"]*?/item/(\d{7,13})"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        for barcode, inner in items:
            if barcode in found:
                continue
            img_m  = re.search(r'<img[^>]+src="[^"]*?/image/(\d{7,13})_', inner)
            # 优先取 alt 文本作为名称
            name_m = re.search(r'alt="([^"]{5,})"', inner)
            # 若 alt 不够，尝试取纯文本
            if not name_m:
                txt = re.sub(r'<[^>]+>', '', inner).strip()
                txt = re.sub(r'\s+', ' ', txt)
                name_m_txt = txt if len(txt) >= 5 else ""
            else:
                name_m_txt = ""
            img_code = img_m.group(1) if img_m else barcode
            name = name_m.group(1) if name_m else name_m_txt
            # 尝试从 surrounding context 获取状态标签
            status_hint = ""
            for jp, en in STATUS_MAP:
                if jp in inner:
                    status_hint = en
                    break
            found[barcode] = {"img": img_code, "name": name, "status_hint": status_hint}

        # 方法2：从 img src 补充遗漏的 barcode
        img_barcodes = set(re.findall(r'/image/(\d{7,13})_', html))
        for bc in img_barcodes:
            if bc not in found:
                found[bc] = {"img": bc, "name": "", "status_hint": ""}

        if not found:
            print(f"    → 0 products (end or parsing failed)")
            break

        has_next = (f"page={page+1}" in html or f"page%3D{page+1}" in html)

        for barcode, info in found.items():
            products.append({
                "img":          info["img"],
                "name":         info["name"],
                "category":     cat_key,
                "series":       cat_name,
                "status_hint":  info["status_hint"],
            })

        print(f"    → {len(found)} products found")

        if not has_next:
            break
        page += 1
        time.sleep(1.2)

    return products

def check_product_status(barcode, existing_status):
    """访问单个产品页面获取最新库存状态；同时尝试获取名称"""
    url = f"{BASE}/item/{barcode}"
    html = fetch(url)
    if not html:
        return existing_status, ""
    return parse_status(html), parse_name_from_page(html)

def run():
    print("=== AZONEWS Scraper v3 ===\n")

    # 加载现有数据（只保留目标分类）
    target_keys = {cat_key for _, cat_key, _ in CATEGORIES}
    existing_all = []
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            existing_all = json.load(f)
    # 只保留目标分类的现有数据
    existing = [p for p in existing_all if p.get("category") in target_keys]
    existing_map = {p["img"]: p for p in existing}
    print(f"Existing target-category products: {len(existing)} / {len(existing_all)} total\n")

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
        print("WARNING: Category scraping returned 0 products. Checking existing products individually...")
        updated = 0
        for p in existing:
            old_st = p.get("status", "closed")
            new_st, new_name = check_product_status(p["img"], old_st)
            changed = False
            if new_st != old_st:
                print(f"  Status changed: {p['img']} {old_st} → {new_st}")
                p["status"] = new_st
                changed = True
            if new_name and not p.get("name"):
                print(f"  Name found: {p['img']} → {new_name[:40]}")
                p["name"] = new_name
                changed = True
            if changed:
                updated += 1
            time.sleep(0.8)
        if updated > 0:
            with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            print(f"\n✓ Updated {updated} products in products.json")
        else:
            print("\nNo changes detected.")
        return

    # 第二步：合并
    merged = {}
    for p in existing:
        merged[p["img"]] = dict(p)

    for bc, scraped in all_scraped.items():
        if bc in merged:
            if scraped.get("name") and not merged[bc].get("name"):
                merged[bc]["name"] = scraped["name"]
            # 若分类页已有状态提示，更新
            if scraped.get("status_hint") and merged[bc].get("status") == "closed":
                merged[bc]["status"] = scraped["status_hint"]
        else:
            merged[bc] = {
                "id":       0,
                "name":     scraped.get("name", ""),
                "series":   scraped.get("series", ""),
                "category": scraped.get("category", "doll"),
                "scale":    "1/6",
                "price":    0,
                "status":   scraped.get("status_hint") or "closed",
                "img":      bc,
            }

    # 第三步：逐一检查所有产品的状态（不限数量）
    # 优先检查"有可能有货"的产品（非 sold 的）
    to_check = [p for p in merged.values() if p.get("status") != "sold"]
    print(f"\nChecking status for all {len(to_check)} non-sold products...")
    for i, p in enumerate(to_check, 1):
        old_st  = p.get("status", "closed")
        old_name = p.get("name", "")
        new_st, new_name = check_product_status(p["img"], old_st)
        changed = []
        if new_st != old_st:
            merged[p["img"]]["status"] = new_st
            changed.append(f"status {old_st}→{new_st}")
        if new_name and not old_name:
            merged[p["img"]]["name"] = new_name
            changed.append(f"name found")
        if changed:
            print(f"  [{i}/{len(to_check)}] {p['img']}: {', '.join(changed)}")
        time.sleep(0.8)

    # 重新编号、排序
    final = sorted(merged.values(), key=lambda x: x.get("id") or 9999)
    for i, p in enumerate(final, 1):
        p["id"] = i

    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    from collections import Counter
    status_counts = Counter(p["status"] for p in final)
    no_name = sum(1 for p in final if not p.get("name"))
    print(f"\n✓ Saved {len(final)} products to products.json")
    print(f"  Status: {dict(status_counts)}")
    print(f"  No name: {no_name}")

if __name__ == "__main__":
    run()
