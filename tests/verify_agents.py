import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_healthcheck():
    try:
        resp = requests.get(f"{BASE_URL}/healthcheck")
        print(f"Healthcheck: {resp.status_code} - {resp.json()}")
    except Exception as e:
        print(f"Healthcheck Failed: {e}")

def test_news_scrape():
    print("\nTesting News Scraper & NLP...")
    try:
        resp = requests.get(f"{BASE_URL}/acquisition/news/scrape")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Success! Scraped {data['count']} items.")
            print("Sample Data:", json.dumps(data['data'][0], indent=2))
        else:
            print(f"Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Scrape Test Failed: {e}")

def test_knowledge_fusion():
    print("\nTesting Knowledge Fusion...")
    payload = [
        {"source": "NEWS_MEDIA", "cases": 50, "location": "Ikeja", "disease": "Cholera"},
        {"source": "NCDC_OFFICIAL", "cases": 10, "location": "Ikeja", "disease": "Cholera"}
    ]
    try:
        resp = requests.post(f"{BASE_URL}/intelligence/fuse", json=payload)
        if resp.status_code == 200:
            print("Fusion Result:", json.dumps(resp.json(), indent=2))
        else:
            print(f"Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Fusion Test Failed: {e}")

if __name__ == "__main__":
    test_healthcheck()
    test_news_scrape()
    test_knowledge_fusion()
