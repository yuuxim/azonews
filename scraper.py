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

# アゾンオリジナルドール 的各子系列全部映射到 category="doll"，series 保留子系列名
# ピュアニーモボディ 映射到 category="body"
# 抓取顺序：子系列优先，cat 103 放最后补漏（已存在的 barcode 不会被覆盖）
CATEGORIES = [
    # ── アゾンオリジナルドール 子系列 ──
    (1198, "doll", "からふるDreamin'"),
    (1129, "doll", "ルミナス＊ストリート"),
    (101,  "doll", "えっくす☆きゅーと"),
    (715,  "doll", "アルヴァスタリア"),
    (377,  "doll", "サアラズ ア・ラ・モード"),
    (549,  "doll", "KIKIPOP"),
    (1520, "doll", "ビキニメイツ"),
    (1497, "doll", "ディアス"),
    (1078, "doll", "シュガーカップス"),
    (486,  "doll", "リルフェアリー"),
    (877,  "doll", "ミミーガーデン"),
    (953,  "doll", "アイリスコレクトプチ"),
    (721,  "doll", "アイリスコレクト"),
    (498,  "doll", "ハピネスクローバー"),
    (393,  "doll", "ブラックレイヴン"),
    (374,  "doll", "エレン"),
    (104,  "doll", "キャラクタードール"),
    (103,  "doll", "アゾンオリジナルドール"),  # 最后补漏，避免遗漏未分类产品
    # ── ピュアニーモボディ ──
    (482,  "body", "ピュアニーモボディ"),
]

BASE = "https://www.azone-int.co.jp/azonet"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,zh-CN;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 分类页用的状态提示关键词（仅用于 status_hint，以 parse_status 为准）
STATUS_MAP = [
    ('stock_maru',   'stock'),
    ('stock_batu',   'sold'),
    ('SOLD OUT',     'sold'),
    ('SOLDOUT',      'sold'),
    ('完売',         'sold'),
    ('在庫無し',     'sold'),
    ('在庫なし',     'sold'),
    ('受注終了',     'closed'),
    ('予約終了',     'closed'),
    ('受注受付中',   'pre'),
    ('予約受付中',   'pre'),
    ('近日予約開始', 'prep'),
    ('準備中',       'prep'),
    ('近日発売',     'prep'),
    ('カートに入れる', 'stock'),
    ('在庫あり',     'stock'),
    ('販売中',       'stock'),
]

def fetch(url):
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=25) as r:
            raw = r.read()
            for enc in ("utf-8", "cp932", "euc-jp"):
                try:
                    html = raw.decode(enc)
                    # 统一处理 HTML 实体，方便后续关键词匹配
                    html = (html
                        .replace('&yen;', '¥')
                        .replace('&#165;', '¥')
                        .replace('&#x00A5;', '¥')
                        .replace('&#xA5;', '¥')
                        .replace('&amp;', '&')
                        .replace('&nbsp;', ' ')
                    )
                    return html
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    [fetch error] {url}: {e}")
        return None

def parse_status(html):
    """从产品页面 HTML 判断库存状态"""

    # ── 策略1：Azone 专用 CSS 类（最可靠）──
    # <span class="stock_icon stock_maru"></span> = ○ = 有货 or 预约受付中
    # <span class="stock_icon stock_batu"></span> = × = 无货/售罄
    if 'stock_maru' in html:
        # 预约受付中优先：即使有 ○，若有预约关键词则为 pre
        for kw in ('受注受付中', '予約受付中', '受注受付', '予約受付'):
            if kw in html:
                return 'pre'
        return 'stock'
    if 'stock_batu' in html:
        # 还需区分 sold 和 closed：看页面是否有受注/预约截止文字
        for kw in ('受注終了', '予約終了', '受付終了', '販売終了'):
            if kw in html:
                return 'closed'
        return 'sold'

    # ── 策略2：关键词匹配（含漢字/平假名两种写法）──
    STATUS_MAP_EXTENDED = [
        # sold
        ('SOLD OUT',        'sold'),   # 有空格版本
        ('SOLDOUT',         'sold'),
        ('完売',            'sold'),
        ('売り切れ',        'sold'),
        ('在庫無し',        'sold'),   # 漢字 無
        ('在庫なし',        'sold'),   # 平假名 なし
        ('品切れ',          'sold'),
        # closed
        ('受注終了',        'closed'),
        ('予約終了',        'closed'),
        ('受付終了',        'closed'),
        ('販売終了',        'closed'),
        # pre-order open
        ('受注受付中',      'pre'),
        ('予約受付中',      'pre'),
        ('受注受付',        'pre'),
        ('予約受付',        'pre'),
        # prep / coming soon
        ('近日予約開始',    'prep'),
        ('準備中',          'prep'),
        ('近日発売',        'prep'),
        ('発売予定',        'prep'),
        # stock
        ('カートに入れる',  'stock'),
        ('買い物カゴに入れる', 'stock'),
        ('在庫あり',        'stock'),
        ('販売中',          'stock'),
    ]
    for kw, st in STATUS_MAP_EXTENDED:
        if kw in html:
            return st

    # ── 策略3：JSON-LD schema.org ──
    m = re.search(r'"availability"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
    if m:
        av = m.group(1).lower()
        if 'instock' in av:
            return 'stock'
        if 'outofstock' in av or 'discontinued' in av:
            return 'sold'
        if 'preorder' in av:
            return 'pre'
        if 'comingsoon' in av:
            return 'prep'

    return 'closed'


def detect_scale(name, series=""):
    """从产品名称/系列推断比例尺"""
    if '1／12' in name or '1/12' in name:
        return '1/12'
    if '1／3' in name or '1/3' in name:
        return '1/3'
    if '23cm' in name or '２３ｃｍ' in name:
        return '23cm'
    if '27cm' in name or '２７ｃｍ' in name:
        return '27cm'
    if '7cm' in name:
        return '7cm'
    if 'ピコニーモ' in name or series == 'ピコニーモボディ':
        return '1/12'
    if 'カスタムリリィ' in name:
        return '1/12'
    return '1/6'

def parse_price_from_page(html):
    """从产品页提取含税价格（日元）"""
    def to_int(s):
        try:
            v = int(str(s).replace(',', '').replace('，', '').replace(' ', ''))
            return v if 500 <= v <= 500000 else 0
        except Exception:
            return 0

    # 1. JSON-LD schema（最可靠）
    for m in re.finditer(r'"price"\s*:\s*"?([\d,\.]+)"?', html):
        v = to_int(m.group(1).split('.')[0])
        if v:
            return v

    # 2. 含税価格 — 日文各种写法（¥ 已在 fetch 时从 &yen; 转换）
    patterns = [
        r'税込(?:価格)?[：:]\s*¥?\s*([\d,]+)\s*円?',     # 税込価格：22,000 / 税込：¥22,000
        r'¥\s*([\d,]+)\s*[（(]税込[）)]',                  # ¥22,000（税込）
        r'([\d,]+)\s*円\s*[（(]税込[）)]',                  # 22,000円（税込）
        r'税込\s*¥?\s*([\d,]+)',                            # 税込22,000
        r'含税[価格]*[：:]\s*¥?\s*([\d,]+)',               # 含税価格：22,000
        r'お支払い金額[：:]\s*¥?\s*([\d,]+)',              # お支払い金額：22,000
        r'販売価格[：:]\s*¥?\s*([\d,]+)',                   # 販売価格：22,000
        r'価格[：:]\s*¥?\s*([\d,]+)\s*円',                 # 価格：22,000円
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            v = to_int(m.group(1))
            if v:
                return v

    # 3. ¥数字（兜底，&yen; 已经被转换为 ¥）
    for m in re.finditer(r'¥\s*([\d,]{4,7})', html):
        v = to_int(m.group(1))
        if v:
            return v

    # 4. 数字+円（最宽松兜底）
    for m in re.finditer(r'([\d,]{5,7})\s*円', html):
        v = to_int(m.group(1))
        if v:
            return v

    return 0

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
        # Azone 分页为路径形式：/category/all/103/1、/103/2 ...
        url = f"{BASE}/category/all/{cat_id}/{page}"
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

        # 检查是否存在下一页的路径链接
        # 注意：HTML 中链接带 /azonet/ 前缀，所以不加 / 开头做宽松匹配
        has_next = (
            f"category/all/{cat_id}/{page+1}" in html or   # /azonet/category/all/103/2
            f"page={page+1}" in html or
            f"page%3D{page+1}" in html
        )

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

def check_product_status(barcode, existing_status, existing_price=0):
    """访问单个产品页面获取最新库存状态、名称、价格"""
    url = f"{BASE}/item/{barcode}"
    html = fetch(url)
    if not html:
        return existing_status, "", existing_price

    status = parse_status(html)
    price  = parse_price_from_page(html) or existing_price
    name   = parse_name_from_page(html)

    # ── 调试输出（仅对第一个产品打印原始 HTML 片段，帮助排查）──
    if getattr(check_product_status, '_debug_done', False) is False:
        check_product_status._debug_done = True
        print(f"\n[DEBUG] barcode={barcode}  status={status}  price={price}")
        # 打印 在庫/price/cart 相关片段
        for kw in ['在庫', '円', '¥', 'price', 'cart', 'availability', 'InStock', 'カート', '販売']:
            idx = html.find(kw)
            if idx >= 0:
                snippet = html[max(0,idx-60):idx+100].replace('\n',' ')
                print(f"  [{kw}] ...{snippet}...")
        print()

    return status, name, price

def scrape_homepage_banners():
    """从 Azone 首页提取轮播 banner 图 → {barcode: img_url}"""
    html = fetch("https://www.azone-int.co.jp/")
    if not html:
        return {}
    banners = {}
    # 方法1：<a href="...item/BARCODE"> 内紧跟的 img src
    for m in re.finditer(
        r'<a[^>]+href="[^"]*?/item/(\d{10,13})[^"]*?"[^>]*>\s*(?:<[^/][^>]*>\s*)*'
        r'<img[^>]+src="([^"]+)"',
        html, re.DOTALL
    ):
        bc, img_url = m.group(1), m.group(2)
        if not img_url.startswith('http'):
            img_url = 'https://www.azone-int.co.jp' + img_url
        if bc not in banners:
            banners[bc] = img_url
    # 方法2：img src 文件名中含 barcode（跳过 _0.jpg 缩略图）
    for m in re.finditer(
        r'<img[^>]+src="([^"]*?(\d{10,13})[^"]*?\.jpe?g)"', html
    ):
        img_url, bc = m.group(1), m.group(2)
        if '_0.jpg' in img_url:
            continue
        if not img_url.startswith('http'):
            img_url = 'https://www.azone-int.co.jp' + img_url
        if bc not in banners:
            banners[bc] = img_url
    print(f"  Homepage banners found: {len(banners)}")
    return banners

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
            new_st, new_name, new_price = check_product_status(p["img"], old_st, p.get("price", 0))
            changed = False
            if new_st != old_st:
                print(f"  Status changed: {p['img']} {old_st} → {new_st}")
                p["status"] = new_st
                changed = True
            if new_name and not p.get("name"):
                p["name"] = new_name
                changed = True
            if new_price and not p.get("price"):
                p["price"] = new_price
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

    # 顶级分类名（不作为子系列覆盖依据）
    TOP_LEVEL_NAMES = {"アゾンオリジナルドール", "ピュアニーモボディ"}

    for bc, scraped in all_scraped.items():
        if bc in merged:
            if scraped.get("name") and not merged[bc].get("name"):
                merged[bc]["name"] = scraped["name"]
            # 始终以最新抓取的分类/系列为准（子系列名优先于顶级分类名）
            new_series = scraped.get("series", "")
            old_series = merged[bc].get("series", "")
            if new_series and (
                not old_series
                or old_series in TOP_LEVEL_NAMES      # 旧的是顶级名 → 用子系列名覆盖
                or new_series not in TOP_LEVEL_NAMES  # 新的是子系列名 → 覆盖
            ):
                merged[bc]["series"] = new_series
            if scraped.get("category"):
                merged[bc]["category"] = scraped["category"]
            # 若分类页已有状态提示，更新
            if scraped.get("status_hint") and merged[bc].get("status") == "closed":
                merged[bc]["status"] = scraped["status_hint"]
        else:
            _name = scraped.get("name", "")
            _series = scraped.get("series", "")
            merged[bc] = {
                "id":       0,
                "name":     _name,
                "series":   _series,
                "category": scraped.get("category", "doll"),
                "scale":    detect_scale(_name, _series),
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
        new_st, new_name, new_price = check_product_status(p["img"], old_st, p.get("price", 0))
        changed = []
        if new_st != old_st:
            merged[p["img"]]["status"] = new_st
            merged[p["img"]]["status_at"] = int(time.time())
            changed.append(f"status {old_st}→{new_st}")
        if new_name and not old_name:
            merged[p["img"]]["name"] = new_name
            # 顺便用新名称更新 scale
            new_scale = detect_scale(new_name, merged[p["img"]].get("series",""))
            if new_scale != merged[p["img"]].get("scale","1/6"):
                merged[p["img"]]["scale"] = new_scale
            changed.append("name found")
        if new_price and not merged[p["img"]].get("price"):
            merged[p["img"]]["price"] = new_price
            changed.append(f"price={new_price}")
        if changed:
            print(f"  [{i}/{len(to_check)}] {p['img']}: {', '.join(changed)}")
        time.sleep(0.8)

    # 第四步：抓取首页 banner 图
    print("\nFetching homepage banners...")
    banners = scrape_homepage_banners()
    for bc, img_url in banners.items():
        if bc in merged:
            merged[bc]['hero_img'] = img_url

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
