"""
Fetches WC 2026 match statistics from Free API Live Football Data (RapidAPI).

Strategy: fetch all football matches for today + yesterday by date, filter for
WC 2026 (leagueId 914609), then for each newly-finished match pull full-time
stats and event details.

Runs hourly via .github/workflows/fetch-stats.yml to stay within the
100 requests/day free-tier limit.
"""
import json, os, sys, time
import urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

API_KEY          = os.environ.get('RAPIDAPI_KEY', '')
BASE_URL         = 'https://free-api-live-football-data.p.rapidapi.com'
HOST             = 'free-api-live-football-data.p.rapidapi.com'
WORLD_CUP_LEAGUE = 914609   # FIFA World Cup 2026 – confirmed from live API data

# Map API team names → canonical names used in teams.json
NAME_MAP = {
    'Korea Republic':           'South Korea',
    'Republic of Korea':        'South Korea',
    'IR Iran':                  'Iran',
    'Cape Verde':               'Cape Verde Islands',
    "Cote d'Ivoire":            'Ivory Coast',
    "Côte d'Ivoire":            'Ivory Coast',
    'Bosnia':                   'Bosnia-Herzegovina',
    'Bosnia and Herzegovina':   'Bosnia-Herzegovina',
    'Turkiye':                  'Turkey',
    'Türkiye':                  'Turkey',
    'USA':                      'United States',
    'United States of America': 'United States',
    'DR Congo':                 'Congo DR',
    'Democratic Republic of Congo': 'Congo DR',
    'Curacao':                  'Curaçao',
}

def normalize(name):
    return NAME_MAP.get(name, name)

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

def get_matches_for_date(date_str):
    """
    Fetch all matches on date_str (YYYYMMDD), return only finished WC ones.
    Confirmed response: {status, response: {matches: [...]}}
    Confirmed match structure: {id, leagueId, home: {name, longName}, away: {...},
                                 status: {finished: bool, started: bool, ...}}
    """
    resp = api_get('/football-get-matches-by-date', {'date': date_str})
    all_matches = []
    if isinstance(resp, dict):
        inner = resp.get('response', {})
        if isinstance(inner, dict):
            all_matches = inner.get('matches', [])
        elif isinstance(inner, list):
            all_matches = inner
    elif isinstance(resp, list):
        all_matches = resp

    wc = [m for m in all_matches
          if m.get('leagueId') == WORLD_CUP_LEAGUE
          and isinstance(m.get('status'), dict)
          and m['status'].get('finished')]
    return wc

def parse_int(val):
    try:
        return int(val or 0)
    except (ValueError, TypeError):
        return 0

def process_stats(teams, home, away, resp):
    """
    Extract fouls, yellow/red cards from /football-get-match-all-stats.
    Handles two common response shapes:
      A) list of {team: {name}, statistics: [{name, value}]}
      B) {home: {statistics: [...]}, away: {...}}  (or wrapped in response.*)
    """
    def apply(tname, stat_list):
        ensure_team(teams, tname)
        for s in (stat_list or []):
            if not isinstance(s, dict):
                continue
            key = str(s.get('name') or s.get('type') or s.get('key') or '').lower()
            val = parse_int(s.get('value') or s.get('count') or 0)
            if 'yellow' in key:
                teams[tname]['yellowCards'] += val
            elif 'red card' in key or key in ('red cards', 'red'):
                teams[tname]['redCards'] += val
            elif 'foul' in key:
                teams[tname]['fouls'] += val

    # Unwrap a possible outer dict
    data = resp
    if isinstance(resp, dict):
        for wrap in ('response', 'data', 'result'):
            if wrap in resp:
                data = resp[wrap]
                break

    # Shape A: list of per-team objects
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            traw = (item.get('team', {}).get('name') if isinstance(item.get('team'), dict)
                    else item.get('teamName') or item.get('name', ''))
            apply(normalize(str(traw)), item.get('statistics') or item.get('stats') or [])
        return

    # Shape B: {home: {...}, away: {...}}
    if isinstance(data, dict):
        for key, tname in (('home', home), ('away', away)):
            if key in data and isinstance(data[key], dict):
                apply(tname, data[key].get('statistics') or data[key].get('stats') or [])

def process_events(teams, home, away, resp):
    """
    Extract own goals and late goals (≥85 min) from /football-get-match-detail.
    """
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

        # Determine team
        is_home = inc.get('isHome')
        traw    = (inc.get('team', {}).get('name') if isinstance(inc.get('team'), dict)
                   else inc.get('teamName') or inc.get('team', ''))
        if traw:
            tname = normalize(str(traw))
        elif is_home is True:
            tname = home
        elif is_home is False:
            tname = away
        else:
            continue

        ensure_team(teams, tname)

        if ('own' in detail or inc.get('isOwnGoal') or
                'own goal' in str(inc).lower()):
            teams[tname]['ownGoals'] += 1

        elapsed = parse_int(
            inc.get('time') if not isinstance(inc.get('time'), dict) else None
            or inc.get('minute') or inc.get('incidentTime')
            or (inc.get('time', {}).get('elapsed') if isinstance(inc.get('time'), dict) else 0))
        extra = parse_int(
            inc.get('addedTime') or inc.get('injury_time')
            or (inc.get('time', {}).get('extra') if isinstance(inc.get('time'), dict) else 0))
        if elapsed + extra >= 85:
            teams[tname]['lateGoals'] += 1


# ── Main ──────────────────────────────────────────────────────────────────────

if not API_KEY:
    print('ERROR: RAPIDAPI_KEY not set.')
    sys.exit(1)

stats_path = 'data/team-stats.json'
try:
    with open(stats_path) as f:
        data = json.load(f)
except Exception:
    data = {}

processed = set(data.get('processedFixtures', []))
teams     = data.get('teams', {})
errors    = []

# Dates to check: today + yesterday (catches matches that finish after midnight UTC)
now       = datetime.now(timezone.utc)
dates     = [(now - timedelta(days=i)).strftime('%Y%m%d') for i in range(2)]

wc_matches = []
for d in dates:
    print(f'Fetching WC matches for {d}...')
    try:
        found = get_matches_for_date(d)
        print(f'  {len(found)} finished WC match(es)')
        wc_matches.extend(found)
    except Exception as e:
        errors.append(f'date {d}: {e}')
        print(f'  Error: {e}')
    time.sleep(0.4)

new_count = 0
for match in wc_matches:
    event_id = match.get('id')
    if event_id is None or event_id in processed:
        continue

    home_obj = match.get('home', {})
    away_obj = match.get('away', {})
    home = normalize(home_obj.get('longName') or home_obj.get('name', ''))
    away = normalize(away_obj.get('longName') or away_obj.get('name', ''))
    if not home or not away:
        continue

    ensure_team(teams, home)
    ensure_team(teams, away)
    print(f'Processing {event_id}: {home} vs {away}')

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

    processed.add(event_id)
    new_count += 1

data['processedFixtures'] = list(processed)
data['teams']             = teams
data['lastUpdated']       = now.isoformat()

with open(stats_path, 'w') as f:
    json.dump(data, f, indent=2)

print(f'\nDone. Processed {new_count} new match(es). Total: {len(processed)}.')
if errors:
    print('Errors:')
    for e in errors:
        print(f'  {e}')
    sys.exit(1)
