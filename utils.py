import requests

KAKAO_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_COORD2REGION_URL = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json"
KAKAO_COORD2ADDR_URL = "https://dapi.kakao.com/v2/local/geo/coord2address.json"

def search_address_to_codes(query, kakao_key):
    if not kakao_key:
        return None, None, None, None, "Kakao API 키가 입력되지 않았습니다."

    headers = {"Authorization": f"KakaoAK {kakao_key}"}

    # Step 1: 아파트 단지명 → 좌표 획득
    try:
        r1 = requests.get(KAKAO_SEARCH_URL, params={"query": query, "size": 1}, headers=headers, timeout=10)
        if r1.status_code == 401:
            return None, None, None, None, "Kakao API 인증 실패 (401). REST API 키와 로컬 API 활성화를 확인하세요."
        if r1.status_code != 200:
            return None, None, None, None, f"Kakao API 오류: HTTP {r1.status_code} / {r1.text[:200]}"
        docs = r1.json().get("documents", [])
        if not docs:
            return None, None, None, None, f"'{query}' 검색 결과 없음. 카카오맵에서 검색되는 정확한 단지명을 입력하세요."
        x, y = docs[0]["x"], docs[0]["y"]
    except Exception as e:
        return None, None, None, None, f"통신 오류 (장소 검색): {str(e)}"

    # Step 2: 좌표 → 법정동 코드 (sigunguCd + bjdongCd)
    try:
        r2 = requests.get(KAKAO_COORD2REGION_URL, params={"x": x, "y": y}, headers=headers, timeout=10)
        adm_cd = None
        for doc in r2.json().get("documents", []):
            if doc.get("region_type") == "B":
                adm_cd = doc["code"]
                break
        if not adm_cd:
            return None, None, None, None, "법정동 코드를 찾을 수 없습니다."
        s_code = adm_cd[:5]
        b_code = adm_cd[5:]
    except Exception as e:
        return None, None, None, None, f"통신 오류 (지역코드 검색): {str(e)}"

    # Step 3: 좌표 → 지번 (번지/호)
    try:
        r3 = requests.get(KAKAO_COORD2ADDR_URL, params={"x": x, "y": y}, headers=headers, timeout=10)
        docs3 = r3.json().get("documents", [])
        bun, ji = "0", "0"
        if docs3 and docs3[0].get("address"):
            addr = docs3[0]["address"]
            bun = addr.get("main_address_no") or "0"
            ji = addr.get("sub_address_no") or "0"
        return s_code, b_code, bun, ji, "성공"
    except Exception as e:
        return None, None, None, None, f"통신 오류 (지번 검색): {str(e)}"
