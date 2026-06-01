import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==========================================
# 1. 구글 스프레드시트 연결 설정
# ==========================================
def connect_to_gsheet():
    # 사용자가 제공한 서비스 계정 정보
    credentials_info = {
        "type": "service_account",
        "project_id": "my7762",
        "private_key_id": "bc1e9ef24e430f9228436878ca392b0a507b174c",
        "private_key": """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDgf95Nex09t4jJ
IHkbgiMjr7r2/OgQGCBY8przwTVyNrAVeYOD+CUcV/FmuHRFCqigQbF21UMXeBQn
pM1yltnFUAqOGYvlZFrcMaoMJ3USQUbWwJkZ3iH4lBAhL/3MmeO/1Fgsk92b3axW
6hjsquHhXnCAYcunySloE33UfI/44w4To1kVnBra1cC0X9eG7JuF/Zjli9kraO9B
N9MpXtFWC37DBlTtBy/1VNIJ1ngj2ruHIWckE7SmADuB93Ax0PH7lK/6ibtRqu+W
D1IPjnco+8IgbI2wMpXWxM7StE3bQGMtCiGvQRR0E+hkzrXUrCwr1xp2hXFWuReY
7S0B2KxdAgMBAAECggEAAfYL/phHOp1KVBt1A2EBJpQn6XVvH4jea3h/EwcKjPte
UWm01OfLhzJbeP6+gUXlEDVStAuL4P4bCvedFdWshFU9Kl2dw7y7MHY8mouTsbuh
P0oCbF/s4wuEEo4lRO7JNwlHVehaxLxMf5ve6N5bR8k36V8xVL9knbSh4kPOTCnH
abntKyEZkA/QtdX1wgtVqlH06AsrDsKJ0eydsi18//kvU1au+FA45CK2IU+stxjC
UBQFvhHf5iOWrYGv7/ct3tnWsoLPLE7KBi1TB386kmG0l+eLu/YJBlFOXM1HQaxO
DT4u6dIIeiWk+vGrrxtQTXUhzs+vF9f09dr3wccV7wKBgQD7gP4qSmsCgAF5Amzo
zxr7z1IKdyoYokP7CcwD9R1OUMeOKpEPETdl/aJb1VxYdh3sDVmF7fDExBuArVT4
oWbOjecMzy8yhB4dSLFfl9I36FHZXenKoaesP584cJSD15FGRRnXtOrKflUdyDJl
ATxhLrwWhZZgFArSHE9BJP95PwKBgQDkg0o7g01nbhyZPAu1QYDRR372ZWe+VQHQ
6E1ZPufGyF5pitDNktag5GxctOZTNFg9U59EqeYjE4iySr7jCcRQlApm3qmZhOc5
KhvmBu9qk+90OZ36DfmXYORx5C9p5XkhIfbtMLDt/NhyQf4v1eWpG1FzT0niS9M/
+zIa7a/3YwKBgAtf5h7bhsNyLp7ecTaGR14kHj3C7fB3RkPQSZ3UNCManCvd2Pmp
eavvMKyelbKahPfsEqRwAnejtuq27CTih9fHqy91H1lViFcitoLwRt2ocCs4iB5V
+VNc/UJ8NPtRgIyBC44p7ISD+i2CpGTVDXoHtxH9sLNftK2UAjGcDsHZAoGBAIYv
YmPYEpft3PVOgUGKmW5LIY7mtSjbGhnmj6Ucf1YHSwmG7l4JH+eSut8liyrIzhgV
Bq13ZyCp09d+dOE1VwZKKGGH1ufDV1QGGiPVZrma7T2+p7mygyIVT5BhgkYY7iw6
mZlmwj69/wv5HJ5SaG4JEKc5pBUymXY0t5OAh5gpAoGBALaN+0X6eFmcaJWWpuJ1
7TEnaUnBV1jyv3bu8kKy6n7TafwIbaNkBVprWvEnZ+LVaua00lz1zTzx5NzFj+uF
Y+6K7/6ZiL/F75vLJZqSWQE4vNB/pDPYetP0weXFjSidd28twJjcUH43rjPNF90M
O+YfB8WIN1Q5lvh54Lp234yB
-----END PRIVATE KEY-----""",
        "client_email": "upup-440@my7762.iam.gserviceaccount.com",
        "client_id": "103668876041726168861",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/upup-440%40my7762.iam.gserviceaccount.com"
    }
    
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    try:
        creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
        client = gspread.authorize(creds)
        # 스프레드시트 ID 확인
        SPREADSHEET_ID = '1t1reQUHfw0K7BEzPcaxOaCtP8x--ATip7tGhGy11NTU'
        sheet = client.open_by_key(SPREADSHEET_ID).get_worksheet(0)
        return sheet
    except Exception as e:
        st.error(f"❌ 구글 시트 연결 실패: {e}")
        return None

# ==========================================
# 2. 웹 앱 UI 구성 (담당자 항목 추가)
# ==========================================
st.set_page_config(page_title="영업 이슈 등록 시스템", layout="centered")

st.title("🚀 영업 이슈 리포트")
st.write("현장에서 입력한 데이터가 실시간으로 스프레드시트에 기록됩니다.")
st.divider()

with st.form("issue_form", clear_on_submit=True):
    # 1. 담당자 선택 (온라인 컨설팅 추가됨)
    manager = st.radio(
        "담당자 선택", 
        ["이광호", "문정수", "박원덕", "온라인 컨설팅"], # 👈 여기에 추가되었습니다.
        horizontal=True
    )
    
    # 2. 방문업체명 입력
    company_name = st.text_input("방문 업체명", placeholder="예: OO세무회계, (주)디지털솔루션")

    # 3. 상품 다중 선택
    st.write("**가입(예정/실패) 상품**")
    products = st.multiselect(
        "해당하는 모든 상품을 선택하세요",
        ["위멤버스 프리미엄", "위멤버스 스탠다드", "세모리포트 플러스", "세모리포트 베이직", "링크패스", "경리나라T"]
    )

    # 4. 상세 내용 작성
    st.write("**상세 이슈**")
    issue_detail = st.text_area(
        label="상세 내용",
        placeholder="업체 피드백, 미팅 특이사항 등을 자유롭게 작성하세요.",
        height=150
    )

    # 제출 버튼
    submit_button = st.form_submit_button("이슈 등록 완료")

# ==========================================
# 3. 데이터 처리 로직
# ==========================================
if submit_button:
    if not company_name.strip():
        st.warning("방문 업체명을 입력해 주세요.")
    elif not products:
        st.warning("상품을 하나 이상 선택해 주세요.")
    elif not issue_detail.strip():
        st.warning("상세 이슈 내용을 입력해 주세요.")
    else:
        with st.spinner("데이터를 스프레드시트에 저장 중입니다..."):
            sheet = connect_to_gsheet()
            if sheet:
                try:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    product_str = ", ".join(products)
                    
                    # 시트 저장 데이터 [시간, 담당자, 업체명, 상품명, 상세내용]
                    row_data = [now, manager, company_name, product_str, issue_detail]
                    
                    sheet.append_row(row_data)
                    
                    st.success(f"✅ '{company_name}' 건이 성공적으로 저장되었습니다!")
                    st.balloons()
                except Exception as e:
                    st.error(f"저장 중 오류 발생: {e}")

st.divider()
st.caption("문의 사항: 시스템 관리자에게 연락 바랍니다.")