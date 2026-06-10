"""
Fetches WC 2026 match statistics from Free API Live Football Data (RapidAPI).

Uses data/matches.json (football-data.org) as the authoritative list of WC
fixtures. For each newly-finished WC match, fetches stats from RapidAPI by
matching team names to the correct event on that date.

Runs hourly via .github/workflows/fetch-stats.yml (~48 API calls/day base).
"""
import json, os, re, sys, time, unicodedata
import urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

API_KEY  = os.environ.get('RAPIDAPI_KEY', '')
BASE_URL = 'https://free-api-live-football-data.p.rapidapi.com'
HOST     = 'free-api-live-football-data.p.rapidapi.com'

# Normalise team names to our canonical names (teams.json)
NAME_MAP = {
    'Korea Republic':               'South Korea',
    'Republic of Korea':            'South Korea',
    'IR Iran':                      'Iran',
    'Cape Verde':                   'Cape Verde Islands',
    "Cote d'Ivoire":                'Ivory Coast',
    "Côte d'Ivoire":                'Ivory Coast',
    'Bosnia':                       'Bosnia-Herzegovina',
    'Bosnia and Herzegovina':       'Bosnia-Herzegovina',
    'Turkiye':                      'Turkey',
    'Türkiye':                      'Turkey',
    'USA':                          'United States',
    'United States of America':     'United States',
    'DR Congo':                     'Congo DR',
    'Democratic Republic of Congo': 'Congo DR',
    'Curacao':                      'Curaçao',
}

def normalize(name):
    return NAME_MAP.get(name, name)

# Token-based fuzzy matching — for team-name variants not covered by NAME_MAP
# (accent differences, word order, articles, etc.). Self-healing fallback.
_NOISE_TOKENS = {'the', 'and', 'of', 'fc', 'national', 'team', 'republic', 'islands'}

def _tokenize(name):
    """Lowercase, strip accents, drop noise words, return token set."""
    nfkd = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode('ascii')
    return set(re.findall(r'[a-z0-9]+', nfkd.lower())) - _NOISE_TOKENS

def fuzzy_eq(a, b):
    """True if a and b describe the same team after lenient normalisation."""
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return False
    if ta == tb or ta <= tb or tb <= ta:
        return True
    # Strong overlap: at least 2 shared tokens or all of the smaller set matches
    overlap = len(ta & tb)
    return overlap >= 2 or (overlap >= 1 and overlap == min(len(ta), len(tb)))

def api_get(path, params=None):
    url = BASE_URL + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        'x-rapidapi-host': HOST,
        'x-rapidapi-key':  API_KEY,
        'Content-Type':    'application/json'
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def ensure_team(teams, name):
    if name not in teams:
        teams[name] = {
            'yellowCards': 0, 'redCards': 0,
            'fouls': 0, 'ownGoals': 0, 'lateGoals': 0
        }

def fetch_finished_matches_for_date(date_yyyymmdd):
    """Fetch all finished matches from RapidAPI for a given date."""
    resp = api_get('/football-get-matches-by-date', {'date': date_yyyymmdd})
    all_matches = []
    if isinstance(resp, dict):
        inner = resp.get('response', {})
        if isinstance(inner, dict):
            all_matches = inner.get('matches', [])
        elif isinstance(inner, list):
            all_matches = inner
    elif isinstance(resp, list):
        all_matches = resp
    return [m for m in all_matches
            if isinstance(m.get('status'), dict) and m['status'].get('finished')]

def find_in_rapidapi(ra_matches, home_norm, away_norm):
    """Find a RapidAPI match whose team names match home_norm/away_norm.

    Pass 1: exact match (after NAME_MAP). Pass 2: token-based fuzzy match for
    accent/word-order/article variants — self-healing for unmapped names.
    Pass 3: fuzzy match allowing swapped home/away (some APIs flip them).
    """
    candidates = []
    for m in ra_matches:
        h = m.get('home', {}) or {}
        a = m.get('away', {}) or {}
        ra_home = normalize(h.get('longName') or h.get('name', ''))
        ra_away = normalize(a.get('longName') or a.get('name', ''))
        candidates.append((m, ra_home, ra_away))

    # Pass 1: exact (post-NAME_MAP)
    for m, rh, ra in candidates:
        if rh == home_norm and ra == away_norm:
            return m

    # Pass 2: fuzzy, same orientation
    for m, rh, ra in candidates:
        if fuzzy_eq(rh, home_norm) and fuzzy_eq(ra, away_norm):
            print(f'  Fuzzy matched: "{rh}" ≈ "{home_norm}", "{ra}" ≈ "{away_norm}"')
            return m

    # Pass 3: fuzzy, swapped orientation (rare API quirk)
    for m, rh, ra in candidates:
        if fuzzy_eq(rh, away_norm) and fuzzy_eq(ra, home_norm):
            print(f'  Fuzzy matched (swapped): "{rh}" ≈ "{away_norm}", "{ra}" ≈ "{home_norm}"')
            return m

    return None

def parse_int(val):
    try:
        return int(val or 0)
    except (ValueError, TypeError):
        return 0

def process_stats(teams, home, away, resp):
    """Extract fouls, yellow/red cards from /football-get-match-all-stats."""
    def apply(tname, stat_list):
        ensure_team(teams, tname)
        for s in (stat_list or []):
            if not isinstance(s, dict):
                continue
            key = str(s.get('name') or s.get('type') or '').lower()
            val = parse_int(s.get('value') or s.get('count') or 0)
            if 'yellow' in key:
                teams[tname]['yellowCards'] += val
            elif 'red card' in key or key in ('red cards',):
                teams[tname]['redCards'] += val
            elif 'foul' in key:
                teams[tname]['fouls'] += val

    data = resp
    if isinstance(resp, dict):
        for wrap in ('response', 'data', 'result'):
            if wrap in resp:
                data = resp[wrap]
                break

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            traw = (item.get('team', {}).get('name') if isinstance(item.get('team'), dict)
                    else item.get('teamName') or item.get('name', ''))
            apply(normalize(str(traw)), item.get('statistics') or item.get('stats') or [])
        return

    if isinstance(data, dict):
        for key, tname in (('home', home), ('away', away)):
            if key in data and isinstance(data[key], dict):
                apply(tname, data[key].get('statistics') or data[key].get('stats') or [])

def process_events(teams, home, away, resp):
    """Extract own goals and late goals (≥85 min) from /football-get-match-detail."""
    incidents = []
    data = resp
    if isinstance(resp, dict):
        for wrap in ('response', 'data', 'result'):
            if wrap in resp:
                data = resp[wrap]
                break
    if isinstance(data, list):
        incidents = data
    elif isinstance(data, dict):
        for key in ('incidents', 'events', 'goals', 'timeline'):
            if key in data and isinstance(data[key], list):
                incidents = data[key]
                break

    for inc in incidents:
        if not isinstance(inc, dict):
            continue
        etype  = str(inc.get('type') or inc.get('incidentType') or '').lower()
        detail = str(inc.get('detail') or inc.get('incidentClass') or '').lower()
        if 'goal' not in etype and 'goal' not in detail:
            continue

        is_home = inc.get('isHome')
        traw = (inc.get('team', {}).get('name') if isinstance(inc.get('team'), dict)
                else inc.get('teamName') or inc.get('team', ''))
        tname = normalize(str(traw)) if traw else (home if is_home else away if is_home is False else None)
        if not tname:
            continue

        ensure_team(teams, tname)
        if 'own' in detail or inc.get('isOwnGoal'):
            teams[tname]['ownGoals'] += 1

        t = inc.get('time', {})
        elapsed = parse_int(t.get('elapsed') if isinstance(t, dict) else t)
        extra   = parse_int(t.get('extra') if isinstance(t, dict) else inc.get('addedTime', 0))
        if elapsed + extra >= 85:
            teams[tname]['lateGoals'] += 1


# ── Main ──────────────────────────────────────────────────────────────────────

if not API_KEY:
    print('ERROR: RAPIDAPI_KEY not set.')
    sys.exit(1)

# Load saved stats
stats_path = 'data/team-stats.json'
try:
    with open(stats_path) as f:
        data = json.load(f)
except Exception:
    data = {}

processed = set(data.get('processedFixtures', []))  # fdorg match IDs
teams     = data.get('teams', {})
errors    = []

# Load football-data.org WC fixtures as the authoritative match list
try:
    with open('data/matches.json') as f:
        fdorg = json.load(f)
    fd_matches = fdorg.get('matches', [])
except Exception as e:
    print(f'ERROR: could not load data/matches.json: {e}')
    sys.exit(1)

# Find finished WC matches not yet processed
new_wc_matches = [
    m for m in fd_matches
    if m.get('status') == 'FINISHED' and m.get('id') not in processed
]
print(f'Finished WC matches not yet processed: {len(new_wc_matches)}')

if not new_wc_matches:
    print('Nothing to do.')
    data['lastUpdated'] = datetime.now(timezone.utc).isoformat()
    with open(stats_path, 'w') as f:
        json.dump(data, f, indent=2)
    sys.exit(0)

# Group unprocessed matches by the dates we need to fetch from RapidAPI.
# WC matches are in the Americas (UTC-4 to UTC-7), so a match on "June 11 local"
# might have utcDate "June 12". We check both the UTC date and the day before.
date_cache = {}  # YYYYMMDD -> list of finished RapidAPI matches

def get_cached(date_str):
    if date_str not in date_cache:
        print(f'  Fetching RapidAPI matches for {date_str}...')
        try:
            time.sleep(0.4)
            date_cache[date_str] = fetch_finished_matches_for_date(date_str)
            print(f'    Got {len(date_cache[date_str])} finished matches')
        except Exception as e:
            print(f'    Error: {e}')
            date_cache[date_str] = []
    return date_cache[date_str]

new_count = 0
for m in new_wc_matches:
    fdorg_id   = m['id']
    home = normalize(m['homeTeam']['name'])
    away = normalize(m['awayTeam']['name'])

    # Candidate dates: UTC date from fdorg + day before (local time in Americas)
    utc_date   = m['utcDate'][:10]   # "2026-06-11"
    dt         = datetime.strptime(utc_date, '%Y-%m-%d')
    candidates = [
        dt.strftime('%Y%m%d'),
        (dt - timedelta(days=1)).strftime('%Y%m%d'),
    ]

    ra_match = None
    for date_str in candidates:
        ra_match = find_in_rapidapi(get_cached(date_str), home, away)
        if ra_match:
            break

    if ra_match is None:
        print(f'  Could not find {home} vs {away} in RapidAPI — will retry next run')
        continue

    event_id = ra_match.get('id')
    ensure_team(teams, home)
    ensure_team(teams, away)
    print(f'Processing fdorg#{fdorg_id} → event {event_id}: {home} vs {away}')

    try:
        time.sleep(0.4)
        stats_resp = api_get('/football-get-match-all-stats', {'eventid': event_id})
        process_stats(teams, home, away, stats_resp)
    except Exception as e:
        errors.append(f'stats {event_id}: {e}')
        print(f'  Stats error: {e}')

    try:
        time.sleep(0.4)
        detail_resp = api_get('/football-get-match-detail', {'eventid': event_id})
        process_events(teams, home, away, detail_resp)
    except Exception as e:
        errors.append(f'detail {event_id}: {e}')
        print(f'  Detail error: {e}')

    processed.add(fdorg_id)
    new_count += 1

# Save
data['processedFixtures'] = list(processed)
data['teams']             = teams
data['lastUpdated']       = datetime.now(timezone.utc).isoformat()

with open(stats_path, 'w') as f:
    json.dump(data, f, indent=2)

print(f'\nDone. Processed {new_count} new WC match(es). Total: {len(processed)}.')
if errors:
    print('Errors:')
    for e in errors:
        print(f'  {e}')
    sys.exit(1)
