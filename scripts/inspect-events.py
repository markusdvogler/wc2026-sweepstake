"""
One-shot diagnostic: dump every event for a given fixture id, so we can
see exactly what api-sports returns. Defaults to fixture 1489373
(Qatar vs Switzerland), the one whose OG isn't being detected.
"""
import json, os, sys
import urllib.request, urllib.parse

API_KEY  = os.environ.get('APISPORTS_KEY', '')
BASE_URL = 'https://v3.football.api-sports.io'
FIXTURE  = int(os.environ.get('FIXTURE_ID', '1489373'))

if not API_KEY:
    print('ERROR: APISPORTS_KEY not set.'); sys.exit(1)

url = f'{BASE_URL}/fixtures/events?fixture={FIXTURE}'
req = urllib.request.Request(url, headers={
    'x-apisports-host': 'v3.football.api-sports.io',
    'x-apisports-key':  API_KEY,
})
resp = json.loads(urllib.request.urlopen(req, timeout=20).read())

print(f'=== Events for fixture {FIXTURE} ===\n')
events = resp.get('response') or []
print(f'Total events: {len(events)}\n')

for ev in events:
    print(json.dumps(ev, indent=2, ensure_ascii=False))
    print('---')
