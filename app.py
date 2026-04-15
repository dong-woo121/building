import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import os
from dotenv import load_dotenv
from utils import search_address_to_codes

# .env 파일에서 API 키 로드 (로컬용)
load_dotenv()
API_KEY = os.getenv("DATA_GO_KR_API_KEY", "")
VWORLD_KEY = os.getenv("VWORLD_API_KEY", "")

# 국토교통부 건축물대장 API URL
BR_EXCT_HABIT_PD_URL = "http://apis.data.go.kr/1613000/BldRgstService_v2/getBrExctHabitPdInfo"

def get_unit_data(s_code, b_code, bun, ji, dong_nm, api_key):
    """건축물대장 API 호출"""
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
        if response.status_code == 200:
            return response.text
        return None
    except:
        return None

def parse_units(xml_data, target_dong):
    if not xml_data: return []
    try:
        root = ET.fromstring(xml_data)
        return [{
            '동': i.findtext('dongNm', ''),
            '호': i.findtext('hoNm', ''),
            '층': i.findtext('flrNm', ''),
            '면적': float(i.findtext('exposPubuseArea', '0'))
        } for i in root.findall(".//item") if target_dong in i.findtext('dongNm', '')]
    except: return []

# --- UI 세팅 ---
st.set_page_config(page_title="Unit Matcher - KING GEMINI", page_icon="🏢", layout="centered")

# 사이드바 설정 (API 키 입력)
with st.sidebar:
    st.header("🔑 API 설정")
    st.caption("서비스 이용을 위해 아래 키를 입력해주세요.")
    
    # 1. 공공데이터포털 인증키
    input_api_key = st.text_input("공공데이터 인증키 (Decoding)", value=API_KEY, type="password", help="data.go.kr에서 발급받은 건축물대장 API 키")
    if input_api_key: API_KEY = input_api_key
    
    # 2. Vworld 인증키 (주소 검색용)
    input_vworld_key = st.text_input("Vworld 인증키", value=VWORLD_KEY, type="password", help="vworld.kr에서 발급받은 API 키 (주소 검색용)")
    if input_vworld_key: VWORLD_KEY = input_vworld_key
    
    st.divider()
    st.markdown("### 📖 사용 가이드")
    st.markdown("""
    1. **주소**에 아파트명이나 지번을 입력하세요.
    2. **동/층/면적** 정보를 입력합니다.
    3. **정답 확인** 버튼을 누르면 끝!
    """)

st.title("🏢 매물 호수 자동 식별 시스템")
st.subheader("KING GEMINI Edition v1.0")
st.markdown("---")

# 메인 입력 섹션
with st.container():
    addr_input = st.text_input("📍 주소 검색", placeholder="예: 강남구 삼성동 101-1 또는 삼성동 아이파크")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        dong = st.text_input("🏘️ 동 (예: 101)", placeholder="101")
    with col2:
        floor = st.text_input("🪜 층 (예: 5)", placeholder="5")
    with col3:
        area = st.number_input("📐 전용면적 (㎡)", value=84.93, step=0.01, format="%.2f")

# 실행 버튼
if st.button("✨ 정확한 호수 찾아내기", use_container_width=True, type="primary"):
    if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
        st.warning("⚠️ 왼쪽 사이드바에 '공공데이터 인증키'를 입력해주세요.")
    elif not VWORLD_KEY:
        st.warning("⚠️ 왼쪽 사이드바에 'Vworld 인증키'를 입력해주세요. (주소 검색용)")
    elif not addr_input or not dong:
        st.error("❌ 주소와 동 정보를 입력해주세요.")
    else:
        with st.status("💎 KING GEMINI 분석 엔진 가동 중...", expanded=True) as status:
            # 1. 주소 -> 코드 변환
            st.write("🔍 주소 코드를 분석하고 있습니다...")
            s_code, b_code, bun, ji = search_address_to_codes(addr_input, VWORLD_KEY)
            
            if s_code:
                st.write(f"✅ 주소 인식 완료 (코드: {s_code}{b_code})")
                st.write("🏢 건축물대장 데이터를 대조 중입니다...")
                
                # 2. 건축물대장 API 호출
                xml_res = get_unit_data(s_code, b_code, bun, ji, dong, API_KEY)
                units = parse_units(xml_res, dong)
                
                if units:
                    df = pd.DataFrame(units)
                    # 필터링 
                    df_filtered = df[df['층'].str.contains(floor) if floor else True]
                    df_final = df_filtered[abs(df_filtered['면적'] - area) < 0.1]
                    
                    if not df_final.empty:
                        status.update(label="🎯 매칭 성공!", state="complete", expanded=False)
                        st.balloons()
                        st.success(f"### 🎉 총 {len(df_final)}개의 후보 호수를 찾았습니다!")
                        
                        for _, row in df_final.iterrows():
                            with st.chat_message("assistant", avatar="🏠"):
                                st.write(f"추정 호수: **{row['동']} {row['hoNm'] if 'hoNm' in row else row['호']}**")
                                st.caption(f"층: {row['층']} / 정확한 면적: {row['면적']}㎡")
                    else:
                        status.update(label="❌ 면적 불일치", state="error")
                        st.error(f"입력하신 면적({area}㎡)과 일치하는 호수가 해당 층에 없습니다.")
                        with st.expander("해당 동의 전체 호수 데이터 보기"):
                            st.dataframe(df)
                else:
                    status.update(label="❌ 데이터 없음", state="error")
                    st.error("해당 주소/동의 데이터를 찾을 수 없습니다. (번지수나 동 명칭을 확인하세요)")
            else:
                status.update(label="❌ 주소 인식 실패", state="error")
                st.error("정확한 주소를 입력해주세요. (Vworld API 키 확인 필요)")

st.divider()
st.caption("Powered by Public Data Portal & Vworld API")
