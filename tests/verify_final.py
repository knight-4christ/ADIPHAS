import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_auth_and_scraping():
    print("--- Testing Real-time Features & Authentication ---")
    
    # 1. Healthcheck
    try:
        resp = requests.get(f"{BASE_URL}/healthcheck")
        health = resp.json()
        print(f"Healthcheck: {health['status']} | Version: {health['version']} | spaCy: {health['spacy_loaded']}")
    except Exception as e:
        print(f"Healthcheck failed: {e}")
        return

    # 2. Registration
    print("\nTesting Registration...")
    reg_payload = {
        "username": "testuser_unique_1",
        "password": "securepassword123",
        "email": "test@example.com",
        "full_name": "Test User"
    }
    try:
        resp = requests.post(f"{BASE_URL}/auth/register", json=reg_payload)
        if resp.status_code == 200:
            print("Registration Successful!")
        else:
            print(f"Registration Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Registration Error: {e}")

    # 3. Login
    print("\nTesting Login...")
    login_payload = {
        "username": "testuser_unique_1",
        "password": "securepassword123"
    }
    token = None
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", data=login_payload)
        if resp.status_code == 200:
            token = resp.json()["access_token"]
            print("Login Successful! Token acquired.")
        else:
            print(f"Login Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Login Error: {e}")

    # 4. Real Scraping & NLP
    print("\nTesting Real News Scraping (Punch/Vanguard)...")
    try:
        resp = requests.get(f"{BASE_URL}/acquisition/news/scrape")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Scraped {data['count']} actual headlines from live sites.")
            if data['count'] > 0:
                print("First actual result:", json.dumps(data['data'][0], indent=2))
        else:
            print(f"Scrape Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Scrape Error: {e}")

if __name__ == "__main__":
    test_auth_and_scraping()
