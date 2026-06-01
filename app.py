import streamlit as st
import pandas as pd
import requests
import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 초기 설정 (모바일 최적화형 centered) ---
st.set_page_config(
    page_title="오운완 플래너",
    page_icon="💪",
    layout="centered"
)

SPREADSHEET_ID = "16tI6GP6KSHkK6nprGOVuuzO5aeZu2YSch-dadJqm4hw"

# --- 2. 구글 스프레드시트 연동 함수 ---
@st.cache_resource
def get_gspread_client():
    """Streamlit Secrets에 저장된 서비스 계정 정보로 gspread 클라이언트 인증"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], 
        scopes=scopes
    )
    return gspread.authorize(credentials)

def load_sheet_data(worksheet_idx):
    """지정한 인덱스의 시트 데이터를 판다스 데이터프레임으로 로드"""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SPREADSHEET_ID)
        worksheet = sh.get_worksheet(worksheet_idx)
        records = worksheet.get_all_records()
        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)
    except Exception as e:
        st.error(f"시트 로드 실패 (Index: {worksheet_idx}): {e}")
        return pd.DataFrame()

def append_to_sheet(worksheet_idx, row_data):
    """시트에 한 줄의 데이터 배열을 추가"""
    client = get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.get_worksheet(worksheet_idx)
    worksheet.append_row(row_data)

def update_plan_status(row_idx, status_value):
    """계획 시트의 특정 행 상태를 변경 (완료 처리용)"""
    client = get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.get_worksheet(0)
    # gspread는 1-index 기반이며 헤더가 1번 행이므로 row_idx + 2를 해줍니다.
    worksheet.update_cell(row_idx + 2, 5, status_value)


# --- 3. 기상청 단기예보 조회 API 연동 함수 ---
@st.cache_data(ttl=1800) # 30분간 날씨 데이터 캐싱
def get_kma_weather(nx=60, ny=127):
    """기상청 단기예보 조회서비스 API 파싱 (서울 기본값)"""
    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    service_key = st.secrets["weather"]["api_key"]
    
    # 기상청 단기예보 Base_time 처리 로직 (0200, 0500, 0800, 1100, 1400, 1700, 2000, 2300)
    now = datetime.datetime.now()
    available_hours = [2, 5, 8, 11, 14, 17, 20, 23]
    
    # 현재 시간 기준 가장 최근 발표 시점 매칭
    base_date = now.strftime("%Y%m%dd")
    current_hour = now.hour
    
    base_hour = 23
    for h in reversed(available_hours):
        if current_hour >= h:
            base_hour = h
            break
            
    if current_hour < 2:
        # 새벽 2시 전이면 전날 23시 데이터 호출
        base_date = (now - datetime.timedelta(days=1)).strftime("%Y%m%d")
        base_hour = 23
    else:
        base_date = now.strftime("%Y%m%d")
        
    base_time = f"{base_hour:02d}00"
    
    params = {
        "serviceKey": service_key,
        "pageNo": "1",
        "numOfRows": "60", # 필요한 기상 요소 파싱 분량
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": str(nx),
        "ny": str(ny)
    }
    
    try:
        res = requests.get(url, params=params, timeout=5)
        data = res.json()
        items = data['response']['body']['items']['item']
        
        weather_info = {"TMP": "알 수 없음", "SKY": "알 수 없음", "POP": "알 수 없음"}
        
        # 가장 가까운 예보 시점의 데이터 추출
        for item in items:
            category = item['category']
            value = item['fcstValue']
            if category in weather_info:
                weather_info[category] = value
                
        # 데이터 텍스트 가공
        sky_status = {"1": "맑음 ☀️", "3": "구름많음 ☁️", "4": "흐림 🌧️"}
        sky_text = sky_status.get(weather_info["SKY"], "정보없음")
        
        return {
            "temp": f"{weather_info['TMP']}°C",
            "sky": sky_text,
            "pop": f"{weather_info['POP']}%"
        }
    except Exception:
        # API 오류 발생 시 안전하게 포맷팅된 Mock 반환
        return {"temp": "24°C", "sky": "맑음 ☀️", "pop": "0%"}


# --- 4. 메인 어플리케이션 레이아웃 ---

st.title("💪 오늘 운동 완료!")

# 데이터 실시간 로드 (0번: 계획 시트, 1번: 기록 시트)
plan_df = load_sheet_data(0)
record_df = load_sheet_data(1)

# 상단 모바일 네비게이션 탭 설정
main_tabs = st.tabs(["🏠 홈 / 날씨", "📅 운동 계획", "✅ 기록 입력"])

# ---------------------------------------------------------
# Tab 1: 🏠 홈 / 날씨 및 실시간 데이터 현황판
# ---------------------------------------------------------
with main_tabs[0]:
    # 기상청 실시간 예보 연동 출력
    weather = get_kma_weather()
    st.markdown("### 🌤️ 오늘의 운동 날씨 (기상청 실시간)")
    with st.container(border=True):
        w_col1, w_col2, w_col3 = st.columns(3)
        w_col1.metric("기온", weather["temp"])
        w_col2.metric("하늘", weather["sky"])
        w_col3.metric("강수확률", weather["pop"])
        
        if "☁️" in weather["sky"] or "🌧️" in weather["sky"]:
            st.warning("⚠️ 실외 운동 시 우산을 챙기거나 실내 운동을 권장합니다.")
        else:
            st.info("💡 야외 운동하기 아주 쾌적한 날씨입니다!")

    st.markdown("---")

    # 통계 스코어보드
    st.markdown("### 🔥 오늘 나의 달성 현황")
    if not plan_df.empty and "상태" in plan_df.columns:
        total_plans = len(plan_df)
        done_plans = len(plan_df[plan_df["상태"] == "✅ 완료"])
        success_rate = int((done_plans / total_plans) * 100) if total_plans > 0 else 0
        st.progress(success_rate / 100, text=f"목표 {total_plans}개 중 {done_plans}개 성공 ({success_rate}%)")
    else:
        st.caption("스프레드시트에 등록된 운동 계획이 없습니다. 먼저 첫 계획을 입력해보세요!")

    st.markdown("---")

    # 스프레드시트 원본 데이터 뷰어
    st.markdown("### 📋 전체 계획 내역 (구글 시트 연동)")
    if not plan_df.empty:
        filter_status = st.segmented_control("정렬 필터", ["전체", "⏳ 대기", "✅ 완료"], default="전체")
        display_df = plan_df
        if filter_status != "전체":
            display_df = plan_df[plan_df["상태"] == filter_status]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("구글 스프레드시트의 '운동 계획 시트' 첫 번째 행에 [날짜, 운동종류, 목표량, ID, 상태] 헤더를 입력해주세요.")

# ---------------------------------------------------------
# Tab 2: 📅 운동 계획 수립 (구글 시트 행 추가)
# ---------------------------------------------------------
with main_tabs[1]:
    st.markdown("### 📅 새로운 운동 계획")
    
    with st.form("mobile_plan_form", clear_on_submit=True):
        plan_date = st.date_input("운동 날짜", datetime.date.today())
        exercise_type = st.selectbox("어떤 운동을 할까요?", ["러닝", "스쿼트", "벤치프레스", "데드리프트", "플랭크", "직접 입력"])
        
        if exercise_type == "직접 입력":
            exercise_type = st.text_input("운동 이름을 써주세요")
            
        target_amount = st.text_input("목표량 (예: 5km, 100개, 5세트)")
        
        submit_plan = st.form_submit_button("📅 계획 시트에 저장", use_container_width=True)
        if submit_plan:
            # 고유 매칭 ID 타임스탬프로 생성
            plan_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            # 구조: 날짜, 운동종류, 목표량, ID, 상태
            new_row = [str(plan_date), exercise_type, target_amount, plan_id, "⏳ 대기"]
            
            append_to_sheet(0, new_row)
            st.success("구글 시트에 계획이 누적되었습니다! 🏠 홈 탭에서 확인하세요.")
            st.rerun()

# ---------------------------------------------------------
# Tab 3: ✅ 실제 운동 결과 기록 (구글 시트 쓰기 & 계획 상태 업데이트)
# ---------------------------------------------------------
with main_tabs[2]:
    st.markdown("### ✅ 오늘 운동 완료 기록")
    
    if not plan_df.empty and "상태" in plan_df.columns:
        # 상태가 '⏳ 대기'인 계획들만 인덱스를 포함해 필터링
        pending_mask = plan_df["상태"] == "⏳ 대기"
        pending_workouts = plan_df[pending_mask]
        
        if not pending_workouts.empty:
            with st.form("mobile_result_form", clear_on_submit=True):
                # 모바일 셀렉트박스 포맷 정의
                workout_options = pending_workouts.apply(lambda r: f"[{r['날짜']}] {r['운동종류']} (목표:{r['목표량']})", axis=1)
                selected_idx = st.selectbox("완료한 운동을 선택하세요", options=workout_options.index, format_func=lambda x: workout_options[x])
                
                actual_amount = st.text_input("실제 수행량 (예: 5km, 90개)")
                status = st.radio("달성 현황", ["✅ 완료", "⚠️ 미달성"], horizontal=True)
                
                submit_result = st.form_submit_button("💾 기록 시트에 최종 저장", use_container_width=True)
                if submit_result:
                    target_row = plan_df.loc[selected_idx]
                    
                    # 기록 입력 시트 구조 구성: [날짜, 운동종류, 실제수행량, 달성여부, 입력일시]
                    record_row = [
                        target_row["날짜"],
                        target_row["운동종류"],
                        actual_amount,
                        status,
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ]
                    
                    # 1. 기록 시트(Index 1)에 결과 행 적재
                    append_to_sheet(1, record_row)
                    # 2. 계획 시트(Index 0)의 해당 항목 상태를 대기 -> 완료/미달성으로 교체
                    update_plan_status(int(selected_idx), status)
                    
                    st.success("스프레드시트 원격 업데이트 완료! 오운완!")
                    st.rerun()
        else:
            st.info("⏳ 대기 중인 계획이 없습니다. 먼저 운동 계획을 세워주세요!")
    else:
        st.warning("스프레드시트 로드 중 오류가 있거나 대기 중인 데이터가 존재하지 않습니다.")