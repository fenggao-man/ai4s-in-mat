import requests
import os
from pathlib import Path

def test_key():
    key = "sk-b9b17deb408b425aa649728280f1feba"
    
    endpoints = [
        ("Official DeepSeek", "https://api.deepseek.com/v1/chat/completions", "deepseek-chat"),
        ("Aihubmix", "https://aihubmix.com/v1/chat/completions", "deepseek-chat")
    ]
    
    for name, url, model in endpoints:
        print(f"\n[*] Testing {name}...")
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            print(f"    Status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"    [SUCCESS] {name} works!")
            else:
                print(f"    [FAILED] {resp.text[:100]}")
        except Exception as e:
            print(f"    [ERROR] {e}")

if __name__ == "__main__":
    test_key()
