import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import os
from dotenv import load_dotenv
from utils import search_address_to_codes

# .env 파일에서 API 키 로드
load_dotenv()
API_KEY = os.getenv("DATA_GO_KR_API_KEY", "")
VWORLD_KEY = os.getenv("VWORLD_API_KEY", "")

BR_EXCT_HABIT_PD_URL = "http://apis.data.go.kr/1613000/BldRgstService_v2/getBrExctHabitPdInfo"

def get_unit_data(s_code, b_code, bun, ji, api_key):
    params = {
        'serviceKey': api_key,
        'sigunguCd': s_code,
        'bjdongCd': b_code,
        'bun': bun.zfill(4) if bun else "0000",
        'ji': ji.zfill(4) if ji else "0000",
        'numOfRows': 2000,
        'pageNo': 1
    }
    try:
        response = requests.get(BR_EXCT_HABIT_PD_URL, params=params, timeout=15)
        return response.text, response.status_code
    except Exception as e:
        return str(e), 500

def parse_units(xml_data, target_dong):
    if not xml_data: return [], "데이터가 비어있습니다."
    try:
        root = ET.fromstring(xml_data)
        header_code = root.findtext(".//resultCode")
        header_msg = root.findtext(".//resultMsg")
        if header_code and header_code != "00":
            return [], f"API 에러: {header_msg} ({header_code})"
            
        items = []
        for i in root.findall(".//item"):
            d = i.findtext('dongNm', '')
            clean_target = "".join(filter(str.isdigit, target_dong))
            clean_dong = "".join(filter(str.isdigit, d))
            
            if not target_dong or (clean_target and clean_target in clean_dong) or target_dong in d:
                items.append({
                    '동': d,
                    '호': i.findtext('hoNm', ''),
                    '층': i.findtext('flrNm', ''),
                    '면적': float(i.findtext('exposPubuseArea', '0'))
                })
        return items, "성공"
    except Exception as e:
        return [], f"XML 파싱 에러: {e}"

st.set_page_config(page_title="매물 호수 식별 시스템", page_icon="🏢", layout="centered")

with st.sidebar:
    st.header("🔑 API 설정")
    input_api_key = st.text_input("공공데이터 인증키 (Decoding)", value=API_KEY, type="password")
    if input_api_key: API_KEY = input_api_key
    input_vworld_key = st.text_input("Vworld 인증키", value=VWORLD_KEY, type="password")
    if input_vworld_key: VWORLD_KEY = input_vworld_key
    
    st.divider()
    manual_mode = st.checkbox("⚙️ 코드 직접 입력 모드 (비상용)")

st.title("🏢 매물 호수 자동 식별기")
st.markdown("---")

if not manual_mode:
    addr_input = st.text_input("📍 주소 검색", placeholder="예: 삼성동 아이파크 (단지까지만 입력)")
    s_code, b_code, bun, ji = None, None, "0", "0"
else:
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        s_code = st.text_input("시군구코드 (5자리)", value="11680")
        b_code = st.text_input("법정동코드 (5자리)", value="10100")
    with col_m2:
        bun = st.text_input("번지", value="0")
        ji = st.text_input("호", value="0")
    addr_input = "수동 입력 모드"

col1, col2, col3 = st.columns(3)
with col1:
    dong = st.text_input("🏘️ 동 (숫자만)", placeholder="101")
with col2:
    floor = st.text_input("🪜 층", placeholder="5")
with col3:
    area = st.number_input("📐 전용면적 (㎡)", value=84.93, step=0.01, format="%.2f")

if st.button("🔍 정확한 호수 확인하기", use_container_width=True, type="primary"):
    if not API_KEY:
        st.error("⚠️ 공공데이터 인증키가 필요합니다.")
    else:
        with st.status("분석 중...", expanded=True) as status:
            if not manual_mode:
                st.write("🔍 주소 코드를 분석하고 있습니다...")
                s_code, b_code, bun, ji, v_msg = search_address_to_codes(addr_input, VWORLD_KEY)
            else:
                v_msg = "성공"

            if s_code:
                st.write(f"✅ 주소 인식: {s_code}{b_code} (번지:{bun}-{ji})")
                xml_raw, status_code = get_unit_data(s_code, b_code, bun, ji, API_KEY)
                
                if status_code == 200:
                    units, msg = parse_units(xml_raw, dong)
                    if units:
                        df = pd.DataFrame(units)
                        df_filtered = df[df['층'].str.contains(floor) if floor else True]
                        df_final = df_filtered[abs(df_filtered['면적'] - area) < 0.1]
                        
                        if not df_final.empty:
                            status.update(label="🎯 매칭 성공!", state="complete", expanded=False)
                            st.balloons()
                            st.success(f"### 🎉 총 {len(df_final)}개의 후보 발견")
                            for _, row in df_final.iterrows():
                                st.info(f"**{row['동']} {row['호']}** (층: {row['층']} / 면적: {row['면적']}㎡)")
                        else:
                            status.update(label="❌ 일치하는 호수 없음", state="error")
                            st.error("조건에 맞는 호수가 없습니다.")
                            with st.expander("동 전체 데이터 확인"):
                                st.dataframe(df)
                    else:
                        status.update(label="❌ 데이터 없음", state="error")
                        st.error(f"결과가 없습니다: {msg}")
                        with st.expander("서버 응답 원문"):
                            st.code(xml_raw)
                else:
                    status.update(label="❌ 서버 오류", state="error")
                    st.error(f"코드: {status_code}")
                    st.code(xml_raw)
            else:
                status.update(label="❌ 주소 인식 실패", state="error")
                st.error(v_msg)
                st.info("💡 사이드바의 '코드 직접 입력 모드'를 사용해 보세요.")
