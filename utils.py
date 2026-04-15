import requests
import re

def search_address_to_codes(query, vworld_key):
    """
    주소 키워드를 분석하여 시군구코드/법정동코드/번지/호를 반환합니다.
    실패 시 (None, None, None, None, 에러메시지)를 반환합니다.
    """
    if not vworld_key:
        return None, None, None, None, "Vworld API 키가 입력되지 않았습니다."

    # 전처리: '동/호' 제거 (Vworld는 지번까지만 검색 가능)
    clean_query = re.sub(r'\d+동.*$', '', query).strip()
    clean_query = re.sub(r'\d+호.*$', '', clean_query).strip()
    
    url = "https://api.vworld.kr/req/search"
    params = {
        "service": "search",
        "request": "search",
        "version": "2.0",
        "size": "5",
        "page": "1",
        "query": clean_query,
        "type": "address",
        "category": "parcel", 
        "format": "json",
        "key": vworld_key
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        res = response.json()
        
        # 1. API 자체 오류 (인증 실패 등)
        if res.get('response', {}).get('status') == 'ERROR':
            error_msg = res.get('response', {}).get('error', {}).get('text', '알 수 없는 API 오류')
            return None, None, None, None, f"Vworld API 오류: {error_msg}"

        # 2. 결과 없음 (지번 실패 시 도로명으로 재시도)
        if res.get('response', {}).get('status') == 'NOT_FOUND':
            params['category'] = 'road'
            res = requests.get(url, params=params, timeout=10).json()
            
        if res.get('response', {}).get('status') == 'OK':
            item = res['response']['result']['items'][0]
            addr = item.get('address', {})
            adm_cd = addr.get('admCd', '')
            
            if adm_cd:
                s_code = adm_cd[:5]
                b_code = adm_cd[5:]
                lnm = addr.get('lnmaddr', '')
                nums = re.findall(r'\d+', lnm)
                bun = nums[0] if len(nums) > 0 else "0"
                ji = nums[1] if len(nums) > 1 else "0"
                return s_code, b_code, bun, ji, "성공"
        
        return None, None, None, None, f"검색 결과가 없습니다. (검색어: {clean_query})"
                
    except Exception as e:
        return None, None, None, None, f"네트워크 오류: {str(e)}"
