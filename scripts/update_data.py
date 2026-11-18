import json
import re
import http.cookiejar
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from sentence_transformers import SentenceTransformer

BASE_URL = "https://knowledgebase.treasury.gov.my/kb"

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.addheaders = [
    ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
    ("Accept-Language", "ms-MY,ms;q=0.9,en;q=0.8"),
]

def request_page(url, post_data=None, referer=None):
    headers = {}
    if referer:
        headers["Referer"] = referer
    data = urllib.parse.urlencode(post_data).encode("utf-8") if post_data else None
    req = urllib.request.Request(url, data=data, headers=headers)
    with opener.open(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def scrape_mof_with_session():
    records = []
    # Langkah 1: Lawat halaman utama dahulu untuk dapatkan CFID/CFTOKEN (session cookie)
    try:
        request_page(f"{BASE_URL}/index.cfm")
    except Exception as e:
        print(f"Gagal buka index.cfm: {e}")
        return []

    targets = [
        ("asset.cfm?subsystem_type=asset", "ASET_ALIH"),
        ("asset.cfm?subsystem_type=immovable", "ASET_TAK_ALIH"),
        ("asset.cfm?subsystem_type=intangible", "ASET_TAK_KETARA"),
        ("asset.cfm?subsystem_type=stock", "STOK"),
    ]

    for rel_url, jenis_label in targets:
        full_url = f"{BASE_URL}/{rel_url}"
        try:
            # Lawatan GET dahulu supaya pemboleh ubah DSPTITLE diisytiharkan oleh pelayan ColdFusion
            get_html = request_page(full_url, referer=f"{BASE_URL}/index.cfm")
            soup_get = BeautifulSoup(get_html, "html.parser")

            # Ekstrak sebarang input tersembunyi (seperti DSPTITLE) daripada borang sebenar
            form_payload = {}
            for inp in soup_get.find_all("input"):
                name = inp.get("name")
                if name:
                    form_payload[name] = inp.get("value", "")

            form_payload["keyword"] = ""
            form_payload["btnSearch"] = "Cari"

            post_html = request_page(full_url, post_data=form_payload, referer=full_url)
            soup = BeautifulSoup(post_html, "html.parser")

            for box in soup.select(".product-grid, .item, .thumbnail, .card, div[class*='col-']"):
                text = box.get_text(" ", strip=True)
                kod_match = re.search(r"\b(\d{9,16})\b", text)
                if not kod_match:
                    continue
                kod = kod_match.group(1)

                img_src = ""
                img_tag = box.find("img")
                if img_tag and img_tag.get("src"):
                    src = img_tag["src"].strip()
                    if "no_image" not in src.lower() and "no-image" not in src.lower():
                        img_src = urllib.parse.urljoin(f"{BASE_URL}/", src)

                lines = [ln.strip() for ln in box.get_text("\n").splitlines() if ln.strip()]
                nama = ""
                for ln in lines:
                    if kod not in ln and len(ln) > 2:
                        nama = ln
                        break

                if kod and nama:
                    records.append({
                        "kod": kod,
                        "jenis": jenis_label,
                        "kategori": "-",
                        "sub_kategori": "-",
                        "nama": nama,
                        "keterangan": "",
                        "gambar": img_src,
                    })
            print(f"Selesai {jenis_label}: {len(records)} rekod.")
        except Exception as e:
            print(f"Ralat pada {jenis_label}: {e}")

    unique = {}
    for r in records:
        if r["kod"] not in unique or (r["gambar"] and not unique[r["kod"]]["gambar"]):
            unique[r["kod"]] = r
    return list(unique.values())

def load_existing():
    with open("data_terkini.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("records", data.get("data", []))

def build_vectors(records):
    groups = {}
    for r in records:
        vals = r if isinstance(r, list) else list(r.values())
        obj = {} if isinstance(r, list) else r
        kat = str(obj.get("kategori") or (vals[2] if len(vals) > 2 else "")).strip()
        sub = str(obj.get("sub_kategori") or (vals[3] if len(vals) > 3 else "")).strip()
        nama = str(obj.get("nama") or (vals[4] if len(vals) > 4 else (vals[1] if len(vals) > 1 else ""))).strip()
        key = f"{kat} > {sub}".strip(" >") or nama
        if key and key not in groups:
            groups[key] = f"{sub} | {kat} | {nama}"

    items = list(groups.items())[:3500]
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    embs = model.encode([v for _, v in items], batch_size=128, normalize_embeddings=True, show_progress_bar=False)
    return [{"k": k, "v": [round(float(x), 4) for x in embs[i]]} for i, (k, _) in enumerate(items)]

def main():
    scraped = scrape_mof_with_session()
    if len(scraped) > 1000:
        myt = timezone(timedelta(hours=8))
        now_str = datetime.now(myt).strftime("%d %b %Y, %I:%M %p")
        with open("data_terkini.json", "w", encoding="utf-8") as f:
            json.dump({"updated_at": now_str, "records": scraped}, f, ensure_ascii=False, separators=(",", ":"))
        records = scraped
    else:
        records = load_existing()

    if records:
        vectors = build_vectors(records)
        with open("vectors.json", "w", encoding="utf-8") as f:
            json.dump({"items": vectors}, f, ensure_ascii=False, separators=(",", ":"))

if __name__ == "__main__":
    main()
