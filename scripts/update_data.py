import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from sentence_transformers import SentenceTransformer

BASE_API = "https://knowledgebase.treasury.gov.my/kb/api"

def fetch_json(url, payload=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json"
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))

def try_fetch_mof_records():
    endpoints = [
        ("https://knowledgebase.treasury.gov.my/kb/api/asset/search", {"keyword": "", "limit": 200000}),
        ("https://knowledgebase.treasury.gov.my/kb/api/reference/all", None),
    ]
    for url, payload in endpoints:
        try:
            res = fetch_json(url, payload)
            items = res if isinstance(res, list) else res.get("data", res.get("records", []))
            if items and len(items) > 1000:
                return items
        except Exception:
            continue
    return None

def load_existing_records():
    with open("data_terkini.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("records", data.get("data", []))

def build_semantic_vectors(records):
    unique_groups = {}
    for r in records:
        vals = r if isinstance(r, list) else list(r.values())
        obj = {} if isinstance(r, list) else r
        kat = str(obj.get("kategori") or (vals[2] if len(vals) > 2 else "")).strip()
        sub = str(obj.get("sub_kategori") or (vals[4] if len(vals) > 4 else "")).strip()
        nama = str(obj.get("nama") or (vals[5] if len(vals) > 5 else (vals[1] if len(vals) > 1 else ""))).strip()
        key = f"{kat} > {sub}".strip(" >")
        if key and key not in unique_groups:
            unique_groups[key] = f"{sub} | {kat} | {nama}"

    items = list(unique_groups.items())[:3500]
    texts = [v for _, v in items]
    print(f"Menjana vektor mini AI untuk {len(texts)} kumpulan pengelasan...")

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    embeddings = model.encode(texts, batch_size=128, normalize_embeddings=True, show_progress_bar=False)

    return [
        {"k": kat, "v": [round(float(x), 4) for x in embeddings[idx]]}
        for idx, (kat, _) in enumerate(items)
    ]

def main():
    fetched = try_fetch_mof_records()
    if fetched:
        myt = timezone(timedelta(hours=8))
        now_str = datetime.now(myt).strftime("%d %b %Y, %I:%M %p")
        with open("data_terkini.json", "w", encoding="utf-8") as f:
            json.dump({"updated_at": now_str, "records": fetched}, f, ensure_ascii=False, separators=(",", ":"))
        records = fetched
        print(f"Berjaya menarik {len(records)} rekod baharu daripada MOF.")
    else:
        records = load_existing_records()
        print(f"Menggunakan {len(records)} rekod sedia ada dalam data_terkini.json.")

    if records:
        vectors = build_semantic_vectors(records)
        with open("vectors.json", "w", encoding="utf-8") as f:
            json.dump({"items": vectors}, f, ensure_ascii=False, separators=(",", ":"))
        print(f"Selesai! {len(vectors)} vektor mini dijana.")

if __name__ == "__main__":
    main()
