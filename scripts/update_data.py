import urllib.request
import re
import json
import gzip
from datetime import datetime, timedelta

BASE_URL = "https://knowledgebase.treasury.gov.my/kb/"
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def fetch_url(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode('latin1', errors='ignore')

def find_latest_file(prefix):
    # Cuba cari pautan terus dari halaman utama KB Treasury
    try:
        html = fetch_url(BASE_URL)
        matches = re.findall(rf'href=["\']([^"\']*{prefix}_[^"\']+\.txt)["\']', html, re.IGNORECASE)
        if matches:
            link = matches[0]
            return link if link.startswith('http') else BASE_URL + link.lstrip('/')
    except Exception:
        pass
    
    # Jika tiada di HTML, cuba teka tarikh hari ini hingga 7 hari lepas (format: 18.Nov.2026)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for i in range(8):
        d = datetime.now() - timedelta(days=i)
        fname = f"{prefix}_{d.day:02d}.{months[d.month-1]}.{d.year}.txt"
        test_url = BASE_URL + fname
        try:
            req = urllib.request.Request(test_url, headers=HEADERS, method='HEAD')
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    return test_url
        except Exception:
            continue
    return None

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
    aset_url = find_latest_file("prm_kodaset")
    stok_url = find_latest_file("prm_kodstok")
    records = []

    if aset_url:
        print("Muat turun Aset:", aset_url)
        sql_aset = fetch_url(aset_url)
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

    if stok_url:
        print("Muat turun Stok:", stok_url)
        sql_stok = fetch_url(stok_url)
        s1 = {r[1]: r[2] for r in parse_sql_tuples(sql_stok, "sps_stok_class1") if len(r) > 2}
        s2 = {f"{r[3]}-{r[1]}": r[2] for r in parse_sql_tuples(sql_stok, "sps_stok_class2") if len(r) > 3}
        s3 = {f"{r[3]}-{r[4]}-{r[1]}": r[2] for r in parse_sql_tuples(sql_stok, "sps_stok_class3") if len(r) > 4}
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

    if records:
        output = {
            "updated_at": datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "aset_source": aset_url,
            "stok_source": stok_url,
            "total": len(records),
            "records": records
        }
        with open("data_terkini.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, separators=(',', ':'))
        print(f"Berjaya simpan {len(records)} rekod ke data_terkini.json")

if __name__ == "__main__":
    main()
