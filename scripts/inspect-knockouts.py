"""
Dump every api-sports WC fixture that is NOT 'Group Stage', so we can
see how their knockout rounds are labeled and which matchups (if any)
have been populated.
"""
import json, os, sys
import urllib.request

API_KEY = os.environ.get('APISPORTS_KEY', '')
if not API_KEY:
    print('ERROR: APISPORTS_KEY not set.'); sys.exit(1)

url = 'https://v3.football.api-sports.io/fixtures?league=1&season=2026'
req = urllib.request.Request(url, headers={
    'x-apisports-host': 'v3.football.api-sports.io',
    'x-apisports-key':  API_KEY,
})
resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
fixtures = resp.get('response') or []

print(f'Total WC 2026 fixtures: {len(fixtures)}\n')
print('=== KNOCKOUT FIXTURES (any round not containing "Group Stage") ===\n')

for fx in fixtures:
    league = fx.get('league') or {}
    round_str = league.get('round') or ''
    if 'group stage' in round_str.lower():
        continue
    fix = fx.get('fixture') or {}
    teams = fx.get('teams') or {}
    h = (teams.get('home') or {}).get('name') or 'TBD'
    a = (teams.get('away') or {}).get('name') or 'TBD'
    print(f'  round={round_str!r}  date={fix.get("date")}  {h} vs {a}')
