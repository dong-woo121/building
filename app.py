import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import os
import traceback
from dotenv import load_dotenv
from utils import search_address_to_codes
import urllib.parse

load_dotenv()
API_KEY = os.getenv("DATA_GO_KR_API_KEY", "")
VWORLD_KEY = os.getenv("VWORLD_API_KEY", "")

BR_EXCT_HABIT_PD_URL = "http://apis.data.go.kr/1613000/BldRgstService_v2/getBrExctHabitPdInfo"

def get_unit_data(s_code, b_code, bun, ji, api_key):
    # 공공데이터포털 특유의 인증키 이슈(이미 인코딩된 경우)를 처리하기 위해 unquote 후 다시 처리
    decoded_key = urllib.parse.unquote(api_key)
    
    params = {
        'serviceKey': decoded_key,
        'sigunguCd': s_code,
        'bjdongCd': b_code,
        'bun': bun.zfill(4),
        'ji': ji.zfill(4),
        'numOfRows': 2000,
        'pageNo': 1
    }
    
    try:
        # params를 사용하면 requests가 알아서 안전하게 인코딩합니다.
        response = requests.get(BR_EXCT_HABIT_PD_URL, params=params, timeout=15)
        return response.text, response.status_code
    except Exception as e:
        return f"통신 오류: {str(e)}", 500

def parse_units(xml_data, target_dong):
    if not xml_data: return [], "서버 응답이 비어있습니다."
    try:
        if not xml_data.strip().startswith("<"):
            return [], f"서버가 XML이 아닌 응답을 보냈습니다 (첫 100자): {xml_data[:100]}"
            
        root = ET.fromstring(xml_data)
        header_code = root.findtext(".//resultCode")
        header_msg = root.findtext(".//resultMsg")
        
        if header_code and header_code not in ["00", "0"]:
            return [], f"API 에러메시지: {header_msg} (코드: {header_code})"
            
        items = []
        for i in root.findall(".//item"):
            d = i.findtext('dongNm', '')
            clean_target = "".join(filter(str.isdigit, target_dong)) if target_dong else ""
            clean_dong = "".join(filter(str.isdigit, d))
            
            # 동 매칭 조건 완화
            if not target_dong or (clean_target and clean_target in clean_dong) or target_dong in d:
                items.append({
                    '동': d,
                    '호': i.findtext('hoNm', ''),
                    '층': i.findtext('flrNm', ''),
                    '면적': float(i.findtext('exposPubuseArea', '0'))
                })
        return items, "성공"
    except Exception as e:
        return [], f"데이터 분석(XML) 중 오류: {str(e)}"

st.set_page_config(page_title="매물 호수 식별기", page_icon="🏢", layout="centered")

with st.sidebar:
    st.header("🔑 API 설정")
    # '디코딩된' 키 입력을 강력 권장
    input_api_key = st.text_input("공공데이터 인증키 (Decoding 필수)", value=API_KEY, type="password")
    if input_api_key: API_KEY = input_api_key
    input_vworld_key = st.text_input("Vworld 인증키", value=VWORLD_KEY, type="password")
    if input_vworld_key: VWORLD_KEY = input_vworld_key
    
    st.divider()
    manual_mode = st.checkbox("⚙️ 코드 직접 입력 모드 (비상용)")

st.title("🏢 매물 호수 자동 식별기")
st.markdown("---")

if not manual_mode:
    addr_input = st.text_input("📍 주소 검색", placeholder="예: 광명역 파크자이")
    s_code, b_code, bun, ji = None, None, "0", "0"
else:
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        s_code = st.text_input("시군구코드 (5자리)", value="41210")
        b_code = st.text_input("법정동코드 (5자리)", value="11000")
    with col_m2:
        bun = st.text_input("번지 (숫자만)", value="512")
        ji = st.text_input("호 (숫자만)", value="0")
    addr_input = "수동 입력 모드"

col1, col2, col3 = st.columns(3)
with col1:
    dong = st.text_input("🏘️ 동 (예: 101)", placeholder="101")
with col2:
    floor = st.text_input("🪜 층 (예: 5)", placeholder="5")
with col3:
    area = st.number_input("📐 전용면적 (㎡)", value=84.93, step=0.01, format="%.2f")

if st.button("🔍 정확한 호수 확인하기", use_container_width=True, type="primary"):
    try:
        if not API_KEY:
            st.error("⚠️ 사이드바에 공공데이터 인증키를 먼저 넣어주세요.")
        else:
            with st.status("💎 분석 진행 중...", expanded=True) as status:
                if not manual_mode:
                    st.write("1. 주소 코드를 분석하고 있습니다...")
                    s_code, b_code, bun, ji, v_msg = search_address_to_codes(addr_input, VWORLD_KEY)
                else:
                    v_msg = "성공"

                if s_code:
                    st.write(f"✅ 주소 코드 획득: {s_code}{b_code} (지번: {bun}-{ji})")
                    st.write("2. 국토부 서버에서 건축물대장을 가져오고 있습니다...")
                    xml_raw, status_code = get_unit_data(s_code, b_code, bun, ji, API_KEY)
                    
                    if status_code == 200:
                        units, msg = parse_units(xml_raw, dong)
                        if units:
                            df = pd.DataFrame(units)
                            # 층 필터링
                            df_filtered = df[df['층'].str.contains(floor) if floor else True]
                            # 면적 필터링 (오차 0.1㎡)
                            df_final = df_filtered[abs(df_filtered['면적'] - area) < 0.1]
                            
                            if not df_final.empty:
                                status.update(label="🎯 매칭 완료!", state="complete", expanded=False)
                                st.balloons()
                                st.success(f"### 🎉 총 {len(df_final)}개의 후보 호수 발견")
                                for _, row in df_final.iterrows():
                                    st.info(f"**{row['동']} {row['호']}** (정보: {row['층']} / 면적: {row['면적']}㎡)")
                            else:
                                status.update(label="❌ 면적/층 불일치", state="error")
                                st.error(f"입력한 조건(층:{floor}, 면적:{area}㎡)과 일치하는 호수가 없습니다.")
                                with st.expander("가장 비슷한 면적의 호수들 보기"):
                                    st.dataframe(df.sort_values(by='면적'))
                        else:
                            status.update(label="❌ 데이터 필터링 실패", state="error")
                            st.error(f"해당 동({dong})의 데이터를 찾지 못했습니다: {msg}")
                            with st.expander("국토부 응답 원문 (Debug)"):
                                st.code(xml_raw)
                    else:
                        status.update(label="❌ 국토부 서버 응답 오류", state="error")
                        st.error(f"에러 코드: {status_code}")
                        st.code(xml_raw)
                else:
                    status.update(label="❌ 주소 인식 실패", state="error")
                    st.error(v_msg)
    except Exception as e:
        st.error(f"⚠️ 앱 구동 중 예상치 못한 오류 발생: {str(e)}")
        st.code(traceback.format_exc())
