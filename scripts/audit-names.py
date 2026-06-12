"""
One-shot name-audit script. Fetches ALL WC 2026 fixtures from api-sports
and compares team names against the canonical names in data/matches.json
(fdorg schema). Prints any mismatches so we can pre-populate NAME_MAP
before the matches actually happen.

Run via .github/workflows/audit-names.yml (manual dispatch only).
"""
import json, os, sys, time, re, unicodedata
import urllib.request, urllib.parse

API_KEY  = os.environ.get('APISPORTS_KEY', '')
BASE_URL = 'https://v3.football.api-sports.io'
HOST     = 'v3.football.api-sports.io'
WC_LEAGUE_ID = 1
WC_SEASON    = 2026

# Same NAME_MAP as the live script — entries here mean "we already know"
NAME_MAP = {
    'Korea Republic':               'South Korea',
    'Republic of Korea':            'South Korea',
    'IR Iran':                      'Iran',
    'Cape Verde':                   'Cape Verde Islands',
    "Cote d'Ivoire":                'Ivory Coast',
    "Côte d'Ivoire":                'Ivory Coast',
    'Bosnia':                       'Bosnia-Herzegovina',
    'Bosnia and Herzegovina':       'Bosnia-Herzegovina',
    'Bosnia & Herzegovina':         'Bosnia-Herzegovina',
    'Turkiye':                      'Turkey',
    'Türkiye':                      'Turkey',
    'USA':                          'United States',
    'United States of America':     'United States',
    'DR Congo':                     'Congo DR',
    'Congo Democratic Republic':    'Congo DR',
    'Democratic Republic of Congo': 'Congo DR',
    'Curacao':                      'Curaçao',
    'Czech Republic':               'Czechia',
}

def normalize(n):
    return NAME_MAP.get(n, n) if n else ''

_NOISE = {'the', 'and', 'of', 'fc', 'national', 'team', 'republic', 'islands'}

def _tokenize(name):
    nfkd = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode('ascii')
    return set(re.findall(r'[a-z0-9]+', nfkd.lower())) - _NOISE

def fuzzy_eq(a, b):
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb: return False
    if ta == tb or ta <= tb or tb <= ta: return True
    overlap = len(ta & tb)
    return overlap >= 2 or (overlap >= 1 and overlap == min(len(ta), len(tb)))

def api_get(path, params=None):
    url = BASE_URL + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        'x-apisports-host': HOST, 'x-apisports-key': API_KEY,
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

if not API_KEY:
    print('ERROR: APISPORTS_KEY not set.'); sys.exit(1)

# 1) All canonical WC team names from fdorg
fd = json.load(open('data/matches.json', encoding='utf-8'))
fd_teams = set()
for m in fd['matches']:
    h = (m.get('homeTeam') or {}).get('name')
    a = (m.get('awayTeam') or {}).get('name')
    if h: fd_teams.add(h)
    if a: fd_teams.add(a)
print(f'fdorg has {len(fd_teams)} unique team names.')

# 2) Fetch ALL WC 2026 fixtures from api-sports (single call covers all 104)
print(f'\nFetching ALL WC 2026 fixtures from api-sports...')
resp = api_get('/fixtures', {'league': WC_LEAGUE_ID, 'season': WC_SEASON})
fixtures = resp.get('response') or []
print(f'api-sports returned {len(fixtures)} fixtures.')

ra_teams = set()
for fx in fixtures:
    teams = fx.get('teams') or {}
    h = (teams.get('home') or {}).get('name')
    a = (teams.get('away') or {}).get('name')
    if h: ra_teams.add(h)
    if a: ra_teams.add(a)
print(f'api-sports has {len(ra_teams)} unique team names.')

# 3) For each api-sports team name, check whether it maps to an fdorg team
print('\n--- TEAM NAME COMPARISON ---')
exact_ok    = []      # already matches an fdorg name (after NAME_MAP)
fuzzy_ok    = []      # matches an fdorg name via fuzzy
unmapped    = []      # no match — needs NAME_MAP entry

for ra_name in sorted(ra_teams):
    norm = normalize(ra_name)
    if norm in fd_teams:
        exact_ok.append(ra_name)
        continue
    fuzzy = next((fd for fd in fd_teams if fuzzy_eq(norm, fd)), None)
    if fuzzy:
        fuzzy_ok.append((ra_name, fuzzy))
        continue
    unmapped.append(ra_name)

print(f'\n[EXACT] {len(exact_ok)} team(s) match exactly (after NAME_MAP):')
for n in exact_ok:
    print(f'  {n}')

print(f'\n[FUZZY] {len(fuzzy_ok)} team(s) match via fuzzy fallback:')
for ra, fd in fuzzy_ok:
    print(f'  "{ra}"  →  "{fd}"')

print(f'\n[UNMAPPED] {len(unmapped)} team(s) need NAME_MAP entries:')
for n in unmapped:
    # Show what fdorg name is closest (token overlap)
    tokens = _tokenize(n)
    candidates = []
    for fd in fd_teams:
        overlap = len(tokens & _tokenize(fd))
        if overlap > 0:
            candidates.append((overlap, fd))
    candidates.sort(reverse=True)
    suggestion = candidates[0][1] if candidates else '???'
    print(f'  "{n}"  →  suggest: "{suggestion}"')

# Also flag fdorg teams that NO api-sports fixture references
missing = fd_teams - {normalize(n) for n in ra_teams}
# Adjust: remove the ones we successfully mapped to via NAME_MAP
mapped_to = {normalize(n) for n in ra_teams}
for _, fd in fuzzy_ok: mapped_to.add(fd)
missing = fd_teams - mapped_to

if missing:
    print(f'\n[fdorg teams with NO api-sports fixture seen yet] {len(missing)}:')
    for n in sorted(missing):
        print(f'  {n}')

print('\n--- END ---')
