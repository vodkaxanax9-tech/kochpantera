"""
Health check для Railway.
Проверяет что BOT_TOKEN установлен и валиден.
"""
import os
import sys
import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8765723335:AAE-XaH0oAu1VizrKNfmGjhCy2LYyGzxckU"

def check():
    """Проверяет здоровье бота."""
    if not BOT_TOKEN:
        print("FAIL: BOT_TOKEN не установлен")
        sys.exit(1)
    
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if data.get("ok"):
            print("OK: Бот валиден")
            sys.exit(0)
        else:
            print(f"FAIL: {data.get('description', 'Неизвестная ошибка')}")
            sys.exit(1)
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check()
