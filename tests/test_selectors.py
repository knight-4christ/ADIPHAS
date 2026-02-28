import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

sources = [
    {"name": "Punch Health", "url": "https://punchng.com/topics/health-wise/"},
    {"name": "Vanguard Health", "url": "https://www.vanguardngr.com/category/health/"}
]

for source in sources:
    print(f"\n--- Testing {source['name']} ---")
    try:
        resp = requests.get(source['url'], headers=headers, timeout=10)
        print(f"Status: {resp.status_code}")
        soup = BeautifulSoup(resp.content, "html.parser")
        
        if source['name'] == "Punch Health":
            # Trying different common selectors
            h3s = soup.find_all("h3")
            print(f"Found {len(h3s)} h3 tags")
            for h in h3s[:5]:
                print(f"  - {h.get_text(strip=True)}")
                
        elif source['name'] == "Vanguard Health":
            articles = soup.find_all("article")
            print(f"Found {len(articles)} article tags")
            for a in articles[:5]:
                h = a.find(["h2", "h3"])
                if h:
                    print(f"  - {h.get_text(strip=True)}")
    except Exception as e:
        print(f"Error: {e}")
