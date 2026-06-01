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
# 경기(수원) 기상청 격자 좌표 고정
NX, NY = 60, 121 

# --- 2. 구글 스프레드시트 연동 함수 ---
@st.cache_resource
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(credentials)

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


# --- 3. 기상청 단기예보 API 연동 (이후 6시간 필터링) ---

@st.cache_data(ttl=1800) # 원본 API 호출만 30분간 캐싱
def fetch_kma_raw_data(base_date, base_time):
    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    service_key = st.secrets["weather"]["api_key"].strip()
    
    params = {
        "serviceKey": service_key,
        "pageNo": "1",
        "numOfRows": "300", 
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": str(NX),
        "ny": str(NY)
    }
    try:
        res = requests.get(url, params=params, timeout=7)
        if res.status_code != 200:
            return {"error": f"기상청 서버 연결 실패 (HTTP: {res.status_code})"}
        try:
            return res.json()
        except Exception:
            return {"error": f"기상청 시스템 에러 발생: {res.text}"}
    except Exception as e:
        return {"error": f"네트워크 통신 오류: {str(e)}"}

def get_suwon_hourly_weather():
    now = datetime.datetime.now()
    available_hours = [2, 5, 8, 11, 14, 17, 20, 23]
    current_hour = now.hour
    
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
    
    raw_data = fetch_kma_raw_data(base_date, base_time)
    
    if "error" in raw_data:
        st.error(raw_data["error"])
        return pd.DataFrame()
        
    try:
        if 'response' not in raw_data or 'body' not in raw_data['response'] or 'items' not in raw_data['response']['body']:
            msg = raw_data.get('response', {}).get('header', {}).get('resultMsg', '데이터 구조 오류')
            st.error(f"기상청 응답 에러 메시지: {msg}")
            return pd.DataFrame()
            
        items = raw_data['response']['body']['items']['item']
        
        hourly_dict = {}
        for item in items:
            key = (item['fcstDate'], item['fcstTime'])
            if key not in hourly_dict:
                hourly_dict[key] = {}
            hourly_dict[key][item['category']] = item['fcstValue']
            
        parsed_records = []
        
        for (f_date, f_time), categories in sorted(hourly_dict.items()):
            f_dt = datetime.datetime.strptime(f_date + f_time, "%Y%m%d%H%M")
            
            # 조회 시점 기준 '이후' 시간대만 적용
            if f_dt <= now:
                continue
                
            # 🛠️ [수정 포인트] 이후 미래 데이터가 6개 채워지면 즉시 종료
            if len(parsed_records) >= 6:
                break
                
            f_date_obj = f_dt.date()
            date_label = "오늘" if f_date_obj == now.date() else "내일"
            time_label = f"{f_time[:2]}:00"
            
            temp = f"{categories.get('TMP', '-')}°C"
            precipitation = categories.get('PCP', '-')
            if precipitation == "강수없음":
                precipitation = "0mm"
                
            sky_code = categories.get('SKY', '1')
            sky_icon = {"1": "☀️", "3": "☁️", "4": "☁️"}.get(sky_code, "☀️")
            
            parsed_records.append({
                "일자": date_label,
                "시간": time_label,
                "날씨": sky_icon,
                "온도": temp,
                "강수량": precipitation
            })
            
        return pd.DataFrame(parsed_records)
        
    except Exception as e:
        st.error(f"데이터 가공 중 오류 발생: {e}")
        return pd.DataFrame()


# --- 4. 메인 UI 화면 구성 ---

st.title("💪 오늘 운동 완료!")

plan_df = load_sheet_data(0)
record_df = load_sheet_data(1)

main_tabs = st.tabs(["🏠 홈 / 날씨", "📅 운동 계획", "✅ 기록 입력"])

# ---------------------------------------------------------
# Tab 1: 🏠 홈 / 날씨 및 운동 현황
# ---------------------------------------------------------
with main_tabs[0]:
    # 🛠️ 타이틀 문구 6시간으로 수정
    st.markdown("### 🌤️ 경기(수원) 시간대별 날씨 예보 (이후 6시간)")
    
    weather_df = get_suwon_hourly_weather()
    
    if not weather_df.empty:
        st.dataframe(
            weather_df,
            use_container_width=True,
            hide_index=True
        )
        
        if "강수량" in weather_df.columns:
            rain_rows = weather_df[weather_df["강수량"] != "0mm"]
            if not rain_rows.empty:
                first_rain_idx = rain_rows.index[0]
                st.warning(f"⚠️ {weather_df.loc[first_rain_idx, '일자']} {weather_df.loc[first_rain_idx, '시간']}에 비 예보({weather_df.loc[first_rain_idx, '강수량']})가 있습니다!")
            else:
                # 🛠️ 알림 텍스트 문구 6시간으로 수정
                st.info("💡 향후 6시간 동안 비 소식이 없습니다. 야외 운동하기 최고입니다!")

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
                    st.cache_data.clear() 
                    st.success("스프레드시트 결과 반영 성공! 오늘도 고생하셨습니다.")
                    st.rerun()
        else:
            st.info("⏳ 대기 중인 계획이 없습니다. 먼저 운동 계획을 세워주세요!")
    else:
        st.warning("스프레드시트가 비어있거나 데이터를 가져올 수 없습니다.")