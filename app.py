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
KAKAO_KEY = os.getenv("KAKAO_API_KEY", "")

BR_EXCT_HABIT_PD_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo"

def get_unit_data(s_code, b_code, bun, ji, api_key):
    decoded_key = urllib.parse.unquote(api_key)
    base_params = {
        'serviceKey': decoded_key,
        'sigunguCd': s_code,
        'bjdongCd': b_code,
        'bun': bun.zfill(4),
        'ji': ji.zfill(4),
        'numOfRows': 2000,
        'pageNo': 1
    }
    try:
        r = requests.get(BR_EXCT_HABIT_PD_URL, params=base_params, timeout=15)
        if r.status_code != 200:
            return r.text, r.status_code

        # totalCount 파악 후 페이지네이션
        root = ET.fromstring(r.text)
        total = int(root.findtext('.//totalCount') or '0')
        all_xml = r.text

        if total > 2000:
            pages = (total // 2000) + 1
            for page in range(2, pages + 1):
                base_params['pageNo'] = page
                r2 = requests.get(BR_EXCT_HABIT_PD_URL, params=base_params, timeout=15)
                root2 = ET.fromstring(r2.text)
                for item in root2.findall('.//item'):
                    ET.SubElement(root.find('.//items'), 'item').extend(list(item))
            all_xml = ET.tostring(root, encoding='unicode')

        return all_xml, 200
    except Exception as e:
        return f"통신 오류: {str(e)}", 500

def parse_units(xml_data, target_dong):
    if not xml_data: return [], "서버 응답이 비어있습니다."
    try:
        if not xml_data.strip().startswith("<"):
            return [], f"데이터 형식 오류: {xml_data[:100]}"
            
        root = ET.fromstring(xml_data)
        header_code = root.findtext(".//resultCode")
        header_msg = root.findtext(".//resultMsg")
        
        if header_code and header_code not in ["00", "0"]:
            return [], f"API 에러: {header_msg} ({header_code})"
            
        items = []
        for i in root.findall(".//item"):
            # 공용면적 제외, 전유(1)만
            if i.findtext('exposPubuseGbCd', '') != '1':
                continue
            d = i.findtext('dongNm', '')
            clean_target = "".join(filter(str.isdigit, target_dong)) if target_dong else ""
            clean_dong = "".join(filter(str.isdigit, d))

            if not target_dong or (clean_target and clean_target in clean_dong) or target_dong in d:
                items.append({
                    '동': d,
                    '호': i.findtext('hoNm', ''),
                    '층': i.findtext('flrNoNm', ''),
                    '면적': float(i.findtext('area', '0') or '0')
                })
        return items, "성공"
    except Exception as e:
        return [], f"XML 분석 실패: {str(e)}"

st.set_page_config(page_title="매물 호수 식별기", page_icon="🏢", layout="centered")

with st.sidebar:
    st.header("🔑 API 설정")
    input_api_key = st.text_input("공공데이터 인증키 (Decoding)", value=API_KEY, type="password")
    if input_api_key: API_KEY = input_api_key
    input_kakao_key = st.text_input("Kakao REST API 키", value=KAKAO_KEY, type="password")
    if input_kakao_key: KAKAO_KEY = input_kakao_key
    
    st.divider()
    manual_mode = st.checkbox("⚙️ 코드 직접 입력 모드")

st.title("🏢 매물 호수 자동 식별기")
st.markdown("---")

if not manual_mode:
    addr_input = st.text_input("📍 주소 검색 (아파트명 입력)", placeholder="예: 광명역 파크자이")
    s_code, b_code, bun, ji = None, None, "0", "0"
else:
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        s_code = st.text_input("시군구코드", value="41210")
        b_code = st.text_input("법정동코드", value="11000")
    with col_m2:
        bun = st.text_input("번지", value="518")
        ji = st.text_input("호", value="0")
    addr_input = "수동 입력 모드"

col1, col2, col3 = st.columns(3)
with col1:
    dong = st.text_input("🏘️ 동", placeholder="101")
with col2:
    floor = st.text_input("🪜 층", placeholder="5")
with col3:
    area = st.number_input("📐 전용면적 (㎡)", value=84.93, step=0.01, format="%.2f")

if st.button("🔍 정확한 호수 확인하기", use_container_width=True, type="primary"):
    try:
        if not API_KEY or not KAKAO_KEY:
            st.error("⚠️ 사이드바에 API 키를 모두 입력해주세요.")
        else:
            with st.status("분석 중...", expanded=True) as status:
                if not manual_mode:
                    st.write("1. 주소 및 지번 분석 중...")
                    s_code, b_code, bun, ji, v_msg = search_address_to_codes(addr_input, KAKAO_KEY)
                else:
                    v_msg = "성공"

                if s_code:
                    st.write(f"✅ 주소 파악 완료: {s_code}{b_code} (지번: {bun}-{ji})")
                    st.write("2. 국토부 서버에서 건축물대장을 가져오고 있습니다...")
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
                                st.error("조건에 맞는 호수가 없습니다. 면적이나 층을 확인하세요.")
                                with st.expander("동 전체 호수 보기"):
                                    st.dataframe(df)
                                with st.expander("원본 XML (필드명 확인용)"):
                                    st.code(xml_raw[:3000])
                        else:
                            status.update(label="❌ 데이터 없음", state="error")
                            st.error(f"결과 없음: {msg}")
                            with st.expander("원본 로그"):
                                st.code(xml_raw)
                    else:
                        status.update(label="❌ 서버 응답 오류", state="error")
                        st.error(f"상태 코드: {status_code}")
                        st.write("**요청 파라미터:**")
                        import urllib.parse as up
                        dk = up.unquote(API_KEY)
                        st.code(f"sigunguCd={s_code}\nbjdongCd={b_code}\nbun={bun.zfill(4)}\nji={ji.zfill(4)}\nserviceKey={dk[:10]}...({len(dk)}자)")
                        st.write("**서버 응답:**")
                        st.code(xml_raw[:2000] if xml_raw else "(응답 없음)")
                else:
                    status.update(label="❌ 주소 인식 실패", state="error")
                    st.error(v_msg)
    except Exception as e:
        st.error(f"시스템 에러: {str(e)}")
        st.code(traceback.format_exc())
