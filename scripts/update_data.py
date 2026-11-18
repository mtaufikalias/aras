import urllib.request
import ssl
import re
import json
from datetime import datetime

ASSET_URL = "https://knowledgebase.treasury.gov.my/kb/dump_asset.cfm"
STOCK_URL = "https://knowledgebase.treasury.gov.my/kb/dump_stock.cfm"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://knowledgebase.treasury.gov.my/kb/'
}

# Bypass pengesahan SSL jika pelayan kerajaan menggunakan sijil rantaian lama
SSL_CONTEXT = ssl._create_unverified_context()

def fetch_dump(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
        content_disp = resp.headers.get('Content-Disposition', '')
        fname_match = re.search(r'filename="?([^";]+)"?', content_disp, re.IGNORECASE)
        fname = fname_match.group(1) if fname_match else url.split('/')[-1]
        raw_bytes = resp.read()
        print(f"Berjaya muat turun {fname} ({len(raw_bytes) / (1024*1024):.2f} MB)")
        return raw_bytes.decode('latin1', errors='ignore'), fname

def parse_sql_tuples(sql_text, table_name):
    rows = []
    pattern = re.compile(rf"INSERT INTO `{table_name}` VALUES\s*", re.IGNORECASE)
    for match in pattern.finditer(sql_text):
        i = match.end()
        n = len(sql_text)
        while i < n:
            while i < n and sql_text[i] in ' \r\n\t,':
                i += 1
            if i >= n or sql_text[i] == ';':
                break
            if sql_text[i] != '(':
                i += 1
                continue
            i += 1
            fields = []
            cur = []
            in_str = False
            while i < n:
                ch = sql_text[i]
                if in_str:
                    if ch == '\\' and i + 1 < n:
                        nxt = sql_text[i + 1]
                        cur.append('\n' if nxt == 'n' else '\r' if nxt == 'r' else nxt)
                        i += 2
                        continue
                    elif ch == "'" and i + 1 < n and sql_text[i + 1] == "'":
                        cur.append("'")
                        i += 2
                        continue
                    elif ch == "'":
                        in_str = False
                    else:
                        cur.append(ch)
                else:
                    if ch == "'":
                        in_str = True
                    elif ch == ',':
                        val = ''.join(cur).strip()
                        fields.append(None if val.upper() == 'NULL' else val)
                        cur = []
                    elif ch == ')':
                        val = ''.join(cur).strip()
                        fields.append(None if val.upper() == 'NULL' else val)
                        rows.append(fields)
                        i += 1
                        break
                    else:
                        cur.append(ch)
                i += 1
    return rows

def clean_html(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', text)).strip()

def main():
    records = []
    aset_fname = ""
    stok_fname = ""

    # 1. Tarik data Aset dari dump_asset.cfm
    try:
        sql_aset, aset_fname = fetch_dump(ASSET_URL)
        c3 = {r[1]: r[2] for r in parse_sql_tuples(sql_aset, "code_003") if len(r) > 2}
        c4 = {r[1]: r[2] for r in parse_sql_tuples(sql_aset, "code_004") if len(r) > 2}
        for r in parse_sql_tuples(sql_aset, "code_005"):
            if len(r) < 4 or not r[1] or not r[2]:
                continue
            code, desc, ctype = r[1].strip(), r[2].strip(), (r[3] or "").strip()
            detail = clean_html(r[10]) if len(r) > 10 else ""
            img_time = r[11] if len(r) > 11 else None
            upper = desc.upper()
            cat = "ASET_TAK_ALIH" if "ASET TAK ALIH" in upper else \
                  "ASET_TAK_KETARA" if "ASET TAK KETARA" in upper else \
                  "STOK" if "(STOK)" in upper else "ASET_ALIH"
            records.append({
                "id": r[0], "code": code, "desc": desc, "cat": cat,
                "c1": c3.get(ctype[:3], ""), "c2": c4.get(ctype, ""),
                "detail": detail[:300], "img": img_time
            })
        print(f"Jumlah rekod Aset diekstrak: {len(records)}")
    except Exception as e:
        print(f"Ralat semasa menarik Aset: {e}")

    # 2. Tarik data Stok dari dump_stock.cfm
    try:
        sql_stok, stok_fname = fetch_dump(STOCK_URL)
        s1 = {r[1]: r[2] for r in parse_sql_tuples(sql_stok, "sps_stok_class1") if len(r) > 2}
        s2 = {f"{r[3]}-{r[1]}": r[2] for r in parse_sql_tuples(sql_stok, "sps_stok_class2") if len(r) > 3}
        s3 = {f"{r[3]}-{r[4]}-{r[1]}": r[2] for r in parse_sql_tuples(sql_stok, "sps_stok_class3") if len(r) > 4}
        count_stok = 0
        for r in parse_sql_tuples(sql_stok, "sps_stok_class4"):
            if len(r) < 7 or not r[2]:
                continue
            fullcode = (r[6] or f"{r[3]}{r[4]}{r[5]}{r[1]}").strip()
            desc = r[2].strip()
            detail = clean_html(r[21]) if len(r) > 21 else ""
            records.append({
                "id": r[0], "code": fullcode, "desc": desc, "cat": "STOK",
                "c1": s1.get(r[3], ""), "c2": s2.get(f"{r[3]}-{r[4]}", ""),
                "c3": s3.get(f"{r[3]}-{r[4]}-{r[5]}", ""),
                "detail": "" if detail == "Sedang Dikemaskini" else detail[:300],
                "img": r[10] if len(r) > 10 else None
            })
            count_stok += 1
        print(f"Jumlah rekod Stok diekstrak: {count_stok}")
    except Exception as e:
        print(f"Ralat semasa menarik Stok: {e}")

    if not records:
        raise RuntimeError("Tiada rekod berjaya diekstrak daripada kedua-dua pautan MOF.")

    output = {
        "updated_at": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        "aset_source": aset_fname,
        "stok_source": stok_fname,
        "total": len(records),
        "records": records
    }
    with open("data_terkini.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(',', ':'))
    print(f"SELESAI: {len(records)} jumlah rekod disimpan ke data_terkini.json")

if __name__ == "__main__":
    main()
