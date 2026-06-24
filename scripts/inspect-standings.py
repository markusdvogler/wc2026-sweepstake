"""
One-shot diagnostic: dump api-sports standings for WC 2026 so we can see
exactly what fields they expose (in particular whether qualification
status appears in a 'description' or similar field).
"""
import json, os, sys
import urllib.request

API_KEY  = os.environ.get('APISPORTS_KEY', '')

if not API_KEY:
    print('ERROR: APISPORTS_KEY not set.'); sys.exit(1)

url = 'https://v3.football.api-sports.io/standings?league=1&season=2026'
req = urllib.request.Request(url, headers={
    'x-apisports-host': 'v3.football.api-sports.io',
    'x-apisports-key':  API_KEY,
})
resp = json.loads(urllib.request.urlopen(req, timeout=20).read())

print('=== WC 2026 STANDINGS ===\n')
print(json.dumps(resp, indent=2, ensure_ascii=False))
