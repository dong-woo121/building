import requests
import re

def search_address_to_codes(query, vworld_key):
    """
    주소 키워드를 분석하여 시군구코드/법정동코드/번지/호를 반환합니다.
    사용자가 '동' 정보를 포함해도 똑똑하게 필터링합니다.
    """
    if not vworld_key:
        return None, None, None, None

    # 전처리: 주소에서 '동', '호' 정보가 포함되어 있으면 검색을 위해 제거
    # 예: '삼성동 아이파크 101동' -> '삼성동 아이파크'
    clean_query = re.sub(r'\d+동.*$', '', query).strip()
    clean_query = re.sub(r'\d+호.*$', '', clean_query).strip()
    
    # 1차 시도: Vworld Search API (가장 강력함)
    url = "https://api.vworld.kr/req/search"
    params = {
        "service": "search",
        "request": "search",
        "version": "2.0",
        "size": "5", # 여러 결과 중 가장 적절한 것 선택
        "page": "1",
        "query": clean_query,
        "type": "address",
        "category": "parcel", # 지번 기반이 코드가 정확함
        "format": "json",
        "key": vworld_key
    }
    
    try:
        res = requests.get(url, params=params, timeout=10).json()
        
        # 지번(parcel) 검색 실패 시 도로명(road)으로 재시도
        if res.get('response', {}).get('status') == 'NOT_FOUND':
            params['category'] = 'road'
            res = requests.get(url, params=params, timeout=10).json()
            
        if res.get('response', {}).get('status') == 'OK':
            # 검색 결과 중 첫 번째 항목 사용
            item = res['response']['result']['items'][0]
            addr = item.get('address', {})
            adm_cd = addr.get('admCd', '') # 행정구역코드 (1168010100)
            
            if adm_cd:
                s_code = adm_cd[:5]
                b_code = adm_cd[5:]
                
                # 번지/호 추출 (lnmaddr: 지번주소에서 숫자 파싱)
                lnm = addr.get('lnmaddr', '')
                nums = re.findall(r'\d+', lnm)
                bun = nums[0] if len(nums) > 0 else "0"
                ji = nums[1] if len(nums) > 1 else "0"
                
                return s_code, b_code, bun, ji
                
    except Exception as e:
        print(f"주소 검색 오류: {e}")
        
    return None, None, None, None
