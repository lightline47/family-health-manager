import os, sqlite3
from pathlib import Path
import pandas as pd
from supabase import create_client

DB_PATH = Path(os.environ.get("LOCAL_DB_PATH", "data/blood_manager.db"))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
FAMILY_ID = os.environ.get("FAMILY_ID", "our-family")

if not DB_PATH.exists():
    raise SystemExit(f"SQLite DB를 찾을 수 없습니다: {DB_PATH}")
if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise SystemExit("SUPABASE_URL / SUPABASE_SECRET_KEY 환경변수를 설정해 주세요.")

sb = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
conn = sqlite3.connect(DB_PATH)

def rows(table):
    return pd.read_sql_query(f"select * from {table}", conn).to_dict("records")

def clean(row):
    out = {}
    for k,v in row.items():
        if k == "id":
            continue
        if pd.isna(v): v = None
        if hasattr(v, "isoformat"): v = v.isoformat()
        out[k] = v
    out["family_id"] = FAMILY_ID
    return out

for table in ["health_settings","health_lab_records","health_events","family_health_logs"]:
    data = [clean(r) for r in rows(table)]
    print(table, len(data))
    for i in range(0, len(data), 200):
        batch = data[i:i+200]
        if not batch: continue
        if table == "health_settings":
            for r in batch:
                ex = sb.table(table).select("id").eq("family_id",FAMILY_ID).eq("key",r["key"]).limit(1).execute().data or []
                if ex: sb.table(table).update({"value":r.get("value")}).eq("id",ex[0]["id"]).execute()
                else: sb.table(table).insert(r).execute()
        elif table == "health_lab_records":
            for r in batch:
                ex = sb.table(table).select("id").eq("family_id",FAMILY_ID).eq("exam_date",r["exam_date"]).limit(1).execute().data or []
                if ex: sb.table(table).update({k:v for k,v in r.items() if k not in ("family_id","exam_date")}).eq("id",ex[0]["id"]).execute()
                else: sb.table(table).insert(r).execute()
        else:
            sb.table(table).insert(batch).execute()
print("마이그레이션 완료")
