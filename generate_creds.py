import asyncio
import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

async def main():
    load_dotenv()
    pk = os.getenv("PRIVATE_KEY") 
    
    if not pk:
        print("❌ Ошибка: Переменная PRIVATE_KEY не найдена в .env")
        return

    client = ClobClient(
        host="https://clob.polymarket.com",
        key=pk,
        chain_id=POLYGON
    )

    try:
        print("⏳ Попытка СОЗДАТЬ новые API ключи (create_api_key)...")
        # Этот метод создает абсолютно новые ключи
        creds = client.create_api_key()
        
        print("\n✅ УСПЕШНО СОЗДАНО! Добавьте это в .env:")
        print(f"POLYMARKET_API_KEY=\"{creds.api_key}\"")
        print(f"POLYMARKET_API_SECRET=\"{creds.api_secret}\"")
        print(f"POLYMARKET_API_PASSPHRASE=\"{creds.api_passphrase}\"")
        
    except Exception as e:
        print(f"⚠️ Не удалось создать (возможно, уже есть). Пробуем вывести (derive_api_key)...")
        try:
            creds = client.derive_api_key()
            print("\n✅ УСПЕШНО ПОЛУЧЕНО! Добавьте это в .env:")
            print(f"POLYMARKET_API_KEY=\"{creds.api_key}\"")
            print(f"POLYMARKET_API_SECRET=\"{creds.api_secret}\"")
            print(f"POLYMARKET_API_PASSPHRASE=\"{creds.api_passphrase}\"")
        except Exception as e2:
            print(f"❌ Критическая ошибка: {e2}")
            print("\nПроверьте:")
            print("1. Есть ли на кошельке немного MATIC/POL (для регистрации в CLOB может потребоваться транзакция).")
            print("2. Правильно ли указан PRIVATE_KEY (он должен соответствовать адресу в Polymarket).")

if __name__ == "__main__":
    asyncio.run(main())