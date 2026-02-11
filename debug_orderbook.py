"""Debug script to check orderbook data"""
import requests
from config import APIKEY

# Получаем данные рынка
print("=== GETTING MARKET DATA ===")
url = 'https://openapi.opinion.trade/openapi/market/4144'
headers = {'apikey': APIKEY}

response = requests.get(url, headers=headers, timeout=10)
data = response.json()
print('Errno:', data.get('errno'))

if data.get('errno') == 0:
    result = data.get('result', {}).get('data', {})
    print('Market ID:', result.get('marketId'))
    print('Title:', result.get('marketTitle'))
    
    yes_token = result.get('yesTokenId')
    no_token = result.get('noTokenId')
    
    print(f'\nYES Token ID: {yes_token}')
    print(f'NO Token ID: {no_token}')
    
    # Теперь получаем orderbook для каждого токена
    print("\n" + "="*50)
    print("=== YES ORDERBOOK ===")
    
    if yes_token:
        url = f'https://openapi.opinion.trade/openapi/token/orderbook?token_id={yes_token}'
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        print('Errno:', data.get('errno'))
        
        if data.get('errno') == 0:
            result = data.get('result', {})
            bids = result.get('bids', [])
            asks = result.get('asks', [])
            
            print("\nTOP 5 BIDS (buyers):")
            for b in bids[:5]:
                print(f"  Price: {b.get('price')} | Size: {b.get('size')}")
            
            print("\nTOP 5 ASKS (sellers):")
            for a in asks[:5]:
                print(f"  Price: {a.get('price')} | Size: {a.get('size')}")
        else:
            print("Error:", data.get('errmsg'))
    
    print("\n" + "="*50)
    print("=== NO ORDERBOOK ===")
    
    if no_token:
        url = f'https://openapi.opinion.trade/openapi/token/orderbook?token_id={no_token}'
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        print('Errno:', data.get('errno'))
        
        if data.get('errno') == 0:
            result = data.get('result', {})
            bids = result.get('bids', [])
            asks = result.get('asks', [])
            
            print("\nTOP 5 BIDS (buyers):")
            for b in bids[:5]:
                print(f"  Price: {b.get('price')} | Size: {b.get('size')}")
            
            print("\nTOP 5 ASKS (sellers):")
            for a in asks[:5]:
                print(f"  Price: {a.get('price')} | Size: {a.get('size')}")
        else:
            print("Error:", data.get('errmsg'))
