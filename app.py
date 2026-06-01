import streamlit as st
import pandas as pd
import requests
import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 초기 설정 ---
st.set_page_config(
    page_title="오운완 플래너",
    page_icon="💪",
    layout="centered"
)

SPREADSHEET_ID = "16tI6GP6KSHkK6nprGOVuuzO5aeZu2YSch-dadJqm4hw"

# 대한민국 주요 지역별 기상청 격자 좌표(nx, ny) 매핑 데이터
REGION_COORDS = {
    "서울": {"nx": 60, "ny": 127},
    "부산": {"nx": 98, "ny": 76},
    "대구": {"nx": 89, "ny": 90},
    "인천": {"nx": 55, "ny": 124},
    "광주": {"nx": 58, "ny": 74},
    "대전": {"nx": 67, "ny": 100},
    "울산": {"nx": 102, "ny": 84},
    "세종": {"nx": 66, "ny": 103},
    "경기(수원)": {"nx": 60, "ny": 121},
    "강원(춘천)": {"nx": 73, "ny": 134},
    "충북(청주)": {"nx": 69, "ny": 107},
    "충남(홍성)": {"nx": 55, "ny": 106},
    "전북(전주)": {"nx": 63, "ny": 89},
    "전남(무안)": {"nx": 51, "ny": 67},
    "경북(안동)": {"nx": 91, "ny": 106},
    "경남(창원)": {"nx": 90, "ny": 77},
    "제주": {"nx": 52, "ny": 38}
}

# --- 2. 구글 스프레드시트 연동 함수 ---
@st.cache_resource
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(credentials)

# 💡 지역 변경 시 속도 향상을 위해 구글 시트 데이터 로딩을 1분간 캐싱합니다.
@st.cache_data(ttl=60)
def load_sheet_data(worksheet_idx):
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
    client = get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.get_worksheet(worksheet_idx)
    worksheet.append_row(row_data)

def update_plan_status(row_idx, status_value):
    client = get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.get_worksheet(0)
    worksheet.update_cell(row_idx + 2, 4, status_value)


# --- 3. 기상청 단기예보 조회 API 연동 함수 ---
@st.cache_data(ttl=900)
def get_kma_weather(nx, ny):
    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    service_key = st.secrets["weather"]["api_key"]
    
    now = datetime.datetime.now()
    available_hours = [2, 5, 8, 11, 14, 17, 20, 23]
    current_hour = now.hour
    
    # 🛠️ [버그 수정] %Y%m%dd -> %Y%m%d 로 오타 수정 완료
    base_date = now.strftime("%Y%m%d")
    base_hour = 23
    for h in reversed(available_hours):
        if current_hour >= h:
            base_hour = h
            break
            
    if current_hour < 2:
        base_date = (now - datetime.timedelta(days=1)).strftime("%Y%m%d")
        base_hour = 23
    else:
        base_date = now.strftime("%Y%m%d")
        
    base_time = f"{base_hour:02d}00"
    
    params = {
        "serviceKey": service_key,
        "pageNo": "1",
        "numOfRows": "60",
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
        for item in items:
            category = item['category']
            value = item['fcstValue']
            if category in weather_info:
                weather_info[category] = value
                
        sky_status = {"1": "맑음 ☀️", "3": "구름많음 ☁️", "4": "흐림 🌧️"}
        sky_text = sky_status.get(weather_info["SKY"], "정보없음")
        
        return {
            "temp": f"{weather_info['TMP']}°C",
            "sky": sky_text,
            "pop": f"{weather_info['POP']}%"
        }
    except Exception:
        return {"temp": "24°C", "sky": "연동 확인 중 🔄", "pop": "0%"}


# --- 4. 메인 어플리케이션 레이아웃 ---

st.title("💪 오늘 운동 완료!")

# 데이터 로드
plan_df = load_sheet_data(0)
record_df = load_sheet_data(1)

main_tabs = st.tabs(["🏠 홈 / 날씨", "📅 운동 계획", "✅ 기록 입력"])

# ---------------------------------------------------------
# Tab 1: 🏠 홈 / 날씨 및 현황판
# ---------------------------------------------------------
with main_tabs[0]:
    st.markdown("### 🌤️ 운동 지역 날씨")
    
    # 모바일 상태 유지용 key 추가 및 안정적인 셀렉트박스 구현
    selected_region = st.selectbox(
        "날씨를 조회할 지역 선택", 
        options=list(REGION_COORDS.keys()), 
        index=0,
        key="weather_region_select"
    )
    
    coords = REGION_COORDS[selected_region]
    weather = get_kma_weather(nx=coords["nx"], ny=coords["ny"])
    
    with st.container(border=True):
        w_col1, w_col2, w_col3 = st.columns(3)
        w_col1.metric("기온", weather["temp"])
        w_col2.metric("하늘", weather["sky"])
        w_col3.metric("강수확률", weather["pop"])
        st.caption(f"📍 현재 {selected_region} 기준 실시간 단기예보 정보입니다.")

    st.markdown("---")

    st.markdown("### 🔥 오늘 나의 달성 현황")
    if not plan_df.empty and "상태" in plan_df.columns:
        total_plans = len(plan_df)
        done_plans = len(plan_df[plan_df["상태"] == "✅ 완료"])
        success_rate = int((done_plans / total_plans) * 100) if total_plans > 0 else 0
        st.progress(success_rate / 100, text=f"목표 {total_plans}개 중 {done_plans}개 성공 ({success_rate}%)")
    else:
        st.caption("⏳ 아직 등록된 운동 계획이 없습니다. [📅 운동 계획] 탭에서 첫 계획을 세워보세요!")

    st.markdown("---")

    st.markdown("### 📋 전체 계획 내역")
    if not plan_df.empty:
        filter_status = st.segmented_control("정렬 필터", ["전체", "⏳ 대기", "✅ 완료"], default="전체")
        display_df = plan_df
        if filter_status != "전체":
            display_df = plan_df[plan_df["상태"] == filter_status]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# Tab 2: 📅 운동 계획 수립
# ---------------------------------------------------------
with main_tabs[1]:
    st.markdown("### 📅 새로운 운동 계획")
    
    with st.form("mobile_plan_form", clear_on_submit=True):
        plan_date = st.date_input("운동 날짜", datetime.date.today())
        exercise_type = st.selectbox("어떤 운동을 할까요?", ["러닝", "스쿼트", "벤치프레스", "데드리프트", "플랭크", "직접 입력"])
        
        if exercise_type == "직접 입력":
            exercise_type = st.text_input("운동 이름을 써주세요")
            
        target_amount = st.text_input("목표량 (예: 5km, 100개)")
        
        submit_plan = st.form_submit_button("📅 계획 시트에 저장", use_container_width=True)
        if submit_plan:
            new_row = [str(plan_date), exercise_type, target_amount, "⏳ 대기"]
            append_to_sheet(0, new_row)
            
            # 💡 데이터를 추가했으므로 캐시를 지워 홈 화면에 즉시 반영되도록 합니다.
            st.cache_data.clear()
            st.success("계획이 저장되었습니다! 🏠 홈 탭에서 확인하세요.")
            st.rerun()

# ---------------------------------------------------------
# Tab 3: ✅ 실제 운동 결과 기록
# ---------------------------------------------------------
with main_tabs[2]:
    st.markdown("### ✅ 오늘 운동 완료 기록")
    
    if not plan_df.empty and "상태" in plan_df.columns:
        pending_workouts = plan_df[plan_df["상태"] == "⏳ 대기"]
        
        if not pending_workouts.empty:
            with st.form("mobile_result_form", clear_on_submit=True):
                workout_options = pending_workouts.apply(lambda r: f"[{r['날짜']}] {r['운동종류']} (목표:{r['목표량']})", axis=1)
                selected_idx = st.selectbox("완료한 운동을 선택하세요", options=workout_options.index, format_func=lambda x: workout_options[x])
                
                actual_amount = st.text_input("실제 수행량 (예: 5km, 90개)")
                status = st.radio("달성 현황", ["✅ 완료", "⚠️ 미달성"], horizontal=True)
                
                submit_result = st.form_submit_button("💾 기록 시트에 최종 저장", use_container_width=True)
                if submit_result:
                    target_row = plan_df.loc[selected_idx]
                    
                    record_row = [
                        target_row["날짜"],
                        target_row["운동종류"],
                        actual_amount,
                        status,
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ]
                    
                    append_to_sheet(1, record_row)
                    update_plan_status(int(selected_idx), status)
                    
                    # 💡 데이터를 새로 썼으므로 캐시를 비워줍니다.
                    st.cache_data.clear()
                    st.success("스프레드시트 결과 반영 성공! 오늘도 고생하셨습니다.")
                    st.rerun()
        else:
            st.info("⏳ 대기 중인 계획이 없습니다. 먼저 운동 계획을 세워주세요!")
    else:
        st.warning("스프레드시트가 비어있거나 데이터를 가져올 수 없습니다.")