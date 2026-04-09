import json, requests
resp = requests.get('https://openrouter.ai/api/v1/models')
data = resp.json()
free_models = []
for m in data.get('data', []):
    pricing = m.get('pricing', {})
    prompt_price = pricing.get('prompt', '0')
    completion_price = pricing.get('completion', '0')
    if prompt_price == '0' and completion_price == '0':
        free_models.append({
            'id': m['id'],
            'name': m.get('name', ''),
            'context': m.get('context_length', 0)
        })

print(f'Found {len(free_models)} free models:\n')
for m in sorted(free_models, key=lambda x: x['context'], reverse=True):
    print(f"  {m['id']:<55s} ctx={m['context']:>8,}  ({m['name']})")
