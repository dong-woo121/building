import requests
import re
import time

def search_address_to_codes(query, vworld_key):
    """
    Vworld API 호출 시 네트워크 오류에 대비하여 최대 3번 재시도합니다.
    """
    if not vworld_key:
        return None, None, None, None, "Vworld API 키가 입력되지 않았습니다."

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
    
    max_retries = 3
    for i in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=10)
            res = response.json()
            
            if res.get('response', {}).get('status') == 'ERROR':
                error_msg = res.get('response', {}).get('error', {}).get('text', '알 수 없는 API 오류')
                return None, None, None, None, f"Vworld API 오류: {error_msg}"

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
                    
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if i < max_retries - 1:
                time.sleep(1) # 1초 대기 후 재시도
                continue
            return None, None, None, None, "Vworld 서버 연결이 불안정합니다. 잠시 후 다시 시도하거나 '수동 입력 모드'를 사용해 주세요."
        except Exception as e:
            return None, None, None, None, f"예상치 못한 오류: {str(e)}"
