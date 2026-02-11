import os
from dotenv import load_dotenv
from coinbase_commerce.client import Client

load_dotenv()

# 1. Initialize the client with your API Key
API_KEY = os.getenv("COINBASE_API_KEY")
client = Client(api_key=API_KEY)

# 2. Define the payment details
charge_info = {
    "name": "Test",
    "description": "Test transaction",
    "local_price": {
        "amount": "1.00",
        "currency": "USD"
    },
    "pricing_type": "fixed_price",
    "metadata": {
        "order_id": "123",
        "user_id": "123"
    }
}

# 3. Create the charge
charge = client.charge.create(**charge_info)

# 4. Get the Payment ID and Hosted URL
print(f"Payment ID: {charge.id}")
print(f"Order Code: {charge.code}")
print(f"Payment Link: {charge.hosted_url}")
