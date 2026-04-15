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

def get_unit_data(s_code, b_code, bun, ji, api_key):
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
        return response.text, response.status_code
    except Exception as e:
        return str(e), 500

def parse_units(xml_data, target_dong):
    if not xml_data: return [], "데이터가 비어있습니다."
    try:
        root = ET.fromstring(xml_data)
        
        # 공공데이터 API 자체 에러 체크 (200 OK 내부에 에러 메시지가 있는 경우)
        header_code = root.findtext(".//resultCode")
        header_msg = root.findtext(".//resultMsg")
        if header_code and header_code != "00":
            return [], f"API 에러: {header_msg} ({header_code})"
            
        items = []
        for i in root.findall(".//item"):
            d = i.findtext('dongNm', '')
            # 동 명칭 매칭 (입력값이 데이터에 포함되거나 그 반대인 경우)
            # 예: '101' vs '0101동' 매칭 성공
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

# --- UI 세팅 ---
st.set_page_config(page_title="매물 호수 식별 시스템", page_icon="🏢", layout="centered")

# 사이드바 설정
with st.sidebar:
    st.header("🔑 API 설정")
    input_api_key = st.text_input("공공데이터 인증키 (Decoding)", value=API_KEY, type="password")
    if input_api_key: API_KEY = input_api_key
    
    input_vworld_key = st.text_input("Vworld 인증키", value=VWORLD_KEY, type="password")
    if input_vworld_key: VWORLD_KEY = input_vworld_key
    
    st.divider()
    st.info("💡 API 응답이 200인데 데이터가 안 나오면 인증키(Decoding)가 정확한지 다시 확인하세요.")

st.title("🏢 매물 호수 자동 식별기")
st.markdown("---")

# 메인 입력 섹션
with st.container():
    addr_input = st.text_input("📍 주소 검색 (단지만 나오도록 입력)", placeholder="예: 삼성동 아이파크 (동/호수 제외)")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        dong = st.text_input("🏘️ 동 (숫자만)", placeholder="101")
    with col2:
        floor = st.text_input("🪜 층", placeholder="5")
    with col3:
        area = st.number_input("📐 전용면적 (㎡)", value=84.93, step=0.01, format="%.2f")

# 실행 버튼
if st.button("🔍 정확한 호수 확인하기", use_container_width=True, type="primary"):
    if not API_KEY or not VWORLD_KEY:
        st.warning("⚠️ API 키를 설정해주세요.")
    elif not addr_input or not dong:
        st.error("❌ 주소와 동 정보를 입력해주세요.")
    else:
        with st.status("분석 중...", expanded=True) as status:
            # 1. 주소 -> 코드 변환
            s_code, b_code, bun, ji = search_address_to_codes(addr_input, VWORLD_KEY)
            
            if s_code:
                st.write(f"✅ 주소 인식: {s_code}{b_code} (번지:{bun}-{ji})")
                
                # 2. 건축물대장 API 호출
                xml_raw, status_code = get_unit_data(s_code, b_code, bun, ji, API_KEY)
                
                if status_code == 200:
                    units, msg = parse_units(xml_raw, dong)
                    
                    if units:
                        df = pd.DataFrame(units)
                        # 필터링 
                        df_filtered = df[df['층'].str.contains(floor) if floor else True]
                        df_final = df_filtered[abs(df_filtered['면적'] - area) < 0.1]
                        
                        if not df_final.empty:
                            status.update(label="🎯 매칭 성공!", state="complete", expanded=False)
                            st.balloons()
                            st.success(f"### 🎉 총 {len(df_final)}개의 후보 발견")
                            for _, row in df_final.iterrows():
                                st.info(f"**{row['동']} {row['호']}** (층: {row['층']} / 면적: {row['면적']}㎡)")
                        else:
                            status.update(label="❌ 면적/층 불일치", state="error")
                            st.error(f"입력하신 조건(층:{floor}, 면적:{area}㎡)과 맞는 호수가 없습니다.")
                            with st.expander("데이터베이스에 있는 해당 동 전체 호수 목록"):
                                st.dataframe(df)
                    else:
                        status.update(label="❌ 데이터 없음", state="error")
                        st.error(f"결과가 없습니다: {msg}")
                        with st.expander("국토부 서버 응답 원문 (Debug)"):
                            st.code(xml_raw)
                else:
                    status.update(label="❌ 통신 실패", state="error")
                    st.error(f"서버 응답 오류 (코드: {status_code})")
                    st.code(xml_raw)
            else:
                status.update(label="❌ 주소 인식 실패", state="error")
                st.error("Vworld에서 주소를 찾지 못했습니다. 주소를 더 간단하게 입력해 보세요.")
