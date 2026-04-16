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
BR_HSPRC_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrHsprcInfo"

def _norm(s):
    return "".join(s.split()).lower()

def _fetch_all_items(url, base_params):
    import math
    try:
        r = requests.get(url, params=base_params, timeout=15)
        if r.status_code != 200:
            return [], 0
        root = ET.fromstring(r.text)
        code = root.findtext('.//resultCode', '')
        if code not in ('00', '0', ''):
            return [], 0
        total = int(root.findtext('.//totalCount') or '0')
        items = list(root.findall('.//item'))
        per_page = len(items) if items else 1000
        if per_page > 0 and total > per_page:
            for page in range(2, math.ceil(total / per_page) + 1):
                p = {**base_params, 'pageNo': page}
                r2 = requests.get(url, params=p, timeout=15)
                items += list(ET.fromstring(r2.text).findall('.//item'))
        return items, total
    except Exception:
        return [], 0

def get_unit_data(s_code, b_code, bun, ji, api_key, debug_container=None):
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
    # 1) 전유부 목록 (동, 호, 층번호)
    raw_units, total_units = _fetch_all_items(BR_EXPOS_INFO_URL, base)

    # 2) 면적 데이터 (전유 only)
    raw_area, total_area = _fetch_all_items(BR_AREA_URL, base)
    area_items = [i for i in raw_area if i.findtext('exposPubuseGbCd', '') == '1']

    if debug_container:
        debug_container.info(
            f"📊 **API 로그**\n\n"
            f"- getBrExposInfo: API총계={total_units}건 / 수신={len(raw_units)}건\n"
            f"- getBrExposPubuseAreaInfo: API총계={total_area}건 / 수신={len(raw_area)}건 / 전유={len(area_items)}건"
        )

    unit_items = raw_units
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

def calc_property_tax(gongsi_price):
    base = gongsi_price * 0.45
    if base <= 60_000_000:
        tax = base * 0.001
    elif base <= 150_000_000:
        tax = 60_000 + (base - 60_000_000) * 0.002
    elif base <= 300_000_000:
        tax = 240_000 + (base - 150_000_000) * 0.003
    else:
        tax = 570_000 + (base - 300_000_000) * 0.004
    return round(tax)

def get_hsprc_for_candidates(s_code, b_code, bun, ji, candidates, api_key):
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
    items, _ = _fetch_all_items(BR_HSPRC_URL, base)
    candidate_keys = {(c['동'], c['호']) for c in candidates}
    # Take most recent year per unit
    price_by_unit = {}
    for item in items:
        dong = item.findtext('dongNm', '')
        ho = item.findtext('hoNm', '')
        if (dong, ho) not in candidate_keys:
            continue
        try:
            year = int(item.findtext('stdrYear', '0') or '0')
            price = float(item.findtext('hsprc', '0') or '0')
            key = (dong, ho)
            if key not in price_by_unit or year > price_by_unit[key][0]:
                price_by_unit[key] = (year, price)
        except ValueError:
            pass
    return {k: v[1] for k, v in price_by_unit.items()}

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

if 'ambiguous_candidates' not in st.session_state:
    st.session_state.ambiguous_candidates = None
if 'search_params' not in st.session_state:
    st.session_state.search_params = None

if st.button("🔍 정확한 호수 확인하기", use_container_width=True, type="primary"):
    st.session_state.ambiguous_candidates = None
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
                        debug_container=st
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
                            # 면적까지 동일한 후보 2개 이상 → 재산세로 2차 확인 준비
                            if len(df_final) >= 2 and has_area and df_final['면적'].nunique() == 1:
                                st.session_state.ambiguous_candidates = df_final[['동', '호']].to_dict('records')
                                st.session_state.search_params = (s_code, b_code, bun, ji)
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

# 2차 필터: 재산세로 최종 호수 확정
if st.session_state.get('ambiguous_candidates'):
    candidates = st.session_state.ambiguous_candidates
    s_c, b_c, bn, j = st.session_state.search_params
    st.divider()
    st.warning(f"⚠️ {len(candidates)}개 후보의 면적이 완전히 동일합니다. 네이버 매물 '중개보수 및 세금정보'에서 **재산세** 항목 금액만 입력하세요 (지방교육세·도시지역분·종부세 제외).")
    jaesan_val = st.number_input("💰 재산세 본세 (원)", min_value=0, step=1000, key="jaesan_input")
    if st.button("🎯 재산세로 최종 확인", key="btn_jaesan", type="secondary"):
        with st.spinner("공시가격 조회 중..."):
            hsprc_map = get_hsprc_for_candidates(s_c, b_c, bn, j, candidates, API_KEY)
        if not hsprc_map:
            st.error("공시가격 데이터를 가져올 수 없습니다. API 응답을 확인하세요.")
        else:
            results = []
            for cand in candidates:
                key = (cand['동'], cand['호'])
                gongsi = hsprc_map.get(key, 0)
                if gongsi > 0:
                    tax = calc_property_tax(gongsi)
                    results.append({**cand, '공시가격': int(gongsi), '계산재산세': tax})
            if not results:
                st.error("후보 호수의 공시가격을 찾을 수 없습니다.")
            else:
                st.write("**후보별 재산세 계산 결과:**")
                for r in results:
                    st.write(f"- {r['동']} {r['호']}: 공시가격 {r['공시가격']:,}원 → 재산세 {r['계산재산세']:,}원")
                matched = [r for r in results if abs(r['계산재산세'] - jaesan_val) <= 10_000]
                if len(matched) == 1:
                    st.success(f"### 🎉 최종 확정: **{matched[0]['동']} {matched[0]['호']}**")
                    st.session_state.ambiguous_candidates = None
                elif len(matched) == 0:
                    st.warning("입력한 재산세와 일치하는 후보가 없습니다. 금액을 다시 확인하세요.")
                else:
                    st.warning(f"여전히 {len(matched)}개가 일치합니다. 재산세를 더 정확히 입력해보세요.")
