"""
Fetches match statistics from Free API Live Football Data (RapidAPI/Creativesdev).
Endpoints used:
  /football-get-all-leagues
  /football-get-all-matches-by-league?leagueid={id}
  /football-get-match-all-stats?eventid={id}
  /football-get-match-detail?eventid={id}

Saves aggregated per-team stats to data/team-stats.json (incremental).
"""
import json, os, sys, time
import urllib.request, urllib.parse
from datetime import datetime, timezone

API_KEY  = os.environ.get('RAPIDAPI_KEY', '')
BASE_URL = 'https://free-api-live-football-data.p.rapidapi.com'
HOST     = 'free-api-live-football-data.p.rapidapi.com'

# Map API team names -> canonical names in our teams.json
NAME_MAP = {
    'Korea Republic':          'South Korea',
    'Republic of Korea':       'South Korea',
    'IR Iran':                 'Iran',
    'Cape Verde':              'Cape Verde Islands',
    "Cote d'Ivoire":           'Ivory Coast',
    "Côte d'Ivoire":           'Ivory Coast',
    'Ivory Coast':             'Ivory Coast',
    'Bosnia':                  'Bosnia-Herzegovina',
    'Bosnia and Herzegovina':  'Bosnia-Herzegovina',
    'Turkiye':                 'Turkey',
    'Türkiye':                 'Turkey',
    'USA':                     'United States',
    'United States of America':'United States',
    'DR Congo':                'Congo DR',
    'Democratic Republic of Congo': 'Congo DR',
    'Curacao':                 'Curaçao',
    'New Zealand':             'New Zealand',
}

FINISHED_STATUSES = {
    'finished', 'ft', 'aet', 'pen', 'ap',
    'after extra time', 'after penalties', 'full-time', 'full time'
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

def find_world_cup_league(data):
    """Return cached league ID or discover it from the leagues endpoint."""
    if data.get('leagueId'):
        print(f"Using cached World Cup league ID: {data['leagueId']}")
        return data['leagueId']

    print('Fetching all leagues to find FIFA World Cup 2026...')
    resp = api_get('/football-get-all-leagues')

    # The response might be a list or a dict with a key containing the list
    if isinstance(resp, list):
        leagues = resp
    elif isinstance(resp, dict):
        for key in ('response', 'data', 'result', 'leagues', 'items'):
            if key in resp and isinstance(resp[key], list):
                leagues = resp[key]
                break
        else:
            # Last resort: look for any list value
            leagues = next((v for v in resp.values() if isinstance(v, list)), [])
    else:
        leagues = []

    def extract_name_and_id(item):
        """Try various field name patterns to get league name and ID."""
        if not isinstance(item, dict):
            return '', None
        name = (item.get('name') or item.get('leagueName') or
                item.get('league', {}).get('name', '') or
                item.get('tournament', {}).get('name', '') or '')
        lid  = (item.get('id') or item.get('leagueId') or
                item.get('league', {}).get('id') or
                item.get('tournament', {}).get('id'))
        return str(name).lower(), lid

    # First pass: look for "world cup" with 2026 somewhere nearby
    for item in leagues:
        name, lid = extract_name_and_id(item)
        if 'world cup' in name and lid is not None:
            item_str = json.dumps(item)
            if '2026' in item_str or '2026' in name:
                print(f'  Found: "{name}" → ID={lid}')
                return lid

    # Second pass: any "world cup"
    for item in leagues:
        name, lid = extract_name_and_id(item)
        if 'world cup' in name and lid is not None:
            print(f'  Found: "{name}" → ID={lid}')
            return lid

    # Debug output so we can manually find the right ID
    print('  WARNING: Could not auto-detect FIFA World Cup league.')
    print(f'  Total leagues found: {len(leagues)}')
    if leagues:
        print('  Sample entries (first 10):')
        for item in leagues[:10]:
            name, lid = extract_name_and_id(item)
            print(f'    id={lid}  name={name}')
    return None

def get_matches(league_id):
    """Fetch all fixtures for the given league ID."""
    resp = api_get('/football-get-all-matches-by-league', {'leagueid': league_id})
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for key in ('response', 'data', 'result', 'events', 'matches', 'fixtures', 'items'):
            if key in resp and isinstance(resp[key], list):
                return resp[key]
    return []

def get_event_id(match):
    """Extract the event/match ID from a match record."""
    return (match.get('id') or match.get('eventId') or match.get('event_id') or
            match.get('fixture', {}).get('id'))

def get_status(match):
    """Extract and normalise the match status string."""
    raw = (match.get('status') or match.get('matchStatus') or
           match.get('fixture', {}).get('status', {}).get('short', '') or '')
    if isinstance(raw, dict):
        raw = raw.get('type') or raw.get('short') or raw.get('name') or ''
    return str(raw).strip().lower()

def get_team_names(match):
    """Return (home_name, away_name) from a match record."""
    # Pattern A: homeTeam / awayTeam objects with name
    if 'homeTeam' in match and isinstance(match['homeTeam'], dict):
        home = match['homeTeam'].get('name', '')
        away = match.get('awayTeam', {}).get('name', '')
        return home, away
    # Pattern B: home / away objects
    if 'home' in match and isinstance(match['home'], dict):
        home = match['home'].get('name', '')
        away = match.get('away', {}).get('name', '')
        return home, away
    # Pattern C: flat strings
    home = match.get('homeName') or match.get('home_team') or match.get('homeTeamName', '')
    away = match.get('awayName') or match.get('away_team') or match.get('awayTeamName', '')
    return home, away

def parse_int(val):
    try:
        return int(val or 0)
    except (ValueError, TypeError):
        return 0

def process_stats(teams, home, away, resp):
    """
    Extract fouls, yellow cards, red cards from /football-get-match-all-stats.
    The response is typically a list of two objects (one per team) or a dict
    with 'home'/'away' keys, each containing a list of stat entries.
    """
    def apply_stats(tname, stat_list):
        ensure_team(teams, tname)
        if not isinstance(stat_list, list):
            return
        for s in stat_list:
            if not isinstance(s, dict):
                continue
            key  = str(s.get('name') or s.get('type') or s.get('key') or '').lower()
            val  = parse_int(s.get('value') or s.get('count') or s.get('stat') or 0)
            if 'yellow' in key:
                teams[tname]['yellowCards'] += val
            elif 'red card' in key or key == 'red cards':
                teams[tname]['redCards'] += val
            elif 'foul' in key:
                teams[tname]['fouls'] += val

    # Pattern A: list of {team: {name}, statistics: [...]}
    if isinstance(resp, list):
        for item in resp:
            if not isinstance(item, dict):
                continue
            tname_raw = (item.get('team', {}).get('name') or
                         item.get('teamName') or item.get('name', ''))
            tname = normalize(str(tname_raw))
            stats = item.get('statistics') or item.get('stats') or []
            apply_stats(tname, stats)
        return

    if not isinstance(resp, dict):
        return

    # Pattern B: {home: {stats: [...]}, away: {stats: [...]}}
    for key, tname in (('home', home), ('away', away)):
        if key in resp and isinstance(resp[key], dict):
            stat_list = resp[key].get('statistics') or resp[key].get('stats') or []
            apply_stats(tname, stat_list)

    # Pattern C: wrapped in response/data key
    for wrap_key in ('response', 'data', 'result'):
        if wrap_key in resp and isinstance(resp[wrap_key], list):
            for item in resp[wrap_key]:
                if not isinstance(item, dict):
                    continue
                tname_raw = (item.get('team', {}).get('name') or
                             item.get('teamName') or item.get('name', ''))
                tname = normalize(str(tname_raw))
                stats = item.get('statistics') or item.get('stats') or []
                apply_stats(tname, stats)
            return

def process_events(teams, home, away, resp):
    """
    Extract own goals and late goals (minute >= 85) from /football-get-match-detail.
    """
    incidents = []
    if isinstance(resp, list):
        incidents = resp
    elif isinstance(resp, dict):
        for key in ('incidents', 'events', 'goals', 'timeline', 'data', 'response'):
            if key in resp and isinstance(resp[key], list):
                incidents = resp[key]
                break

    for inc in incidents:
        if not isinstance(inc, dict):
            continue

        # Determine event type
        etype  = str(inc.get('type') or inc.get('incidentType') or '').lower()
        detail = str(inc.get('detail') or inc.get('incidentClass') or inc.get('description') or '').lower()

        if 'goal' not in etype and 'goal' not in detail:
            continue

        # Determine owning team
        is_home = inc.get('isHome')
        team_raw = (inc.get('team', {}).get('name') if isinstance(inc.get('team'), dict)
                    else inc.get('teamName') or inc.get('team', ''))
        if team_raw:
            tname = normalize(str(team_raw))
        elif is_home is True:
            tname = home
        elif is_home is False:
            tname = away
        else:
            continue

        ensure_team(teams, tname)

        # Own goal?
        own_goal = ('own' in detail or inc.get('isOwnGoal') or
                    'own goal' in str(inc).lower())
        if own_goal:
            teams[tname]['ownGoals'] += 1

        # Late goal (minute >= 85)?
        elapsed = parse_int(inc.get('time') or inc.get('minute') or
                            inc.get('incidentTime') or
                            (inc.get('time', {}).get('elapsed') if isinstance(inc.get('time'), dict) else 0))
        extra   = parse_int(inc.get('addedTime') or inc.get('injury_time') or
                            (inc.get('time', {}).get('extra') if isinstance(inc.get('time'), dict) else 0))
        minute  = elapsed + extra
        if minute >= 85:
            teams[tname]['lateGoals'] += 1


# ── Main ──────────────────────────────────────────────────────────────────────

if not API_KEY:
    print('ERROR: RAPIDAPI_KEY environment variable not set.')
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

# Step 1: Resolve league ID
league_id = find_world_cup_league(data)
if not league_id:
    print('ERROR: FIFA World Cup 2026 league not found. Add it manually as leagueId in team-stats.json.')
    sys.exit(1)
data['leagueId'] = league_id

# Step 2: Get all fixtures
print(f'Fetching fixtures for league {league_id}...')
time.sleep(0.3)
matches = get_matches(league_id)
print(f'  Found {len(matches)} total fixtures')

# Step 3: Process new finished matches
new_count = 0
for match in matches:
    event_id = get_event_id(match)
    status   = get_status(match)

    if status not in FINISHED_STATUSES:
        continue
    if event_id is None or event_id in processed:
        continue

    home_raw, away_raw = get_team_names(match)
    if not home_raw or not away_raw:
        print(f'  Skipping {event_id}: could not determine team names')
        continue

    home = normalize(home_raw)
    away = normalize(away_raw)
    ensure_team(teams, home)
    ensure_team(teams, away)
    print(f'  Processing {event_id}: {home} vs {away}  [{status}]')

    # Stats (fouls, cards)
    try:
        time.sleep(0.4)
        stats_resp = api_get('/football-get-match-all-stats', {'eventid': event_id})
        process_stats(teams, home, away, stats_resp)
    except Exception as e:
        errors.append(f'stats {event_id}: {e}')
        print(f'    Stats error: {e}')

    # Detail (own goals, late goals)
    try:
        time.sleep(0.4)
        detail_resp = api_get('/football-get-match-detail', {'eventid': event_id})
        process_events(teams, home, away, detail_resp)
    except Exception as e:
        errors.append(f'detail {event_id}: {e}')
        print(f'    Detail error: {e}')

    processed.add(event_id)
    new_count += 1

# Step 4: Save
data['processedFixtures'] = list(processed)
data['teams']             = teams
data['lastUpdated']       = datetime.now(timezone.utc).isoformat()

with open(stats_path, 'w') as f:
    json.dump(data, f, indent=2)

print(f'\nDone. Processed {new_count} new fixtures. Total processed: {len(processed)}.')
if errors:
    print('Errors encountered:')
    for e in errors:
        print(f'  {e}')
    sys.exit(1)
