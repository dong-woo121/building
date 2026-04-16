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

BR_EXPOS_INFO_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposInfo"
BR_AREA_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo"

def _norm(s):
    return "".join(s.split()).lower()

def _fetch_all_items(url, base_params):
    import math
    try:
        r = requests.get(url, params=base_params, timeout=15)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
        code = root.findtext('.//resultCode', '')
        if code not in ('00', '0', ''):
            return []
        total = int(root.findtext('.//totalCount') or '0')
        items = list(root.findall('.//item'))
        for page in range(2, math.ceil(total / 1000) + 1):
            p = {**base_params, 'pageNo': page}
            r2 = requests.get(url, params=p, timeout=15)
            items += list(ET.fromstring(r2.text).findall('.//item'))
        return items
    except Exception:
        return []

def get_unit_data(s_code, b_code, bun, ji, api_key, bld_name=None):
    decoded_key = urllib.parse.unquote(api_key)
    base = {
        'serviceKey': decoded_key,
        'sigunguCd': s_code,
        'bjdongCd': b_code,
        'bun': bun.zfill(4) if bun else '0000',
        'ji': ji.zfill(4) if ji else '0000',
        'numOfRows': 1000,
        'pageNo': 1,
    }
    bld_tokens = [_norm(t) for t in (bld_name or '').split() if len(t) > 1]

    def bld_ok(item):
        if not bld_tokens:
            return True
        return any(t in _norm(item.findtext('bldNm', '')) for t in bld_tokens)

    # 1) 전유부 목록 (동, 호, 층번호)
    unit_items = [i for i in _fetch_all_items(BR_EXPOS_INFO_URL, base) if bld_ok(i)]

    # 2) 면적 데이터 (전유 only)
    area_items = [i for i in _fetch_all_items(BR_AREA_URL, base)
                  if i.findtext('exposPubuseGbCd', '') == '1' and bld_ok(i)]
    area_map = {}
    for i in area_items:
        key = (i.findtext('dongNm', ''), i.findtext('hoNm', ''))
        try:
            area_map[key] = float(i.findtext('area', '0') or '0')
        except ValueError:
            pass

    if not unit_items:
        return [], "데이터 없음: API에서 해당 건물 정보를 찾을 수 없습니다."

    units = []
    for i in unit_items:
        dong = i.findtext('dongNm', '')
        ho = i.findtext('hoNm', '')
        try:
            flr_int = int(i.findtext('flrNo', '0') or '0')
            flr_str = f"{flr_int}층" if flr_int > 0 else (f"지{abs(flr_int)}층" if flr_int < 0 else "")
        except ValueError:
            flr_str = i.findtext('flrNo', '')
        area = area_map.get((dong, ho), 0.0)
        units.append({'동': dong, '호': ho, '층': flr_str, '면적': area})

    return units, "성공"

st.set_page_config(page_title="매물 호수 식별기", page_icon="🏢", layout="centered")

with st.sidebar:
    st.header("🔑 API 설정")
    st.success("공공데이터 키 로드됨" if API_KEY else "공공데이터 키 없음")
    st.success("Kakao 키 로드됨" if KAKAO_KEY else "Kakao 키 없음")

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
                    st.write(f"✅ 주소 파악 완료: {s_code}{b_code}")
                    st.write("2. 국토부 서버에서 건축물대장을 가져오고 있습니다...")
                    units, msg = get_unit_data(
                        s_code, b_code, bun, ji, API_KEY,
                        bld_name=addr_input if not manual_mode else None
                    )

                    if units:
                        df = pd.DataFrame(units)
                        # 동 필터
                        dong_digits = "".join(filter(str.isdigit, dong)) if dong else ""
                        if dong_digits:
                            df = df[df['동'].apply(lambda d: dong_digits in "".join(filter(str.isdigit, d)))]
                        # 층 필터 (정확히 일치: "5" → "5층"만, "15층"/"25층" 제외)
                        df_floor = df[df['층'] == f"{floor}층"] if floor else df
                        # 면적 필터 (면적 데이터가 있을 때만)
                        has_area = df_floor['면적'].max() > 0
                        df_final = df_floor[abs(df_floor['면적'] - area) < 0.1] if has_area else df_floor

                        if not df_final.empty:
                            status.update(label="🎯 매칭 성공!", state="complete", expanded=False)
                            st.balloons()
                            st.success(f"### 🎉 총 {len(df_final)}개의 후보 발견")
                            for _, row in df_final.iterrows():
                                st.info(f"**{row['동']} {row['호']}** (층: {row['층']} / 면적: {row['면적']}㎡)")
                            if not has_area:
                                st.warning("⚠️ 면적 데이터 없음 — 층만으로 필터링한 결과입니다.")
                        else:
                            status.update(label="❌ 일치하는 호수 없음", state="error")
                            st.error("조건에 맞는 호수가 없습니다. 면적이나 층을 확인하세요.")
                            with st.expander("동 전체 호수 보기"):
                                st.dataframe(df.reset_index(drop=True))
                    else:
                        status.update(label="❌ 데이터 없음", state="error")
                        st.error(f"결과 없음: {msg}")
                else:
                    status.update(label="❌ 주소 인식 실패", state="error")
                    st.error(v_msg)
    except Exception as e:
        st.error(f"시스템 에러: {str(e)}")
        st.code(traceback.format_exc())
