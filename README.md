# 내 혈액관리 V1.1 Cloud

업로드한 `3혈액검사 추이.xlsx`를 최초 1회 불러오고, 이후에는 Supabase 클라우드 DB에서 관리하는 Streamlit 앱입니다.

## 주요 기능
- 대시보드: 최신 총콜레스테롤, LDL, 공복혈당, 몸무게
- 지질/혈당/간수치/혈액/비타민D 추이 그래프
- 신장·몸무게·혈압 변화
- 새 검사 기록
- 약물·이벤트 기록
- 기록 관리
- CSV ZIP 백업
- PC/휴대폰 공용 모바일 메뉴
- 숫자 PIN 로그인

## Supabase
기존 자산관리 앱과 같은 Supabase 프로젝트를 사용해도 됩니다.
앱에서 `health_` 접두사의 별도 테이블을 자동 생성하므로 자산관리 데이터와 섞이지 않습니다.

## Streamlit Secrets
[database]
host = "Supabase Transaction pooler host"
port = 6543
database = "postgres"
user = "postgres.프로젝트참조값"
password = "실제 DB 비밀번호"

## 배포
별도 GitHub private repository 예: `my-blood-manager`를 만들고
- app.py
- requirements.txt
를 업로드한 뒤 Streamlit Community Cloud에서 배포합니다.

## 주의
이 앱은 개인 기록 및 추이 확인용입니다. 검사 수치의 의학적 의미, 진단, 약 변경은 의료진과 상의하세요.


## V1.1 추가
- 대시보드 8개 핵심지표와 직전 검사 대비 변화
- Excel 기준 참고범위 표
- 최근 약물·이벤트 대시보드 표시
- 개별 검사 항목 그래프
- 약물·이벤트 타임라인
- 검사 메모 수정
- 검사 기록 삭제 / 이벤트 삭제
- 모바일/PC 동일 클라우드 데이터
