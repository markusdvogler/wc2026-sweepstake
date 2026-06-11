"""
Unified WC 2026 data fetcher from Free API Live Football Data (RapidAPI).

Replaces the old football-data.org pipeline. Each run:
  1. Fetches today's + yesterday's matches by date (timezone-safe)
  2. Overlays live score + status onto data/matches.json (preserves schema)
  3. For matches newly marked FINISHED, fetches stats + detail
  4. Updates data/team-stats.json

Runs every 15 min during match window (20:00–08:00 CEST) via
.github/workflows/fetch-live.yml. ~50 API calls/day max.
"""
import json, os, re, sys, time, unicodedata
import urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

API_KEY  = os.environ.get('RAPIDAPI_KEY', '')
BASE_URL = 'https://free-api-live-football-data.p.rapidapi.com'
HOST     = 'free-api-live-football-data.p.rapidapi.com'

# Map RapidAPI team names to our canonical names (those used in matches.json)
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

# Token-based fuzzy matching — self-healing fallback for unmapped variants.
_NOISE_TOKENS = {'the', 'and', 'of', 'fc', 'national', 'team', 'republic', 'islands'}

def _tokenize(name):
    nfkd = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode('ascii')
    return set(re.findall(r'[a-z0-9]+', nfkd.lower())) - _NOISE_TOKENS

def fuzzy_eq(a, b):
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return False
    if ta == tb or ta <= tb or tb <= ta:
        return True
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

def fetch_matches_for_date(date_yyyymmdd):
    """Fetch ALL matches (any status) from RapidAPI for a given date."""
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
    return all_matches

def ra_status_string(ra_match):
    """Convert RapidAPI status dict to fdorg-style string. matches.json schema."""
    s = ra_match.get('status') or {}
    if not isinstance(s, dict):
        return 'TIMED'
    if s.get('cancelled'):
        return 'CANCELLED'
    if s.get('finished'):
        return 'FINISHED'
    if s.get('started'):
        return 'IN_PLAY'
    return 'TIMED'

def ra_score(ra_match, side):
    """Extract score for 'home' or 'away' from RapidAPI match. Returns int or None."""
    side_obj = ra_match.get(side) or {}
    # Try multiple field names this API uses
    for key in ('score', 'goals'):
        val = side_obj.get(key)
        if val is not None and val != '':
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    # Some responses put scores under match-level 'score'
    score_obj = ra_match.get('score') or {}
    if isinstance(score_obj, dict):
        val = score_obj.get(side) or score_obj.get(f'{side}Score')
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return None

def find_in_rapidapi(ra_matches, home_norm, away_norm):
    """Find RapidAPI match that matches home/away team names (with fuzzy fallback)."""
    candidates = []
    for m in ra_matches:
        h = m.get('home', {}) or {}
        a = m.get('away', {}) or {}
        ra_home = normalize(h.get('longName') or h.get('name', ''))
        ra_away = normalize(a.get('longName') or a.get('name', ''))
        candidates.append((m, ra_home, ra_away))

    for m, rh, ra in candidates:
        if rh == home_norm and ra == away_norm:
            return m
    for m, rh, ra in candidates:
        if fuzzy_eq(rh, home_norm) and fuzzy_eq(ra, away_norm):
            print(f'  Fuzzy matched: "{rh}" ≈ "{home_norm}", "{ra}" ≈ "{away_norm}"')
            return m
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

def ensure_team(teams, name):
    if name not in teams:
        teams[name] = {
            'yellowCards': 0, 'redCards': 0,
            'fouls': 0, 'ownGoals': 0, 'lateGoals': 0
        }

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

# Load existing fixtures (schema preserved from football-data.org era)
matches_path = 'data/matches.json'
try:
    with open(matches_path, encoding='utf-8') as f:
        fixtures = json.load(f)
    fd_matches = fixtures.get('matches', [])
except Exception as e:
    print(f'ERROR: could not load {matches_path}: {e}')
    sys.exit(1)

# Load stats state
stats_path = 'data/team-stats.json'
try:
    with open(stats_path, encoding='utf-8') as f:
        stats_data = json.load(f)
except Exception:
    stats_data = {}

processed = set(stats_data.get('processedFixtures', []))  # fdorg match IDs
teams     = stats_data.get('teams', {})
errors    = []

# Determine which dates to query: today (UTC) and yesterday (covers timezone wrap)
now_utc    = datetime.now(timezone.utc)
date_today = now_utc.strftime('%Y%m%d')
date_yest  = (now_utc - timedelta(days=1)).strftime('%Y%m%d')

print(f'Fetching matches for {date_today} and {date_yest}...')
ra_matches = []
for d in (date_today, date_yest):
    try:
        time.sleep(0.4)
        batch = fetch_matches_for_date(d)
        print(f'  {d}: {len(batch)} matches')
        ra_matches.extend(batch)
    except Exception as e:
        errors.append(f'by-date {d}: {e}')
        print(f'  Error fetching {d}: {e}')

# Overlay live scores + statuses onto our fixture list
updates = 0
newly_finished = []
for m in fd_matches:
    home = normalize(m.get('homeTeam', {}).get('name', ''))
    away = normalize(m.get('awayTeam', {}).get('name', ''))
    if not home or not away:
        continue

    ra = find_in_rapidapi(ra_matches, home, away)
    if not ra:
        continue   # not in today/yesterday window — leave as-is

    new_status = ra_status_string(ra)
    old_status = m.get('status', 'TIMED')
    new_home_score = ra_score(ra, 'home')
    new_away_score = ra_score(ra, 'away')

    score = m.setdefault('score', {})
    full = score.setdefault('fullTime', {})
    changed = False

    if new_status != old_status:
        m['status'] = new_status
        changed = True
    if new_home_score is not None and full.get('home') != new_home_score:
        full['home'] = new_home_score
        changed = True
    if new_away_score is not None and full.get('away') != new_away_score:
        full['away'] = new_away_score
        changed = True

    if changed:
        m['lastUpdated'] = now_utc.isoformat()
        updates += 1

    # Track newly-finished matches for stats fetch
    if (new_status == 'FINISHED'
            and m.get('id') not in processed
            and ra.get('id')):
        newly_finished.append((m, ra))

print(f'Updated {updates} fixture(s) with live data.')
print(f'Newly finished, awaiting stats: {len(newly_finished)}')

# Diagnostic: if no matches found, dump what RapidAPI actually returned so we
# can see whether the WC games are in there at all and what names they use.
if updates == 0 and ra_matches:
    print('\n--- DIAGNOSTIC: RapidAPI returned these matches ---')
    for m in ra_matches:
        h = m.get('home', {}) or {}
        a = m.get('away', {}) or {}
        league = (m.get('tournament', {}) or m.get('league', {}) or {}).get('name') or m.get('leagueName') or m.get('leagueId') or '?'
        hname = h.get('longName') or h.get('name', '?')
        aname = a.get('longName') or a.get('name', '?')
        st = m.get('status', {})
        sstr = 'FIN' if (isinstance(st, dict) and st.get('finished')) else 'LIVE' if (isinstance(st, dict) and st.get('started')) else 'UPC'
        print(f'  [{sstr}] {hname} vs {aname}  (league: {league})')
    print('--- end diagnostic ---\n')

# Pull stats + detail for newly finished matches
new_count = 0
for m, ra in newly_finished:
    fdorg_id = m['id']
    event_id = ra.get('id')
    home = normalize(m['homeTeam']['name'])
    away = normalize(m['awayTeam']['name'])
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
        continue   # don't mark processed if stats failed

    try:
        time.sleep(0.4)
        detail_resp = api_get('/football-get-match-detail', {'eventid': event_id})
        process_events(teams, home, away, detail_resp)
    except Exception as e:
        errors.append(f'detail {event_id}: {e}')
        print(f'  Detail error: {e}')

    processed.add(fdorg_id)
    new_count += 1

# Persist updates
fixtures['lastUpdated'] = now_utc.isoformat()
with open(matches_path, 'w', encoding='utf-8') as f:
    json.dump(fixtures, f, indent=2, ensure_ascii=False)

stats_data['processedFixtures'] = list(processed)
stats_data['teams']             = teams
stats_data['lastUpdated']       = now_utc.isoformat()
with open(stats_path, 'w', encoding='utf-8') as f:
    json.dump(stats_data, f, indent=2, ensure_ascii=False)

print(f'\nDone. Live updates: {updates}. New stats: {new_count}. Total processed: {len(processed)}.')
if errors:
    print('Errors:')
    for e in errors:
        print(f'  {e}')
    sys.exit(1)
