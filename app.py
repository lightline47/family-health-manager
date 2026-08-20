
import io
import re
import json
import hashlib
import zipfile
from datetime import date, datetime

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text as sqltext
from sqlalchemy.engine import URL

st.set_page_config(
    page_title="내 혈액관리",
    page_icon="🩸",
    layout="wide",
    initial_sidebar_state="auto",
)

# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.markdown("""
<style>
.main .block-container {padding-top: 1.1rem; max-width: 1450px;}
.hero {
    background: linear-gradient(135deg,#8b1e2d,#b02a37);
    color:white; padding:22px 26px; border-radius:18px; margin-bottom:16px;
}
.hero h1 {font-size:2rem; margin:0 0 6px 0;}
.hero p {margin:0; opacity:.92;}
.kpi-grid {display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:10px 0 20px 0;}
.kpi {background:white;border:1px solid #e6eaf0;border-radius:15px;padding:16px 18px;box-shadow:0 4px 14px rgba(30,41,59,.05);}
.kpi .label {font-size:.82rem;color:#64748b;font-weight:700;}
.kpi .value {font-size:1.35rem;font-weight:800;margin-top:8px;}
.small-note {color:#64748b;font-size:.82rem;}
@media(max-width:768px){
  .main .block-container {padding: .65rem .65rem 2rem .65rem;}
  .hero {padding:17px 16px;border-radius:14px;}
  .hero h1 {font-size:1.35rem;}
  .kpi-grid {grid-template-columns:1fr 1fr;gap:8px;}
  .kpi {padding:12px;}
  .kpi .value {font-size:1.05rem;}
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Supabase
# ---------------------------------------------------------
def database_config():
    try:
        cfg = st.secrets["database"]
        return {
            "host": str(cfg["host"]).strip(),
            "port": int(cfg.get("port", 6543)),
            "database": str(cfg.get("database", "postgres")).strip(),
            "user": str(cfg["user"]).strip(),
            "password": str(cfg["password"]),
        }
    except Exception as exc:
        raise RuntimeError(
            "Streamlit Secrets의 [database]에 host / port / database / user / password를 설정해 주세요."
        ) from exc

@st.cache_resource(show_spinner=False)
def engine():
    cfg = database_config()
    url = URL.create(
        "postgresql+psycopg2",
        username=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        port=cfg["port"],
        database=cfg["database"],
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=600,
        pool_size=3,
        max_overflow=2,
        connect_args={"sslmode":"require","connect_timeout":8,"application_name":"blood_manager_v1"},
    )

@st.cache_resource(show_spinner=False)
def ensure_schema():
    ddl = [
        """CREATE TABLE IF NOT EXISTS health_settings(
            key TEXT PRIMARY KEY,
            value TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS health_lab_records(
            id BIGSERIAL PRIMARY KEY,
            exam_date DATE NOT NULL UNIQUE,
            total_chol DOUBLE PRECISION,
            ldl DOUBLE PRECISION,
            hdl DOUBLE PRECISION,
            triglyceride DOUBLE PRECISION,
            fasting_glucose DOUBLE PRECISION,
            hba1c DOUBLE PRECISION,
            cpk DOUBLE PRECISION,
            bilirubin DOUBLE PRECISION,
            ast_got DOUBLE PRECISION,
            alt_gpt DOUBLE PRECISION,
            wbc DOUBLE PRECISION,
            mpv DOUBLE PRECISION,
            vitamin_d DOUBLE PRECISION,
            height_cm DOUBLE PRECISION,
            weight_kg DOUBLE PRECISION,
            systolic INTEGER,
            diastolic INTEGER,
            note TEXT DEFAULT '',
            source TEXT DEFAULT 'manual',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS health_events(
            id BIGSERIAL PRIMARY KEY,
            event_date DATE NOT NULL,
            category TEXT DEFAULT '기타',
            event_text TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
    ]
    with engine().begin() as conn:
        for q in ddl:
            conn.execute(sqltext(q))
    return True

def clear_cache():
    st.cache_data.clear()

def setting_get(key, default=None):
    with engine().connect() as conn:
        row = conn.execute(
            sqltext("SELECT value FROM health_settings WHERE key=:key"),
            {"key":key}
        ).fetchone()
    return row[0] if row else default

def setting_set(key, value):
    with engine().begin() as conn:
        conn.execute(sqltext(
            "INSERT INTO health_settings(key,value) VALUES(:key,:value) "
            "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value"
        ), {"key":key,"value":str(value)})
    clear_cache()

@st.cache_data(ttl=30, show_spinner=False)
def load_records():
    with engine().connect() as conn:
        df = pd.read_sql_query(
            sqltext("SELECT * FROM health_lab_records ORDER BY exam_date"),
            conn
        )
    if not df.empty:
        df["exam_date"] = pd.to_datetime(df["exam_date"])
    return df

@st.cache_data(ttl=30, show_spinner=False)
def load_events():
    with engine().connect() as conn:
        df = pd.read_sql_query(
            sqltext("SELECT * FROM health_events ORDER BY event_date,id"),
            conn
        )
    if not df.empty:
        df["event_date"] = pd.to_datetime(df["event_date"])
    return df

def upsert_record(rec):
    cols = [
        "exam_date","total_chol","ldl","hdl","triglyceride","fasting_glucose","hba1c",
        "cpk","bilirubin","ast_got","alt_gpt","wbc","mpv","vitamin_d",
        "height_cm","weight_kg","systolic","diastolic","note","source"
    ]
    params = {c: rec.get(c) for c in cols}
    with engine().begin() as conn:
        conn.execute(sqltext("""
            INSERT INTO health_lab_records(
                exam_date,total_chol,ldl,hdl,triglyceride,fasting_glucose,hba1c,
                cpk,bilirubin,ast_got,alt_gpt,wbc,mpv,vitamin_d,
                height_cm,weight_kg,systolic,diastolic,note,source
            ) VALUES(
                :exam_date,:total_chol,:ldl,:hdl,:triglyceride,:fasting_glucose,:hba1c,
                :cpk,:bilirubin,:ast_got,:alt_gpt,:wbc,:mpv,:vitamin_d,
                :height_cm,:weight_kg,:systolic,:diastolic,:note,:source
            )
            ON CONFLICT(exam_date) DO UPDATE SET
                total_chol=EXCLUDED.total_chol, ldl=EXCLUDED.ldl, hdl=EXCLUDED.hdl,
                triglyceride=EXCLUDED.triglyceride, fasting_glucose=EXCLUDED.fasting_glucose,
                hba1c=EXCLUDED.hba1c, cpk=EXCLUDED.cpk, bilirubin=EXCLUDED.bilirubin,
                ast_got=EXCLUDED.ast_got, alt_gpt=EXCLUDED.alt_gpt, wbc=EXCLUDED.wbc,
                mpv=EXCLUDED.mpv, vitamin_d=EXCLUDED.vitamin_d, height_cm=EXCLUDED.height_cm,
                weight_kg=EXCLUDED.weight_kg, systolic=EXCLUDED.systolic,
                diastolic=EXCLUDED.diastolic, note=EXCLUDED.note, source=EXCLUDED.source
        """), params)
    clear_cache()

def save_event(event_date, category, event_text):
    with engine().begin() as conn:
        conn.execute(sqltext(
            "INSERT INTO health_events(event_date,category,event_text) VALUES(:d,:c,:t)"
        ), {"d":event_date,"c":category,"t":event_text})
    clear_cache()

def delete_record(record_id):
    with engine().begin() as conn:
        conn.execute(
            sqltext("DELETE FROM health_lab_records WHERE id=:id"),
            {"id": int(record_id)}
        )
    clear_cache()

def delete_event(event_id):
    with engine().begin() as conn:
        conn.execute(
            sqltext("DELETE FROM health_events WHERE id=:id"),
            {"id": int(event_id)}
        )
    clear_cache()

def update_note(record_id, note):
    with engine().begin() as conn:
        conn.execute(
            sqltext("UPDATE health_lab_records SET note=:note WHERE id=:id"),
            {"note": note, "id": int(record_id)}
        )
    clear_cache()

# ---------------------------------------------------------
# Login
# ---------------------------------------------------------
def pin_hash(pin):
    return hashlib.sha256(("blood-manager-v1::" + pin).encode("utf-8")).hexdigest()

def auth_gate():
    stored = setting_get("pin_hash", "")
    if not stored:
        st.markdown('<div class="hero"><h1>🔐 내 혈액관리 로그인 설정</h1><p>최초 1회 앱 PIN을 설정합니다.</p></div>', unsafe_allow_html=True)
        a = st.text_input("새 비밀번호", type="password")
        b = st.text_input("새 비밀번호 확인", type="password")
        if st.button("비밀번호 설정", type="primary", width="stretch"):
            a_clean = str(a).strip()
            b_clean = str(b).strip()
            # 브라우저/Streamlit 환경에 따른 길이 판정 문제를 피하기 위해
            # 빈 값 여부와 두 입력의 일치 여부만 확인합니다.
            if not a_clean or not b_clean:
                st.error("비밀번호를 입력해 주세요.")
            elif a_clean != b_clean:
                st.error("두 비밀번호가 일치하지 않습니다.")
            else:
                setting_set("pin_hash", pin_hash(a_clean))
                st.session_state["auth"] = True
                st.rerun()
        st.stop()

    if not st.session_state.get("auth"):
        st.markdown('<div class="hero"><h1>🔐 내 혈액관리 로그인</h1><p>비밀번호 인증 후 기록에 접근할 수 있습니다.</p></div>', unsafe_allow_html=True)
        pin = st.text_input("비밀번호", type="password")
        if st.button("로그인", type="primary", width="stretch"):
            pin_clean = str(pin).strip()
            if pin_hash(pin_clean) == stored:
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("비밀번호가 일치하지 않습니다.")
        st.stop()

def logout():
    if st.button("🔒 로그아웃", width="stretch"):
        st.session_state["auth"] = False
        st.rerun()

# ---------------------------------------------------------
# Excel parser
# ---------------------------------------------------------
def num(v):
    if v is None or (isinstance(v,float) and pd.isna(v)):
        return None
    if isinstance(v,(int,float)):
        return float(v)
    s = str(v).strip().replace(",","")
    try:
        return float(s)
    except:
        return None

def parse_date(v, year_hint=None):
    if v is None:
        return None
    s = str(v).strip()
    if s in ("","-","nan"):
        return None
    s = s.replace("년",".").replace("월",".").replace("일","").strip(". ")
    parts = [p for p in re.split(r"[./-]", s) if p]
    try:
        if len(parts) == 3:
            y,m,d = map(int,parts)
            if y < 100: y += 2000
            return date(y,m,d)
        if len(parts) == 2 and year_hint:
            m,d = map(int,parts)
            return date(int(year_hint),m,d)
    except:
        return None
    return None

def parse_bp(v):
    if not v:
        return None,None
    m = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", str(v))
    return (int(m.group(1)),int(m.group(2))) if m else (None,None)

def parse_excel(file):
    raw = pd.read_excel(file, sheet_name=0, header=None, engine="openpyxl")
    records, events = [], []
    year_hint = None

    for i in range(6, len(raw)):
        row = raw.iloc[i].tolist()
        if len(row) < 18:
            continue

        if pd.notna(row[0]):
            try:
                year_hint = int(float(row[0]))
            except:
                pass

        d = parse_date(row[1], year_hint)
        cval = row[2]

        # Medication/event rows stored in total cholesterol column
        if isinstance(cval, str) and num(cval) is None:
            if d:
                cat = "약물" if any(k in cval for k in ["복용","단약","리피","크로스","스타틴"]) else "기타"
                events.append({"event_date":d,"category":cat,"event_text":cval.strip()})
            continue

        if not d:
            continue

        systolic, diastolic = parse_bp(row[17])
        rec = {
            "exam_date": d,
            "total_chol": num(row[2]),
            "ldl": num(row[3]),
            "hdl": num(row[4]),
            "triglyceride": num(row[5]),
            "fasting_glucose": num(row[6]),
            "hba1c": num(row[7]),
            "cpk": num(row[8]),
            "bilirubin": num(row[9]),
            "ast_got": num(row[10]),
            "alt_gpt": num(row[11]),
            "wbc": num(row[12]),
            "mpv": num(row[13]),
            "vitamin_d": num(row[14]),
            "height_cm": num(row[15]),
            "weight_kg": num(row[16]),
            "systolic": systolic,
            "diastolic": diastolic,
            "note": "",
            "source": "excel_initial",
        }
        # Preserve qualitative values in note
        notes = []
        if isinstance(row[4],str) and num(row[4]) is None: notes.append(f"HDL: {row[4]}")
        if isinstance(row[5],str) and num(row[5]) is None: notes.append(f"중성지방: {row[5]}")
        rec["note"] = " / ".join(notes)
        records.append(rec)

    return records, events

# ---------------------------------------------------------
# Charts/helpers
# ---------------------------------------------------------
LABELS = {
    "total_chol":"총콜레스테롤","ldl":"LDL","hdl":"HDL","triglyceride":"중성지방",
    "fasting_glucose":"공복혈당","hba1c":"당화혈색소","cpk":"CPK","bilirubin":"빌리루빈",
    "ast_got":"GOT(AST)","alt_gpt":"GPT(ALT)","wbc":"WBC","mpv":"MPV","vitamin_d":"비타민D",
    "height_cm":"신장","weight_kg":"몸무게","systolic":"수축기혈압","diastolic":"이완기혈압",
}

def fmt(v, digits=1, suffix=""):
    if v is None or pd.isna(v):
        return "-"
    if digits == 0:
        return f"{v:,.0f}{suffix}"
    return f"{v:,.1f}{suffix}"

REFERENCE = {
    "total_chol": {"label":"총콜레스테롤","good":"≤ 200","normal":"≤ 230"},
    "ldl": {"label":"LDL","good":"≤ 100","normal":"≤ 130"},
    "hdl": {"label":"HDL","good":"≥ 60","normal":"40~50"},
    "triglyceride": {"label":"중성지방","good":"≤ 150","normal":"≤ 200"},
    "fasting_glucose": {"label":"공복혈당","good":"< 100","normal":"-"},
    "hba1c": {"label":"당화혈색소","good":"≤ 5.6","normal":"-"},
    "bilirubin": {"label":"빌리루빈","good":"0.2~1.2","normal":"-"},
    "ast_got": {"label":"GOT(AST)","good":"0~40","normal":"-"},
    "alt_gpt": {"label":"GPT(ALT)","good":"0~41","normal":"-"},
    "wbc": {"label":"WBC","good":"4.8~10.8","normal":"-"},
    "mpv": {"label":"MPV","good":"7.2~10.8","normal":"-"},
    "vitamin_d": {"label":"비타민D","good":"30~100","normal":"-"},
}

def latest_two_nonnull(df, col):
    s = df[["exam_date", col]].dropna()
    if s.empty:
        return None, None, None
    latest = s.iloc[-1][col]
    prev = s.iloc[-2][col] if len(s) >= 2 else None
    d = s.iloc[-1]["exam_date"]
    return d, latest, prev

def delta_text(latest, prev, digits=1, suffix=""):
    if latest is None or prev is None or pd.isna(latest) or pd.isna(prev):
        return "이전 기록 없음"
    diff = float(latest) - float(prev)
    sign = "+" if diff > 0 else ""
    if digits == 0:
        return f"직전 대비 {sign}{diff:,.0f}{suffix}"
    return f"직전 대비 {sign}{diff:,.1f}{suffix}"

def kpi_html(label, value, sub):
    return (
        '<div class="kpi">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="small-note">{sub}</div>'
        '</div>'
    )

def trend_chart(df, cols, title):
    if df.empty:
        st.info("기록이 없습니다.")
        return
    use = df[["exam_date"] + [c for c in cols if c in df.columns]].copy()
    long = use.melt("exam_date", var_name="항목", value_name="값").dropna()
    if long.empty:
        st.info("해당 항목 기록이 없습니다.")
        return
    long["항목"] = long["항목"].map(LABELS)
    chart = alt.Chart(long).mark_line(point=True).encode(
        x=alt.X("exam_date:T", title="검사일"),
        y=alt.Y("값:Q", title="검사값"),
        color=alt.Color("항목:N", title="항목"),
        tooltip=["exam_date:T","항목:N","값:Q"],
    ).properties(height=300, title=title).interactive()
    st.altair_chart(chart, width="stretch")

# ---------------------------------------------------------
# Startup
# ---------------------------------------------------------
try:
    ensure_schema()
except Exception as exc:
    st.error("Supabase 연결에 실패했습니다.")
    st.exception(exc)
    st.stop()

auth_gate()

NAV = ["대시보드","새 검사 기록","검사 추이","신장·몸무게·혈압","약물·이벤트","기록 관리","설정/백업"]
if "page" not in st.session_state:
    st.session_state["page"] = "대시보드"

with st.sidebar:
    st.markdown("## 🩸 내 혈액관리")
    st.caption("V1.1 Cloud")
    page = st.radio("메뉴", NAV, index=NAV.index(st.session_state["page"]), label_visibility="collapsed")
    st.session_state["page"] = page
    st.divider()
    st.success("☁️ Supabase 클라우드 관리")
    st.caption("의료진의 진단을 대신하지 않는 개인 기록용 앱입니다.")
    st.divider()
    logout()

# Mobile menu
page = st.selectbox(
    "📱 메뉴 이동",
    NAV,
    index=NAV.index(st.session_state["page"]),
    key="mobile_page"
)
st.session_state["page"] = page

records = load_records()
events = load_events()

# ---------------------------------------------------------
# Initial import
# ---------------------------------------------------------
if setting_get("initialized","0") != "1":
    st.markdown('<div class="hero"><h1>🩸 내 혈액관리 V1.1 Cloud</h1><p>기존 혈액검사 Excel을 최초 1회 가져옵니다.</p></div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("혈액검사 Excel(.xlsx)", type=["xlsx"])
    if uploaded:
        try:
            recs, evs = parse_excel(uploaded)
            st.success(f"검사 기록 {len(recs)}건, 약물·이벤트 {len(evs)}건을 읽었습니다.")
            if recs:
                preview = pd.DataFrame(recs)[["exam_date","total_chol","ldl","hdl","fasting_glucose","weight_kg"]]
                preview.columns = ["검사일","총콜","LDL","HDL","공복혈당","몸무게"]
                st.dataframe(preview, width="stretch", hide_index=True)
            confirm = st.checkbox("이 파일을 최초 데이터로 등록합니다.")
            if st.button("최초 데이터 등록", type="primary", width="stretch", disabled=not confirm):
                with st.status("Supabase에 데이터를 등록하고 있습니다...", expanded=True) as status:
                    for r in recs:
                        upsert_record(r)
                    for e in evs:
                        save_event(e["event_date"], e["category"], e["event_text"])
                    setting_set("initialized","1")
                    setting_set("initial_file", uploaded.name)
                    status.update(label="✅ 최초 등록 완료", state="complete")
                    st.success("이제 Excel 없이 계속 기록할 수 있습니다.")
                    st.rerun()
        except Exception as exc:
            st.exception(exc)
    st.stop()

# ---------------------------------------------------------
# Pages
# ---------------------------------------------------------
if page == "대시보드":
    st.markdown('<div class="hero"><h1>내 혈액검사 한눈에 보기</h1><p>최근 검사와 직전 검사 변화를 함께 보고 장기 추이를 기록합니다.</p></div>', unsafe_allow_html=True)

    if records.empty:
        st.info("등록된 검사 기록이 없습니다.")
    else:
        metrics = [
            ("total_chol","총콜레스테롤",0,""),
            ("ldl","LDL",0,""),
            ("hdl","HDL",0,""),
            ("triglyceride","중성지방",0,""),
            ("fasting_glucose","공복혈당",0,""),
            ("hba1c","당화혈색소",1,""),
            ("weight_kg","몸무게",1," kg"),
            ("systolic","수축기혈압",0," mmHg"),
        ]
        cards = []
        for col,label,digits,suffix in metrics:
            d, latest, prev = latest_two_nonnull(records, col)
            date_txt = d.strftime("%Y-%m-%d") if d is not None else "-"
            sub = f"{date_txt} · {delta_text(latest, prev, digits, suffix)}"
            cards.append(kpi_html(label, fmt(latest,digits,suffix), sub))
        st.markdown('<div class="kpi-grid">' + "".join(cards) + '</div>', unsafe_allow_html=True)

        c1,c2 = st.columns(2)
        with c1:
            trend_chart(records, ["total_chol","ldl","hdl","triglyceride"], "지질검사 추이")
        with c2:
            trend_chart(records, ["fasting_glucose","hba1c"], "혈당검사 추이")

        st.subheader("참고범위")
        st.caption("아래 값은 업로드한 Excel에 적힌 관리용 기준입니다. 검사기관의 참고범위와 다를 수 있으며 진단 기준으로 사용하지 않습니다.")
        ref_df = pd.DataFrame([
            {"항목":v["label"],"좋음 기준":v["good"],"보통/참고":v["normal"]}
            for v in REFERENCE.values()
        ])
        st.dataframe(ref_df, width="stretch", hide_index=True)

        st.subheader("최근 검사 기록")
        show = records.sort_values("exam_date", ascending=False).head(10).copy()
        cols = ["exam_date","total_chol","ldl","hdl","triglyceride","fasting_glucose","hba1c","weight_kg","systolic","diastolic","note"]
        show = show[cols]
        show.columns = ["검사일","총콜","LDL","HDL","중성지방","공복혈당","당화혈색소","몸무게","수축기","이완기","메모"]
        st.dataframe(show, width="stretch", hide_index=True)

        if not events.empty:
            st.subheader("최근 약물·이벤트")
            ev = events.sort_values("event_date", ascending=False).head(6).copy()
            ev = ev[["event_date","category","event_text"]]
            ev.columns = ["일자","구분","내용"]
            st.dataframe(ev, width="stretch", hide_index=True)

        st.caption("※ 개인 기록·변화 확인용 앱입니다. 검사 결과 해석, 약물 변경, 진단은 의료진과 상의하세요.")

elif page == "새 검사 기록":
    st.title("📝 새 검사 기록")
    with st.form("new_lab"):
        d = st.date_input("검사일", value=date.today())
        c1,c2,c3,c4 = st.columns(4)
        total_chol = c1.number_input("총콜레스테롤", min_value=0.0, step=1.0)
        ldl = c2.number_input("LDL", min_value=0.0, step=1.0)
        hdl = c3.number_input("HDL", min_value=0.0, step=1.0)
        tg = c4.number_input("중성지방", min_value=0.0, step=1.0)
        c1,c2,c3,c4 = st.columns(4)
        glucose = c1.number_input("공복혈당", min_value=0.0, step=1.0)
        hba1c = c2.number_input("당화혈색소", min_value=0.0, step=0.1)
        cpk = c3.number_input("CPK", min_value=0.0, step=1.0)
        bilirubin = c4.number_input("빌리루빈", min_value=0.0, step=0.1)
        c1,c2,c3,c4 = st.columns(4)
        ast = c1.number_input("GOT(AST)", min_value=0.0, step=1.0)
        altv = c2.number_input("GPT(ALT)", min_value=0.0, step=1.0)
        wbc = c3.number_input("WBC", min_value=0.0, step=0.1)
        mpv = c4.number_input("MPV", min_value=0.0, step=0.1)
        c1,c2,c3 = st.columns(3)
        vitd = c1.number_input("비타민D", min_value=0.0, step=0.1)
        height = c2.number_input("신장(cm)", min_value=0.0, step=0.1)
        weight = c3.number_input("몸무게(kg)", min_value=0.0, step=0.1)
        c1,c2 = st.columns(2)
        sys = c1.number_input("수축기 혈압", min_value=0, step=1)
        dia = c2.number_input("이완기 혈압", min_value=0, step=1)
        note = st.text_area("메모", placeholder="검사 당시 복용약, 공복 여부 등")
        submitted = st.form_submit_button("검사 기록 저장", type="primary", width="stretch")
        if submitted:
            def z(v): return None if v == 0 else float(v)
            rec = {
                "exam_date":d,"total_chol":z(total_chol),"ldl":z(ldl),"hdl":z(hdl),
                "triglyceride":z(tg),"fasting_glucose":z(glucose),"hba1c":z(hba1c),
                "cpk":z(cpk),"bilirubin":z(bilirubin),"ast_got":z(ast),"alt_gpt":z(altv),
                "wbc":z(wbc),"mpv":z(mpv),"vitamin_d":z(vitd),"height_cm":z(height),
                "weight_kg":z(weight),"systolic":None if sys==0 else int(sys),
                "diastolic":None if dia==0 else int(dia),"note":note,"source":"manual"
            }
            upsert_record(rec)
            st.success("저장했습니다.")
            st.rerun()

elif page == "검사 추이":
    st.title("📈 검사 추이")
    metric_group = st.selectbox("그래프 묶음", ["지질","혈당","간·빌리루빈·CPK","혈액·비타민D","개별 항목"])
    if metric_group == "지질":
        trend_chart(records, ["total_chol","ldl","hdl","triglyceride"], "지질검사 장기 추이")
    elif metric_group == "혈당":
        trend_chart(records, ["fasting_glucose","hba1c"], "혈당검사 장기 추이")
    elif metric_group == "간·빌리루빈·CPK":
        trend_chart(records, ["ast_got","alt_gpt","bilirubin","cpk"], "간수치·빌리루빈·CPK 추이")
    elif metric_group == "혈액·비타민D":
        trend_chart(records, ["wbc","mpv","vitamin_d"], "WBC·MPV·비타민D 추이")
    else:
        options = list(LABELS.keys())
        selected = st.selectbox("항목", options, format_func=lambda x: LABELS[x])
        trend_chart(records, [selected], f"{LABELS[selected]} 장기 추이")

    if not events.empty:
        st.subheader("약물·이벤트 타임라인")
        ev = events.sort_values("event_date", ascending=False).copy()
        ev = ev[["event_date","category","event_text"]]
        ev.columns = ["일자","구분","내용"]
        st.dataframe(ev, width="stretch", hide_index=True, height=260)

elif page == "신장·몸무게·혈압":
    st.title("📏 신장·몸무게·혈압")
    c1,c2 = st.columns(2)
    with c1:
        trend_chart(records, ["height_cm","weight_kg"], "신장·몸무게 변화")
    with c2:
        trend_chart(records, ["systolic","diastolic"], "혈압 변화")
    st.caption("몸무게와 신장은 기록 및 변화 확인 용도로만 표시하며 목표 체중이나 외모 기준을 제시하지 않습니다.")

elif page == "약물·이벤트":
    st.title("💊 약물·이벤트")
    with st.form("event_form"):
        d = st.date_input("일자", value=date.today())
        cat = st.selectbox("구분", ["약물","검사","증상","진료","기타"])
        txt = st.text_area("내용", placeholder="예: 약 복용 시작/중단, 검사 관련 특이사항")
        if st.form_submit_button("이벤트 저장", type="primary", width="stretch"):
            if txt.strip():
                save_event(d,cat,txt.strip())
                st.success("저장했습니다.")
                st.rerun()
    if not events.empty:
        show = events.sort_values("event_date", ascending=False)[["event_date","category","event_text"]]
        show.columns = ["일자","구분","내용"]
        st.dataframe(show, width="stretch", hide_index=True)

elif page == "기록 관리":
    st.title("📁 기록 관리")
    tab1,tab2 = st.tabs(["검사 기록","약물·이벤트"])

    with tab1:
        if records.empty:
            st.info("기록이 없습니다.")
        else:
            show = records.sort_values("exam_date", ascending=False).copy()
            display_cols = ["id","exam_date","total_chol","ldl","hdl","triglyceride","fasting_glucose","hba1c","weight_kg","systolic","diastolic","note"]
            st.dataframe(show[display_cols], width="stretch", hide_index=True)

            st.subheader("검사 기록 메모 수정")
            choices = show[["id","exam_date"]].copy()
            choices["label"] = choices.apply(lambda r: f"{r['exam_date'].strftime('%Y-%m-%d')} · ID {int(r['id'])}", axis=1)
            label = st.selectbox("수정할 검사", choices["label"].tolist(), key="edit_lab_select")
            rid = int(choices.loc[choices["label"]==label,"id"].iloc[0])
            current_note = show.loc[show["id"]==rid,"note"].iloc[0] or ""
            note_new = st.text_area("메모", value=current_note, key=f"note_{rid}")
            c1,c2 = st.columns(2)
            if c1.button("메모 저장", type="primary", width="stretch"):
                update_note(rid, note_new)
                st.success("메모를 수정했습니다.")
                st.rerun()
            confirm_del = c2.checkbox("삭제 확인", key=f"del_confirm_{rid}")
            if st.button("선택 검사 기록 삭제", disabled=not confirm_del, width="stretch", key=f"delete_lab_{rid}"):
                delete_record(rid)
                st.success("검사 기록을 삭제했습니다.")
                st.rerun()

    with tab2:
        if events.empty:
            st.info("기록이 없습니다.")
        else:
            ev = events.sort_values("event_date", ascending=False).copy()
            st.dataframe(ev[["id","event_date","category","event_text"]], width="stretch", hide_index=True)
            choices = ev.copy()
            choices["label"] = choices.apply(lambda r: f"{r['event_date'].strftime('%Y-%m-%d')} · {r['category']} · ID {int(r['id'])}", axis=1)
            label = st.selectbox("삭제할 이벤트", choices["label"].tolist(), key="event_delete_select")
            eid = int(choices.loc[choices["label"]==label,"id"].iloc[0])
            confirm = st.checkbox("이 이벤트를 삭제합니다.", key=f"event_confirm_{eid}")
            if st.button("선택 이벤트 삭제", disabled=not confirm, width="stretch"):
                delete_event(eid)
                st.success("이벤트를 삭제했습니다.")
                st.rerun()

elif page == "설정/백업":
    st.title("⚙️ 설정 / 백업")
    st.success("☁️ Supabase 클라우드 DB를 사용합니다.")
    st.info("휴대전화와 PC에서 같은 Streamlit 주소를 사용하면 동일한 최신 기록을 확인할 수 있습니다.")
    st.write("초기 파일:", setting_get("initial_file","-"))

    def export_zip():
        bio = io.BytesIO()
        with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("blood_lab_records.csv", load_records().to_csv(index=False).encode("utf-8-sig"))
            z.writestr("blood_events.csv", load_events().to_csv(index=False).encode("utf-8-sig"))
        return bio.getvalue()

    st.download_button(
        "전체 기록 CSV 백업 다운로드",
        data=export_zip(),
        file_name=f"blood_manager_backup_{date.today().isoformat()}.zip",
        mime="application/zip",
        width="stretch"
    )

    st.divider()
    st.subheader("로그인 PIN 재설정")
    st.caption("PIN을 잊었을 때는 Supabase SQL Editor에서 health_settings의 pin_hash만 삭제하면 다시 설정할 수 있습니다.")
