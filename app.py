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
NX, NY = 60, 121 # 경기(수원) 좌표

# 대한민국 표준시(KST) 타임존 정의
KST = datetime.timezone(datetime.timedelta(hours=9))

# --- 2. 구글 스프레드시트 연동 및 수정/삭제 유틸리티 ---
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

def delete_sheet_row(worksheet_idx, row_idx):
    client = get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.get_worksheet(worksheet_idx)
    worksheet.delete_rows(row_idx + 2)

def update_sheet_row(worksheet_idx, row_idx, row_data):
    client = get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.get_worksheet(worksheet_idx)
    for col_idx, value in enumerate(row_data, start=1):
        worksheet.update_cell(row_idx + 2, col_idx, str(value))


# --- 3. 기상청 단기예보 API 연동 ---
@st.cache_data(ttl=1800)
def fetch_kma_raw_data(base_date, base_time):
    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    service_key = st.secrets["weather"]["api_key"].strip()
    
    params = {
        "serviceKey": service_key, "pageNo": "1", "numOfRows": "300", 
        "dataType": "JSON", "base_date": base_date, "base_time": base_time, "nx": str(NX), "ny": str(NY)
    }
    try:
        res = requests.get(url, params=params, timeout=7)
        if res.status_code != 200: return {"error": "기상청 서버 연결 실패"}
        try: return res.json()
        except: return {"error": "기상청 시스템 응답 오류"}
    except Exception as e: return {"error": str(e)}

def get_suwon_hourly_weather():
    now = datetime.datetime.now(KST).replace(tzinfo=None)
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
            return pd.DataFrame()
            
        items = raw_data['response']['body']['items']['item']
        hourly_dict = {}
        for item in items:
            key = (item['fcstDate'], item['fcstTime'])
            if key not in hourly_dict: hourly_dict[key] = {}
            hourly_dict[key][item['category']] = item['fcstValue']
            
        parsed_records = []
        for (f_date, f_time), categories in sorted(hourly_dict.items()):
            f_dt = datetime.datetime.strptime(f_date + f_time, "%Y%m%d%H%M")
            if f_dt <= now: continue
            if len(parsed_records) >= 6: break
                
            f_date_obj = f_dt.date()
            date_label = "오늘" if f_date_obj == now.date() else "내일"
            time_label = f"{f_time[:2]}:00"
            temp = f"{categories.get('TMP', '-')}°C"
            precipitation = categories.get('PCP', '-')
            if precipitation == "강수없음": precipitation = "0mm"
            
            sky_code = categories.get('SKY', '1')
            sky_icon = {"1": "☀️", "3": "☁️", "4": "☁️"}.get(sky_code, "☀️")
            
            parsed_records.append({
                "일자": date_label, "시간": time_label, "날씨": sky_icon, "온도": temp, "강수량": precipitation
            })
        return pd.DataFrame(parsed_records)
    except:
        return pd.DataFrame()


# --- 4. 메인 UI 화면 구성 ---

st.title("💪 오늘 운동 완료!")

# 데이터 실시간 로드
plan_df = load_sheet_data(0)
record_df = load_sheet_data(1)

main_tabs = st.tabs(["🏠 홈 / 날씨", "📅 운동 계획", "✅ 기록 입력", "⚙️ 수정/삭제"])

# ---------------------------------------------------------
# Tab 1: 🏠 홈 / 날씨 및 고도화된 달성도 대시보드
# ---------------------------------------------------------
with main_tabs[0]:
    st.markdown("### 🌤️ 경기(수원) 시간대별 날씨 예보 (이후 6시간)")
    now_kst = datetime.datetime.now(KST)
    st.markdown(f"**🕒 현재 조회 시간:** `{now_kst.strftime('%Y년 %m월 %d일 %H시 %M분 %S초')}`")
    st.markdown("") 
    
    weather_df = get_suwon_hourly_weather()
    if not weather_df.empty:
        st.dataframe(weather_df, use_container_width=True, hide_index=True)
        if "강수량" in weather_df.columns:
            rain_rows = weather_df[weather_df["강수량"] != "0mm"]
            if not rain_rows.empty:
                st.warning(f"⚠️ {weather_df.loc[rain_rows.index[0], '일자']} {weather_df.loc[rain_rows.index[0], '시간']}에 비 예보가 있습니다!")
            else:
                st.info("💡 향후 6시간 동안 비 소식이 없습니다. 야외 운동하기 최고입니다!")

    st.markdown("---")
    
    # 🛠️ [기능 고도화] 오늘 / 주별 / 월별 진행률 계산 영역
    st.markdown("### 📊 나의 운동 달성도 분석")
    
    if not plan_df.empty and "상태" in plan_df.columns and "날짜" in plan_df.columns:
        # 안전한 날짜 데이터 매핑 (문자열 -> Date 객체)
        plan_df['parsed_date'] = pd.to_datetime(plan_df['날짜'], errors='coerce').dt.date
        current_date = now_kst.date()
        
        # 1️⃣ 오늘 진행률
        today_df = plan_df[plan_df['parsed_date'] == current_date]
        t_total = len(today_df)
        t_done = len(today_df[today_df['상태'] == "✅ 완료"])
        t_rate = int((t_done / t_total) * 100) if t_total > 0 else 0
        
        # 2️⃣ 이번 주 진행률 (현재 요일 기준 월요일 ~ 일요일 계산)
        start_of_week = current_date - datetime.timedelta(days=current_date.weekday())
        end_of_week = start_of_week + datetime.timedelta(days=6)
        week_df = plan_df[(plan_df['parsed_date'] >= start_of_week) & (plan_df['parsed_date'] <= end_of_week)]
        w_total = len(week_df)
        w_done = len(week_df[week_df['상태'] == "✅ 완료"])
        w_rate = int((w_done / w_total) * 100) if w_total > 0 else 0
        
        # 3️⃣ 이번 달 진행률
        month_df = plan_df[plan_df['parsed_date'].apply(lambda x: x.year == current_date.year and x.month == current_date.month if pd.notnull(x) else False)]
        m_total = len(month_df)
        m_done = len(month_df[month_df['상태'] == "✅ 완료"])
        m_rate = int((m_done / m_total) * 100) if m_total > 0 else 0
        
        # 모바일용 스택 레이아웃 출력
        st.markdown("**📅 오늘 달성률**")
        if t_total > 0:
            st.progress(t_rate / 100, text=f"{t_total}개 중 {t_done}개 성공 ({t_rate}%)")
        else:
            st.caption("오늘 예정된 운동 계획이 없습니다.")
            
        st.markdown("**📅 이번 주 달성률 (월~일)**")
        if w_total > 0:
            st.progress(w_rate / 100, text=f"{w_total}개 중 {w_done}개 성공 ({w_rate}%)")
        else:
            st.caption("이번 주에 등록된 운동 계획이 없습니다.")
            
        st.markdown("**📅 이번 달 달성률**")
        if m_total > 0:
            st.progress(m_rate / 100, text=f"{m_total}개 중 {m_done}개 성공 ({m_rate}%)")
        else:
            st.caption("이번 달에 등록된 운동 계획이 없습니다.")
            
    else:
        st.caption("⏳ 데이터 분석을 위해 먼저 운동 계획을 등록해 주세요!")

    st.markdown("---")
    st.markdown("### 📋 전체 계획 내역")
    if not plan_df.empty:
        filter_status = st.segmented_control("정렬 필터", ["전체", "⏳ 대기", "✅ 완료"], default="전체")
        display_df = plan_df
        if filter_status != "전체":
            display_df = plan_df[plan_df["상태"] == filter_status]
        # 임시 생성한 날짜 파싱 컬럼은 제외하고 출력
        if 'parsed_date' in display_df.columns:
            display_df = display_df.drop(columns=['parsed_date'])
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# Tab 2: 📅 운동 계획 수립
# ---------------------------------------------------------
with main_tabs[1]:
    st.markdown("### 📅 새로운 운동 계획")
    with st.form("mobile_plan_form", clear_on_submit=True):
        plan_date = st.date_input("운동 날짜", datetime.datetime.now(KST).date())
        exercise_type = st.selectbox("어떤 운동을 할까요?", ["러닝", "스쿼트", "벤치프레스", "데드리프트", "플랭크", "직접 입력"])
        if exercise_type == "직접 입력": exercise_type = st.text_input("운동 이름을 써주세요")
        target_amount = st.text_input("목표량 (예: 5km, 100개)")
        
        if st.form_submit_button("📅 계획 시트에 저장", use_container_width=True):
            append_to_sheet(0, [str(plan_date), exercise_type, target_amount, "⏳ 대기"])
            st.cache_data.clear() 
            st.success("계획이 저장되었습니다!")
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
                selected_idx = st.selectbox("완료한 운동 선택", options=workout_options.index, format_func=lambda x: workout_options[x])
                actual_amount = st.text_input("실제 수행량 (예: 5km, 90개)")
                status = st.radio("달성 현황", ["✅ 완료", "⚠️ 미달성"], horizontal=True)
                
                if st.form_submit_button("💾 기록 시트에 최종 저장", use_container_width=True):
                    target_row = plan_df.loc[selected_idx]
                    now_kst_naive = datetime.datetime.now(KST).replace(tzinfo=None)
                    
                    append_to_sheet(1, [target_row["날짜"], target_row["운동종류"], actual_amount, status, now_kst_naive.strftime("%Y-%m-%d %H:%M:%S")])
                    update_plan_status(int(selected_idx), status)
                    st.cache_data.clear() 
                    st.success("스프레드시트에 성공적으로 기록되었습니다!")
                    st.rerun()
        else:
            st.info("⏳ 대기 중인 계획이 없습니다.")
    else:
        st.warning("스프레드시트 데이터를 가져올 수 없습니다.")

# ---------------------------------------------------------
# Tab 4: ⚙️ 데이터 관리 (수정 및 삭제 통합)
# ---------------------------------------------------------
with main_tabs[3]:
    st.markdown("### ⚙️ 계획 및 기록 데이터 관리")
    manage_target = st.radio("관리 대상 선택", ["📅 운동 계획 관리", "📋 운동 기록 관리"], horizontal=True)
    
    if manage_target == "📅 운동 계획 관리":
        if not plan_df.empty:
            plan_options = plan_df.apply(lambda r: f"[{r['날짜']}] {r['운동종류']} - {r['상태']}", axis=1)
            edit_p_idx = st.selectbox("수정/삭제할 계획 선택", options=plan_options.index, format_func=lambda x: plan_options[x], key="edit_p_select")
            p_row = plan_df.loc[edit_p_idx]
            
            with st.form("plan_edit_form"):
                st.markdown("#### 📝 계획 내용 수정")
                e_date = st.date_input("날짜 변경", datetime.datetime.strptime(str(p_row['날짜']), "%Y-%m-%d").date())
                e_type = st.text_input("운동종류 변경", value=str(p_row['운동종류']))
                e_target = st.text_input("목표량 변경", value=str(p_row['목표량']))
                e_status = st.selectbox("상태 변경", ["⏳ 대기", "✅ 완료", "⚠️ 미달성"], index=["⏳ 대기", "✅ 완료", "⚠️ 미달성"].index(str(p_row['상태'])) if str(p_row['상태']) in ["⏳ 대기", "✅ 완료", "⚠️ 미달성"] else 0)
                
                if st.form_submit_button("💾 계획 수정 내용 저장", use_container_width=True):
                    update_sheet_row(0, int(edit_p_idx), [str(e_date), e_type, e_target, e_status])
                    st.cache_data.clear()
                    st.success("계획 정보가 수정되었습니다!")
                    st.rerun()
            
            st.markdown("---")
            if st.button("❌ 선택한 계획 완전 삭제", use_container_width=True):
                delete_sheet_row(0, int(edit_p_idx))
                st.cache_data.clear()
                st.success("해당 계획이 구글 시트에서 삭제되었습니다.")
                st.rerun()
        else:
            st.info("관리할 운동 계획 데이터가 없습니다.")
            
    elif manage_target == "📋 운동 기록 관리":
        if not record_df.empty:
            record_options = record_df.apply(lambda r: f"[{r['날짜']}] {r['운동종류']} (수행량: {r['실제수행량']})", axis=1)
            edit_r_idx = st.selectbox("수정/삭제할 기록 선택", options=record_options.index, format_func=lambda x: record_options[x], key="edit_r_select")
            r_row = record_df.loc[edit_r_idx]
            
            with st.form("record_edit_form"):
                st.markdown("#### 📝 기록 내용 수정")
                er_date = st.date_input("기록 날짜 변경", datetime.datetime.strptime(str(r_row['날짜']), "%Y-%m-%d").date())
                er_type = st.text_input("운동종류 변경", value=str(r_row['운동종류']))
                er_actual = st.text_input("실제 수행량 변경", value=str(r_row['실제수행량']))
                er_status = st.selectbox("달성여부 변경", ["✅ 완료", "⚠️ 미달성"], index=["✅ 완료", "⚠️ 미달성"].index(str(r_row['달성여부'])) if str(r_row['달성여부']) in ["✅ 완료", "⚠️ 미달성"] else 0)
                
                if st.form_submit_button("💾 기록 수정 내용 저장", use_container_width=True):
                    update_sheet_row(1, int(edit_r_idx), [str(er_date), er_type, er_actual, er_status, str(r_row['입력일시'])])
                    st.cache_data.clear()
                    st.success("운동 기록 정보가 수정되었습니다!")
                    st.rerun()
            
            st.markdown("---")
            if st.button("❌ 선택한 기록 완전 삭제", use_container_width=True):
                delete_sheet_row(1, int(edit_r_idx))
                st.cache_data.clear()
                st.success("해당 기록이 구글 시트에서 삭제되었습니다.")
                st.rerun()
        else:
            st.info("관리할 운동 기록 데이터가 없습니다.")