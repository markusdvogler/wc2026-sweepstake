"""
Single-source WC 2026 data fetcher using api-sports.io.

Strategy (to stay under 100 calls/day on free tier):
  - Fixtures endpoint: every run (1 call) — fast/cheap live scores+status
  - /fixtures/events per live match: at most every 25 min (covers cards,
    goals, own goals, late goals — 4 of 5 stat-prize sources)
  - /fixtures/statistics per live match: at most every 55 min (fouls only)
  - Once a match goes FINISHED, do one final events+stats fetch, then cache

Writes data/matches.json (preserves football-data.org schema) and
data/team-stats.json.

Worst-case calls/day estimate (15-min cadence, 12h match window):
  fixtures 48 + yesterday-fixtures ~12 + events ~24 + stats ~12 = ~96
"""
import json, os, re, sys, time, unicodedata
import urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone, timedelta

API_KEY  = os.environ.get('APISPORTS_KEY', '')
BASE_URL = 'https://v3.football.api-sports.io'
HOST     = 'v3.football.api-sports.io'
WC_LEAGUE_ID = 1
WC_SEASON    = 2026
EVENTS_INTERVAL_MIN = 0      # fetch events on every run for live fixtures
STATS_INTERVAL_MIN  = 0      # fetch statistics on every run for live fixtures

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
    'Congo Democratic Republic':    'Congo DR',
    'Democratic Republic of Congo': 'Congo DR',
    'Curacao':                      'Curaçao',
    'Czech Republic':               'Czechia',
}

def normalize(name):
    return NAME_MAP.get(name, name) if name else ''

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
        'x-apisports-host': HOST,
        'x-apisports-key':  API_KEY,
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def get_response(resp):
    if not isinstance(resp, dict):
        return []
    errs = resp.get('errors') or {}
    if errs and ((isinstance(errs, list) and errs) or (isinstance(errs, dict) and any(errs.values()))):
        print(f'  API errors: {errs}')
    return resp.get('response') or []

STATUS_MAP = {
    'TBD': 'TIMED', 'NS': 'TIMED',
    '1H': 'IN_PLAY', '2H': 'IN_PLAY', 'ET': 'IN_PLAY', 'BT': 'IN_PLAY',
    'P': 'IN_PLAY', 'LIVE': 'IN_PLAY', 'INT': 'IN_PLAY',
    'HT': 'PAUSED',
    'FT': 'FINISHED', 'AET': 'FINISHED', 'PEN': 'FINISHED',
    'PST': 'POSTPONED', 'CANC': 'CANCELLED', 'ABD': 'CANCELLED',
    'AWD': 'CANCELLED', 'WO':  'CANCELLED',
}

def map_status(short):
    return STATUS_MAP.get(short or '', 'TIMED')

def parse_iso(s):
    if not s: return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return None

# ── Main ──────────────────────────────────────────────────────────────────────

if not API_KEY:
    print('ERROR: APISPORTS_KEY not set.')
    sys.exit(1)

now_utc = datetime.now(timezone.utc)

# Skip outside match window (18:00-08:00 CEST = 16:00-06:00 UTC).
# Saves API calls when no matches are likely live.
# Manual workflow_dispatch runs (via GITHUB_EVENT_NAME) always proceed.
event_name = os.environ.get('GITHUB_EVENT_NAME', '')
if event_name == 'schedule':
    hour = now_utc.hour
    in_window = hour >= 16 or hour < 6     # 16:00 UTC inclusive .. 06:00 UTC exclusive
    if not in_window:
        print(f'Outside match window (UTC hour={hour}). Skipping this run.')
        sys.exit(0)
api_calls = 0
errors = []

# Load fixture skeleton (football-data.org schema preserved)
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

# Per-fixture cache: each entry has the latest known stats from that match,
# plus timestamps so we can throttle re-fetches.
match_stats = stats_data.get('matchStats', {})   # {fxid: {team: {yc,rc,fouls,og,lg}}}
last_events = stats_data.get('lastEventsFetch', {})  # {fxid: iso}
last_stats  = stats_data.get('lastStatsFetch',  {})  # {fxid: iso}
finished_fully = set(stats_data.get('finishedFully', []))  # fxids done forever

def ensure_match_entry(fxid, home, away):
    fxid = str(fxid)
    if fxid not in match_stats:
        match_stats[fxid] = {}
    for t in (home, away):
        if t not in match_stats[fxid]:
            match_stats[fxid][t] = {
                'yellowCards': 0, 'redCards': 0,
                'fouls': 0, 'ownGoals': 0, 'lateGoals': 0
            }
    return match_stats[fxid]

# 1) Fetch WC fixtures for today UTC, plus yesterday UTC if we're early in the day
date_today = now_utc.strftime('%Y-%m-%d')
ra_fixtures = []
seen_ids = set()

# Any manual workflow_dispatch triggers a full backfill — fetches all WC
# fixtures and re-processes finished ones with current logic. Scheduled
# runs stay efficient (today+yesterday only).
backfill_mode = event_name == 'workflow_dispatch'

if backfill_mode:
    # One-shot: fetch ALL WC 2026 fixtures so finished matches missed by
    # earlier code revisions can be re-processed with current logic.
    try:
        time.sleep(0.3); api_calls += 1
        resp = api_get('/fixtures', {'league': WC_LEAGUE_ID, 'season': WC_SEASON})
        ra_fixtures = get_response(resp)
        seen_ids = {fx.get('fixture', {}).get('id') for fx in ra_fixtures}
        print(f'BACKFILL: pulled {len(ra_fixtures)} WC fixtures (all dates)')
    except Exception as e:
        errors.append(f'backfill fixtures: {e}')
        print(f'BACKFILL error: {e}')
else:
    dates_to_fetch = [date_today]
    if now_utc.hour < 6:                   # before 06:00 UTC = 08:00 CEST
        dates_to_fetch.append((now_utc - timedelta(days=1)).strftime('%Y-%m-%d'))

    for d in dates_to_fetch:
        try:
            time.sleep(0.3)
            api_calls += 1
            resp = api_get('/fixtures', {
                'league': WC_LEAGUE_ID, 'season': WC_SEASON, 'date': d
            })
            batch = get_response(resp)
            print(f'  {d}: {len(batch)} WC fixtures')
            for fx in batch:
                fid = fx.get('fixture', {}).get('id')
                if fid and fid not in seen_ids:
                    seen_ids.add(fid)
                    ra_fixtures.append(fx)
        except Exception as e:
            errors.append(f'fixtures {d}: {e}')
            print(f'  Error fetching {d}: {e}')

def fx_team_pair(fx):
    home = normalize((fx.get('teams', {}).get('home') or {}).get('name', ''))
    away = normalize((fx.get('teams', {}).get('away') or {}).get('name', ''))
    return home, away

def find_fixture(home_norm, away_norm):
    pairs = [(fx, *fx_team_pair(fx)) for fx in ra_fixtures]
    for fx, h, a in pairs:
        if h == home_norm and a == away_norm:
            return fx
    for fx, h, a in pairs:
        if fuzzy_eq(h, home_norm) and fuzzy_eq(a, away_norm):
            print(f'  Fuzzy: "{h}"≈"{home_norm}", "{a}"≈"{away_norm}"')
            return fx
    for fx, h, a in pairs:
        if fuzzy_eq(h, away_norm) and fuzzy_eq(a, home_norm):
            print(f'  Fuzzy (swapped): "{h}"≈"{away_norm}", "{a}"≈"{home_norm}"')
            return fx
    return None

# 2a) Populate empty knockout placeholders. Our matches.json was bootstrapped
# from fdorg with null teams for knockout fixtures. As the bracket fills in,
# api-sports knows the matchups before fdorg does. Match by stage + utcDate
# and copy team info onto the placeholder.
ROUND_TO_STAGE = {
    'round of 32':     'LAST_32',
    'round of 16':     'LAST_16',
    'quarter-finals':  'QUARTER_FINALS',
    'semi-finals':     'SEMI_FINALS',
    '3rd place final': 'THIRD_PLACE',
    'final':           'FINAL',
}
# Build name → fdorg team object lookup ONLY from group stage matches.
# If we include knockout matches, any prior buggy population that used
# api-sports IDs would poison the lookup on subsequent runs.
fd_team_by_name = {}
for m in fd_matches:
    if m.get('stage') != 'GROUP_STAGE':
        continue
    for side in ('homeTeam', 'awayTeam'):
        t = m.get(side) or {}
        n = t.get('name')
        if n and n not in fd_team_by_name:
            fd_team_by_name[n] = t

ko_filled = 0
for fx in ra_fixtures:
    teams = fx.get('teams') or {}
    h, a = teams.get('home') or {}, teams.get('away') or {}
    hname_raw, aname_raw = h.get('name'), a.get('name')
    if not hname_raw or not aname_raw:
        continue       # api-sports doesn't have the matchup yet either
    league_info = fx.get('league') or {}
    stage = ROUND_TO_STAGE.get((league_info.get('round') or '').lower())
    if not stage:
        continue       # not a knockout round
    fx_date = (fx.get('fixture') or {}).get('date', '')[:19]

    hname_norm = normalize(hname_raw)
    aname_norm = normalize(aname_raw)
    # Prefer fdorg team object (preserves id/tla/crest) if we know this team
    fd_home = fd_team_by_name.get(hname_norm)
    fd_away = fd_team_by_name.get(aname_norm)

    for m in fd_matches:
        if m.get('stage') != stage:
            continue
        m_date = (m.get('utcDate') or '')[:19].replace('Z', '')
        if fx_date != m_date:
            continue
        # Populate/correct the placeholder, preferring fdorg team info so
        # team IDs stay consistent across group and knockout stages.
        desired_home = fd_home or {
            'id':        h.get('id'),
            'name':      hname_norm,
            'shortName': hname_norm,
            'tla':       (h.get('name') or '')[:3].upper(),
            'crest':     h.get('logo'),
        }
        desired_away = fd_away or {
            'id':        a.get('id'),
            'name':      aname_norm,
            'shortName': aname_norm,
            'tla':       (a.get('name') or '')[:3].upper(),
            'crest':     a.get('logo'),
        }
        cur_home = m.get('homeTeam') or {}
        cur_away = m.get('awayTeam') or {}
        if (cur_home.get('id') == desired_home.get('id')
                and cur_away.get('id') == desired_away.get('id')):
            break   # already correct, no update needed
        m['homeTeam'] = desired_home
        m['awayTeam'] = desired_away
        m['lastUpdated'] = now_utc.isoformat()
        ko_filled += 1
        break
if ko_filled:
    print(f'Populated {ko_filled} knockout fixture placeholder(s).')

# 2b) Overlay live scores & statuses; figure out which matches need stat refreshes
needs_refresh = []   # list of (fxid_str, home_norm, away_norm, new_status)
updates = 0
for m in fd_matches:
    home = normalize(m.get('homeTeam', {}).get('name', ''))
    away = normalize(m.get('awayTeam', {}).get('name', ''))
    if not home or not away:
        continue
    fx = find_fixture(home, away)
    if not fx:
        continue

    short = fx.get('fixture', {}).get('status', {}).get('short')
    new_status = map_status(short)
    old_status = m.get('status', 'TIMED')
    goals = fx.get('goals', {}) or {}
    hs = goals.get('home'); as_ = goals.get('away')

    score = m.setdefault('score', {})
    full = score.setdefault('fullTime', {})
    changed = False
    if new_status != old_status:
        m['status'] = new_status; changed = True
    if hs is not None and full.get('home') != hs:
        full['home'] = hs; changed = True
    if as_ is not None and full.get('away') != as_:
        full['away'] = as_; changed = True
    if changed:
        m['lastUpdated'] = now_utc.isoformat()
        updates += 1

    if new_status in ('IN_PLAY', 'PAUSED', 'FINISHED'):
        fxid = str(fx.get('fixture', {}).get('id'))
        if fxid and fxid != 'None' and fxid not in finished_fully:
            needs_refresh.append((fxid, home, away, new_status))

print(f'Updated {updates} fixture(s) with live data.')
print(f'Candidates for stat refresh: {len(needs_refresh)}')

# 3) For each candidate, decide whether to fetch events / statistics
def time_since(iso_str):
    """Minutes since iso_str timestamp, or infinity if never set."""
    dt = parse_iso(iso_str)
    if not dt: return float('inf')
    return (now_utc - dt).total_seconds() / 60.0

# Helpers to find team in match_stats[fxid] regardless of name spelling
def resolve_team(entry, raw_name, home, away):
    n = normalize(raw_name)
    if n in (home, away): return n
    if fuzzy_eq(raw_name, home): return home
    if fuzzy_eq(raw_name, away): return away
    return None

for fxid, home, away, new_status in needs_refresh:
    ensure_match_entry(fxid, home, away)
    is_finished = (new_status == 'FINISHED')
    # Final-pass: if finished and we never did the events pass, force it
    need_events = (is_finished and fxid not in finished_fully) or \
                  (time_since(last_events.get(fxid)) >= EVENTS_INTERVAL_MIN)
    need_stats  = (is_finished and fxid not in finished_fully) or \
                  (time_since(last_stats.get(fxid))  >= STATS_INTERVAL_MIN)

    if need_events:
        try:
            time.sleep(0.3); api_calls += 1
            resp = api_get('/fixtures/events', {'fixture': fxid})
            # Reset per-match counts before re-aggregating (events return full match)
            for t in (home, away):
                match_stats[fxid][t] = {
                    'yellowCards': 0, 'redCards': 0,
                    'fouls': match_stats[fxid][t].get('fouls', 0),  # keep last stats
                    'ownGoals': 0, 'lateGoals': 0
                }
            for ev in get_response(resp):
                etype  = (ev.get('type')   or '').lower()
                detail = (ev.get('detail') or '').lower()
                comments = (ev.get('comments') or '').lower()
                tname_raw = (ev.get('team') or {}).get('name', '')
                tname = resolve_team(match_stats[fxid], tname_raw, home, away)
                if not tname:
                    continue
                t = ev.get('time') or {}
                elapsed = (t.get('elapsed') or 0) + (t.get('extra') or 0)
                if etype == 'card':
                    if 'yellow' in detail and 'second' not in detail:
                        match_stats[fxid][tname]['yellowCards'] += 1
                    elif 'red' in detail or 'second yellow' in detail:
                        match_stats[fxid][tname]['redCards'] += 1
                elif etype == 'goal':
                    # Detect own goal across detail or comments fields, plus
                    # standalone "OG" token (some feeds use it as a marker).
                    detail_toks = detail.split()
                    is_own_goal = (
                        'own goal' in detail
                        or 'own goal' in comments
                        or 'og' in detail_toks
                    )
                    if is_own_goal:
                        # api-sports attributes the goal event to the team
                        # that BENEFITED. The Deflectors prize should track
                        # the team that COMMITTED the own goal.
                        own_goal_team = away if tname == home else home if tname == away else None
                        if own_goal_team:
                            match_stats[fxid][own_goal_team]['ownGoals'] += 1
                    if elapsed >= 85:
                        match_stats[fxid][tname]['lateGoals'] += 1
            last_events[fxid] = now_utc.isoformat()
        except Exception as e:
            errors.append(f'events {fxid}: {e}')
            print(f'  Events error {fxid}: {e}')

    if need_stats:
        try:
            time.sleep(0.3); api_calls += 1
            resp = api_get('/fixtures/statistics', {'fixture': fxid})
            for team_block in get_response(resp):
                tname_raw = (team_block.get('team') or {}).get('name', '')
                tname = resolve_team(match_stats[fxid], tname_raw, home, away)
                if not tname:
                    continue
                for stat in team_block.get('statistics') or []:
                    stype = (stat.get('type') or '').lower()
                    val = stat.get('value')
                    if val is None: continue
                    try: ival = int(val)
                    except (ValueError, TypeError):
                        try: ival = int(str(val).rstrip('%'))
                        except: continue
                    if 'foul' in stype:
                        match_stats[fxid][tname]['fouls'] = ival
            last_stats[fxid] = now_utc.isoformat()
        except Exception as e:
            errors.append(f'stats {fxid}: {e}')
            print(f'  Stats error {fxid}: {e}')

    if is_finished and need_events and need_stats:
        finished_fully.add(fxid)

# 4) Aggregate per-match stats → per-team totals
team_totals = {}
def ensure_team(name):
    if name not in team_totals:
        team_totals[name] = {
            'yellowCards': 0, 'redCards': 0,
            'fouls': 0, 'ownGoals': 0, 'lateGoals': 0
        }

# Group-stage-only aggregation. All Prize Tracker prizes are for group
# stage only — knockout stats (cards, fouls, own goals, late goals)
# must NOT roll up into team totals.
fixture_stages = stats_data.get('fixtureStages', {})
# Update fixture_stages from this run's ra_fixtures (backfill = full list,
# normal = today/yesterday).
for fx in ra_fixtures:
    fxid = str((fx.get('fixture') or {}).get('id') or '')
    if not fxid:
        continue
    round_str = ((fx.get('league') or {}).get('round') or '').lower()
    if 'group stage' in round_str:
        fixture_stages[fxid] = 'GROUP_STAGE'
    elif round_str in ROUND_TO_STAGE:
        fixture_stages[fxid] = ROUND_TO_STAGE[round_str]

for fxid, by_team in match_stats.items():
    if fixture_stages.get(fxid) != 'GROUP_STAGE':
        continue   # skip knockout / unknown-stage fixtures
    for tname, vals in by_team.items():
        ensure_team(tname)
        for k in team_totals[tname]:
            team_totals[tname][k] += vals.get(k, 0)

# 5) Fetch standings (1 call) — includes qualification status per team
#    (description="Round of 32" etc.). Drives The Upgraders prize logic.
standings_path = 'data/standings.json'
try:
    time.sleep(0.3); api_calls += 1
    resp = api_get('/standings', {'league': WC_LEAGUE_ID, 'season': WC_SEASON})
    standings_resp = get_response(resp)
    # Flatten into a simple shape: [{team, group, rank, points, description}]
    flat = []
    for league_block in standings_resp:
        groups = (league_block.get('league') or {}).get('standings') or []
        for grp in groups:
            for row in grp:
                flat.append({
                    'team':        (row.get('team') or {}).get('name'),
                    'group':       row.get('group'),
                    'rank':        row.get('rank'),
                    'points':      row.get('points'),
                    'description': row.get('description'),
                })
    standings_out = {'lastUpdated': now_utc.isoformat(), 'rows': flat}
    with open(standings_path, 'w', encoding='utf-8') as f:
        json.dump(standings_out, f, indent=2, ensure_ascii=False)
    print(f'Standings: {len(flat)} rows.')
except Exception as e:
    errors.append(f'standings: {e}')
    print(f'Standings error: {e}')

# 6) Persist
fixtures['lastUpdated'] = now_utc.isoformat()
with open(matches_path, 'w', encoding='utf-8') as f:
    json.dump(fixtures, f, indent=2, ensure_ascii=False)

stats_data['matchStats']      = match_stats
stats_data['lastEventsFetch'] = last_events
stats_data['lastStatsFetch']  = last_stats
stats_data['finishedFully']   = sorted(finished_fully)
stats_data['fixtureStages']   = fixture_stages
stats_data['teams']           = team_totals
stats_data['lastUpdated']     = now_utc.isoformat()
with open(stats_path, 'w', encoding='utf-8') as f:
    json.dump(stats_data, f, indent=2, ensure_ascii=False)

print(f'\nDone. API calls this run: {api_calls}. '
      f'Live updates: {updates}. Teams with stats: {len(team_totals)}.')
if errors:
    print('Errors:')
    for e in errors:
        print(f'  {e}')
    sys.exit(1)
