import json
from sentence_transformers import SentenceTransformer

def load_existing_records():
    with open("data_terkini.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    raw_list = data if isinstance(data, list) else data.get("records", data.get("data", []))
    parsed = []
    for r in raw_list:
        if isinstance(r, list) and len(r) >= 4:
            kat = str(r[1]).strip()
            sub = str(r[2]).strip()
            nama = str(r[3]).strip()
            parsed.append({"kategori": f"{kat} > {sub}", "nama": nama})
        elif isinstance(r, dict):
            vals = list(r.values())
            kat = str(r.get("kategori") or r.get("category") or (vals[1] if len(vals) > 1 else "")).strip()
            sub = str(r.get("sub_kategori") or r.get("subkategori") or (vals[2] if len(vals) > 2 else "")).strip()
            nama = str(r.get("nama") or r.get("name") or (vals[3] if len(vals) > 3 else "")).strip()
            parsed.append({"kategori": f"{kat} > {sub}".strip(" >"), "nama": nama})
    return parsed

def build_semantic_vectors(records):
    print("Mengumpul kumpulan kategori unik daripada rekod...")
    unique_groups = {}
    for r in records:
        kat = r["kategori"]
        nama = r["nama"]
        if kat and kat not in unique_groups:
            unique_groups[kat] = f"{kat} ({nama})"

    items = list(unique_groups.items())
    texts = [v for _, v in items]
    print(f"Menjana vektor AI untuk {len(texts)} kumpulan pengelasan...")

    model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    compressed_items = []
    for idx, (kat, _) in enumerate(items):
        vec = [round(float(x), 4) for x in embeddings[idx]]
        compressed_items.append({
            "k": kat,
            "v": vec
        })
    return compressed_items

def main():
    records = load_existing_records()
    print(f"Jumlah rekod dibaca untuk indeks vektor: {len(records)}")
    if records:
        vectors = build_semantic_vectors(records)
        with open("vectors.json", "w", encoding="utf-8") as f:
            json.dump({"items": vectors}, f, ensure_ascii=False, separators=(",", ":"))
        print(f"Berjaya menjana vectors.json dengan {len(vectors)} vektor!")

if __name__ == "__main__":
    main()
