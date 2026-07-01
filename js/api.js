// Data wrapper — reads static JSON files updated by GitHub Actions (RapidAPI).
// matches.json contains the WC fixture skeleton with live scores + status
// overlaid by the fetch-rapidapi.py script. Standings are computed client-side.

const CACHE_TTL = 5 * 60 * 1000;
const cache = {};

async function staticFetch(file) {
  const now = Date.now();
  if (cache[file] && now - cache[file].ts < CACHE_TTL) return cache[file].data;
  // Cache-bust at minute granularity: forces both matches.json and
  // team-stats.json to hit the CDN with the same query string within the
  // same minute, so they stay in sync rather than drifting independently.
  const v = Math.floor(now / 60000);
  const res = await fetch(`${file}?v=${v}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`File error ${res.status}`);
  const data = await res.json();
  cache[file] = { data, ts: now };
  return data;
}

const API = {
  hasKey() { return true; },

  async getMatches() {
    return staticFetch('data/matches.json');
  },

  async getEventStats() {
    return staticFetch('data/team-stats.json');
  },

  async getTeamStats() {
    const [{ matches }, eventStats] = await Promise.all([
      this.getMatches(),
      this.getEventStats().catch(() => ({ teams: {} }))
    ]);
    const extStats = eventStats.teams || {};
    const stats = {};

    function ensureTeam(id, name, shortName) {
      if (!stats[id]) {
        stats[id] = {
          id, name, shortName,
          played: 0, appeared: 0, wins: 0, draws: 0, losses: 0,
          goalsFor: 0, goalsAgainst: 0, points: 0,
          yellowCards: 0, redCards: 0, ownGoals: 0,
          zeroZeroMatches: 0, lateGoals: 0,
          biggestDefeat: 0, biggestDefeatScore: null, fouls: 0
        };
      }
    }

    for (const m of matches) {
      // All Prize Tracker prizes are group-stage-only; knockout results
      // must not contribute to goals/points/cards/etc totals.
      if (m.stage !== 'GROUP_STAGE') continue;
      const isFinished = m.status === 'FINISHED';
      const isLive     = m.status === 'IN_PLAY' || m.status === 'PAUSED';
      if (!isFinished && !isLive) continue;

      const h = m.homeTeam, a = m.awayTeam;
      const hs = m.score?.fullTime?.home, as = m.score?.fullTime?.away;
      if (hs === null || hs === undefined || as === null || as === undefined) continue;

      ensureTeam(h.id, h.name, h.shortName);
      ensureTeam(a.id, a.name, a.shortName);

      // `appeared` includes live matches; `played` only finished ones
      stats[h.id].appeared++;
      stats[a.id].appeared++;

      // Count goals + provisional points for both live and finished
      stats[h.id].goalsFor += hs;
      stats[h.id].goalsAgainst += as;
      stats[a.id].goalsFor += as;
      stats[a.id].goalsAgainst += hs;

      if (hs > as) { stats[h.id].wins++; stats[h.id].points += 3; stats[a.id].losses++; }
      else if (hs < as) { stats[a.id].wins++; stats[a.id].points += 3; stats[h.id].losses++; }
      else { stats[h.id].draws++; stats[h.id].points++; stats[a.id].draws++; stats[a.id].points++; }

      // "Played" only increments for fully completed matches
      if (isFinished) {
        stats[h.id].played++;
        stats[a.id].played++;

        // Final-only stats: 0-0 match and biggest defeat can't be determined until full-time
        if (hs === 0 && as === 0) { stats[h.id].zeroZeroMatches++; stats[a.id].zeroZeroMatches++; }
        if (hs > as) {
          const diff = hs - as;
          if (diff > stats[a.id].biggestDefeat) {
            stats[a.id].biggestDefeat = diff;
            stats[a.id].biggestDefeatScore = `${as}-${hs}`;   // scored-conceded
          }
        }
        if (as > hs) {
          const diff = as - hs;
          if (diff > stats[h.id].biggestDefeat) {
            stats[h.id].biggestDefeat = diff;
            stats[h.id].biggestDefeatScore = `${hs}-${as}`;
          }
        }
      }

      // m.goals / m.bookings come from football-data.org (legacy). With api-sports
      // these now feed in via team-stats.json (extStats) and are merged below.
      if (m.goals) {
        for (const g of m.goals) {
          const tid = g.team?.id;
          if (!tid || !stats[tid]) continue;
          if (g.type === 'OWN_GOAL') stats[tid].ownGoals++;
          if (g.minute >= 85) stats[tid].lateGoals++;
        }
      }
      if (m.bookings) {
        for (const b of m.bookings) {
          const tid = b.team?.id;
          if (!tid || !stats[tid]) continue;
          if (b.card === 'YELLOW_CARD') stats[tid].yellowCards++;
          if (b.card === 'RED_CARD' || b.card === 'YELLOW_RED_CARD') stats[tid].redCards++;
        }
      }
    }

    // Merge in event-based stats from api-sports (cards, fouls, own goals,
    // late goals). Create entries for teams currently playing live so the
    // Prize Tracker shows them even before their first match finishes.
    for (const [teamName, ext] of Object.entries(extStats)) {
      let entry = Object.values(stats).find(s => s.name === teamName);
      if (!entry) {
        // Find team metadata from any match (live or scheduled)
        const m = matches.find(mm =>
          mm.homeTeam?.name === teamName || mm.awayTeam?.name === teamName
        );
        if (!m) continue;
        const t = m.homeTeam?.name === teamName ? m.homeTeam : m.awayTeam;
        ensureTeam(t.id, t.name, t.shortName);
        entry = stats[t.id];
      }
      entry.yellowCards = ext.yellowCards || 0;
      entry.redCards    = ext.redCards    || 0;
      entry.fouls       = ext.fouls       || 0;
      entry.ownGoals    = ext.ownGoals    || 0;
      entry.lateGoals   = ext.lateGoals   || 0;
    }

    return stats;
  }
};
