import json
import urllib3
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import numpy as np
from sentence_transformers import SentenceTransformer

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URLS = [
    ("Aset", "https://www.treasury.gov.my/pekeliling/1pp/am/dump_asset.cfm"),
    ("Stok", "https://www.treasury.gov.my/pekeliling/1pp/am/dump_stock.cfm"),
]

def fetch_mof_records():
    records = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for jenis_utama, url in URLS:
        print(f"Memuat turun data daripada {url}...")
        resp = requests.get(url, headers=headers, timeout=120, verify=False)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.find_all("tr")
        for tr in rows[1:]:
            cols = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cols) >= 4 and cols[0]:
                kod = cols[0].strip()
                nama = cols[1].strip()
                kategori = cols[2].strip() if len(cols) > 2 else ""
                keterangan = cols[3].strip() if len(cols) > 3 else ""
                
                jenis = jenis_utama
                if jenis_utama == "Aset":
                    if kod.startswith("02") or "TAK ALIH" in kategori.upper():
                        jenis = "Aset Tak Alih"
                    elif kod.startswith("03") or "TAK KETARA" in kategori.upper():
                        jenis = "Aset Tak Ketara"
                    else:
                        jenis = "Aset Alih"

                records.append({
                    "kod": kod,
                    "nama": nama,
                    "kategori": kategori,
                    "keterangan": keterangan,
                    "jenis": jenis
                })
    return records

def build_semantic_vectors(records):
    print("Mengumpul kumpulan kategori unik untuk indeks semantik...")
    unique_groups = {}
    for r in records:
        kat_parts = [p.strip() for p in r["kategori"].split(">") if p.strip()]
        sub_kat = kat_parts[-1] if kat_parts else r["nama"]
        group_key = f"{r['kategori']}||{sub_kat}"
        if group_key not in unique_groups:
            unique_groups[group_key] = {
                "kategori": r["kategori"],
                "label": f"{sub_kat} ({r['nama']})"
            }

    group_list = list(unique_groups.values())
    texts = [g["label"] for g in group_list]
    print(f"Menjana vektor AI untuk {len(texts)} kumpulan pengelasan...")

    model = SentenceTransformer("Xenova/paraphrase-multilingual-MiniLM-L12-v2")
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    compressed_items = []
    for idx, g in enumerate(group_list):
        vec = [round(float(x), 4) for x in embeddings[idx]]
        compressed_items.append({
            "k": g["kategori"],
            "v": vec
        })

    return compressed_items

def main():
    myt = timezone(timedelta(hours=8))
    now_str = datetime.now(myt).strftime("%d %b %Y, %I:%M %p")

    records = fetch_mof_records()
    print(f"Jumlah rekod berjaya ditarik: {len(records)}")

    if len(records) > 1000:
        data_output = {
            "updated_at": now_str,
            "total": len(records),
            "records": records
        }
        with open("data_terkini.json", "w", encoding="utf-8") as f:
            json.dump(data_output, f, ensure_ascii=False, separators=(",", ":"))

        vectors = build_semantic_vectors(records)
        with open("vectors.json", "w", encoding="utf-8") as f:
            json.dump({"items": vectors}, f, ensure_ascii=False, separators=(",", ":"))
        print("Selesai menjana data_terkini.json dan vectors.json!")

if __name__ == "__main__":
    main()
