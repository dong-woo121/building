import requests
import re

def search_address_to_codes(query, vworld_key):
    if not vworld_key:
        return None, None, None, None, "Vworld API 키가 입력되지 않았습니다."

    url = "https://api.vworld.kr/req/search"

    # Step 1: 아파트 단지명 → place 검색 → 지번 주소 문자열 획득
    try:
        r1 = requests.get(url, params={
            "service": "search", "request": "search", "version": "2.0",
            "size": "5", "page": "1",
            "query": query, "type": "place",
            "format": "json", "key": vworld_key
        }, timeout=10)

        if "application/json" not in r1.headers.get("Content-Type", ""):
            return None, None, None, None, f"Vworld 서버가 비정상 응답을 보냈습니다 (HTML). 키를 확인하세요."

        j1 = r1.json()
        status1 = j1.get('response', {}).get('status')

        if status1 == 'ERROR':
            err = j1['response'].get('error', {}).get('text', '알 수 없는 오류')
            return None, None, None, None, f"Vworld API 오류: {err}"

        parcel_addr = None
        if status1 == 'OK':
            items = j1['response']['result']['items']
            for item in items:
                pa = item.get('address', {}).get('parcel', '')
                if pa:
                    parcel_addr = pa
                    break

        if not parcel_addr:
            return None, None, None, None, f"'{query}'에 해당하는 장소를 찾을 수 없습니다. 단지명을 정확히 입력하세요."

    except Exception as e:
        return None, None, None, None, f"통신 오류 (place 검색): {str(e)}"

    # Step 2: 지번 주소 문자열 → address 검색 → admCd 획득
    try:
        r2 = requests.get(url, params={
            "service": "search", "request": "search", "version": "2.0",
            "size": "1", "page": "1",
            "query": parcel_addr, "type": "address", "category": "parcel",
            "format": "json", "key": vworld_key
        }, timeout=10)

        j2 = r2.json()
        if j2.get('response', {}).get('status') == 'OK':
            item2 = j2['response']['result']['items'][0]
            addr2 = item2.get('address', {})
            adm_cd = addr2.get('admCd', '')
            if adm_cd:
                s_code = adm_cd[:5]
                b_code = adm_cd[5:]
                lnm = addr2.get('lnmaddr', '')
                nums = re.findall(r'\d+', lnm)
                bun = nums[0] if len(nums) > 0 else "0"
                ji = nums[1] if len(nums) > 1 else "0"
                return s_code, b_code, bun, ji, "성공"

        return None, None, None, None, f"admCd 획득 실패 (지번: {parcel_addr})"

    except Exception as e:
        return None, None, None, None, f"통신 오류 (address 검색): {str(e)}"
