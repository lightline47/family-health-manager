# 우리가족 건강관리 Cloud V1.0

현재 오프라인 V2.33의 화면/기능을 최대한 유지하면서 저장소를 SQLite에서 Supabase로 바꾼 클라우드판입니다.

## 1. Supabase 준비
1. Supabase 프로젝트를 하나 만듭니다.
2. SQL Editor에서 `supabase_schema.sql` 전체를 실행합니다.
3. Project URL과 서버용 Secret/Service Role Key를 준비합니다.

## 2. Streamlit Secrets
Streamlit Community Cloud의 App settings > Secrets에 다음 형식으로 넣습니다.

```toml
SUPABASE_URL = "https://...supabase.co"
SUPABASE_SECRET_KEY = "..."
FAMILY_ID = "oh-family"
```

**Secret/Service Role Key는 GitHub에 절대 올리지 마세요.** 이 앱은 서버에서만 해당 키를 읽습니다.

## 3. GitHub 저장소
이 폴더의 `app.py`, `requirements.txt`, `supabase_schema.sql`을 GitHub 저장소에 올립니다. `.streamlit/secrets.toml.example`은 예시만 들어 있고 실제 키는 포함하지 않습니다.

## 4. Streamlit Community Cloud 배포
- GitHub 저장소를 선택합니다.
- Entry point는 `app.py`입니다.
- Secrets에 위 3개 값을 넣습니다.
- 배포 후 생성된 `*.streamlit.app` 주소를 휴대전화 홈 화면에 추가하거나 가족에게 공유할 수 있습니다.

## 5. 기존 PC 데이터 옮기기
기존 `data/blood_manager.db`가 있다면 `migrate_sqlite_to_supabase.py`로 이전할 수 있습니다. Windows PowerShell 예시:

```powershell
$env:SUPABASE_URL="https://...supabase.co"
$env:SUPABASE_SECRET_KEY="..."
$env:FAMILY_ID="oh-family"
$env:LOCAL_DB_PATH="C:\경로\data\blood_manager.db"
python migrate_sqlite_to_supabase.py
```

## 로그인 방식
Cloud V1.0은 현재 오프라인 앱과 동일한 **가족 공용 PIN** 방식을 유지합니다. 첫 접속자가 PIN을 설정하면 PC와 휴대전화에서 같은 PIN을 사용합니다. 다음 단계에서 아빠/엄마/아들 개별 계정과 권한 분리로 확장할 수 있습니다.
