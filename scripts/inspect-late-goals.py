"""
Show per-match late-goal counts for teams whose totals look suspicious.
Reads data/team-stats.json (matchStats) and data/matches.json (for team
+ fixture names), then prints a per-team breakdown.
"""
import json

matches = {m['id']: m for m in json.load(open('data/matches.json', encoding='utf-8'))['matches']}
stats   = json.load(open('data/team-stats.json', encoding='utf-8'))

# Reverse lookup: for each api-sports fxid in matchStats, we don't directly
# know the fdorg match id. Match by team-name pair instead.
def find_match(home, away):
    for m in matches.values():
        h = (m.get('homeTeam') or {}).get('name')
        a = (m.get('awayTeam') or {}).get('name')
        if {h, a} == {home, away}:
            return m
    return None

WATCH = ['Germany', 'Morocco', 'Paraguay', 'Netherlands', 'France', 'Switzerland']

for team in WATCH:
    total = 0
    print(f'\n=== {team} — late-goal breakdown ===')
    for fxid, by_team in stats.get('matchStats', {}).items():
        if team not in by_team:
            continue
        lg = by_team[team].get('lateGoals', 0)
        if lg == 0:
            continue
        opponent = next((t for t in by_team if t != team), '?')
        m = find_match(team, opponent)
        date = m.get('utcDate', '?')[:10] if m else '?'
        score = m.get('score', {}).get('fullTime', {}) if m else {}
        hs, as_ = score.get('home'), score.get('away')
        home_name = (m.get('homeTeam') or {}).get('name') if m else '?'
        result = f'{hs}-{as_}' if hs is not None else 'n/a'
        marker = f'({home_name} home)' if m else ''
        print(f'  fxid={fxid}  {date}  vs {opponent}  {result} {marker}  late={lg}')
        total += lg
    print(f'  Total late goals for {team}: {total}')
