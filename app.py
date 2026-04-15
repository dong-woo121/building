import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import os
import traceback
from dotenv import load_dotenv
from utils import search_address_to_codes

load_dotenv()
API_KEY = os.getenv("DATA_GO_KR_API_KEY", "")
VWORLD_KEY = os.getenv("VWORLD_API_KEY", "")

# 인코딩 문제 방지를 위해 URL과 파라미터를 분리하여 처리
BR_EXCT_HABIT_PD_URL = "http://apis.data.go.kr/1613000/BldRgstService_v2/getBrExctHabitPdInfo"

def get_unit_data(s_code, b_code, bun, ji, api_key):
    # 인코딩된 키와 디코딩된 키 이슈를 해결하기 위해 requests.get의 params 대신 URL에 직접 붙임
    url = f"{BR_EXCT_HABIT_PD_URL}?serviceKey={api_key}&sigunguCd={s_code}&bjdongCd={b_code}&bun={bun.zfill(4)}&ji={ji.zfill(4)}&numOfRows=2000&pageNo=1"
    try:
        response = requests.get(url, timeout=15)
        return response.text, response.status_code
    except Exception as e:
        return str(e), 500

def parse_units(xml_data, target_dong):
    if not xml_data: return [], "데이터가 비어있습니다."
    try:
        # XML이 아닌 경우(에러 메시지 등) 처리
        if not xml_data.strip().startswith("<"):
            return [], f"서버가 XML이 아닌 응답을 보냈습니다: {xml_data[:100]}"
            
        root = ET.fromstring(xml_data)
        header_code = root.findtext(".//resultCode")
        header_msg = root.findtext(".//resultMsg")
        if header_code and header_code not in ["00", "0"]:
            return [], f"API 에러: {header_msg} ({header_code})"
            
        items = []
        for i in root.findall(".//item"):
            d = i.findtext('dongNm', '')
            clean_target = "".join(filter(str.isdigit, target_dong)) if target_dong else ""
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
        return [], f"XML 파싱 에러: {str(e)}\n{xml_data[:200]}"

st.set_page_config(page_title="매물 호수 식별 시스템", page_icon="🏢", layout="centered")

with st.sidebar:
    st.header("🔑 API 설정")
    # 공공데이터 키는 Decoding 키를 권장하지만, Encoding 키도 시도할 수 있도록 안내
    input_api_key = st.text_input("공공데이터 인증키 (Decoding 권장)", value=API_KEY, type="password")
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
        bun = st.text_input("번지", value="512")
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
    try:
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
    except Exception as outer_e:
        st.error(f"⚠️ 앱 내부 오류 발생: {str(outer_e)}")
        st.code(traceback.format_exc())
