import requests

def search_address_to_codes(query, vworld_key):
    """
    Vworld API를 사용하여 주소 키워드를 시군구코드/법정동코드로 변환합니다.
    """
    if not vworld_key:
        return None, None, None, None
        
    url = "https://api.vworld.kr/req/address"
    params = {
        "service": "address",
        "request": "getcoord",
        "version": "2.0",
        "crs": "epsg:3857",
        "address": query,
        "refine": "true",
        "simple": "false",
        "format": "json",
        "type": "road", # 도로명 주소 기준
        "key": vworld_key
    }
    
    try:
        # 1차 도로명 주소 검색
        res = requests.get(url, params=params).json()
        
        # 도로명 검색 실패 시 지번(parcel)으로 재시도
        if res.get('response', {}).get('status') == 'NOT_FOUND':
            params['type'] = 'parcel'
            res = requests.get(url, params=params).json()
            
        if res.get('response', {}).get('status') == 'OK':
            # 주소 정보 추출
            address_info = res['response']['result']['structure']
            
            # 행정구역 코드 추출 (PNU 코드 활용)
            # PNU: 시군구(5) + 법정동(5) + 산(1) + 번지(4) + 호(4)
            pnu = res['response']['refined']['text'] # 실제로는 PNU를 반환하는 다른 API나 가공이 필요할 수 있음
            
            # Vworld의 주소 검색 결과에서 행정코드를 직접 가져오기 위해 
            # 검색 API(search)를 추가로 사용하거나, PNU 파싱 로직을 적용합니다.
            return parse_pnu_from_vworld(query, vworld_key)
            
    except Exception as e:
        print(f"주소 검색 오류: {e}")
        
    return None, None, None, None

def parse_pnu_from_vworld(query, key):
    """
    Vworld Search API를 통해 PNU(필지식별번호)를 가져와서 
    시군구코드와 법정동코드를 분리합니다.
    """
    url = "https://api.vworld.kr/req/search"
    params = {
        "service": "search",
        "request": "search",
        "version": "2.0",
        "size": "1",
        "page": "1",
        "query": query,
        "type": "address",
        "category": "parcel", # 지번 주소 기반이 코드가 더 정확함
        "format": "json",
        "errorformat": "json",
        "key": key
    }
    
    try:
        res = requests.get(url, params=params).json()
        if res.get('response', {}).get('status') == 'OK':
            item = res['response']['result']['items'][0]
            # 지번 주소의 경우 행정코드가 포함되어 있음
            # admCd: 행정구역코드(10자리) = 시군구(5) + 법정동(5)
            # lnmaddr: 지번 (예: 101-1)
            adm_cd = item.get('address', {}).get('admCd', '')
            lnm = item.get('address', {}).get('lnmaddr', '')
            
            if adm_cd:
                s_code = adm_cd[:5]
                b_code = adm_cd[5:]
                
                # 번지/호 추출
                import re
                nums = re.findall(r'\d+', lnm)
                bun = nums[0] if len(nums) > 0 else "0"
                ji = nums[1] if len(nums) > 1 else "0"
                
                return s_code, b_code, bun, ji
    except:
        pass
    return None, None, None, None
