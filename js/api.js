// football-data.org API wrapper
// - On localhost: proxies through serve.ps1 to avoid CORS
// - On GitHub Pages: reads from data/*.json files updated by GitHub Actions every 15 min

const CACHE_TTL = 5 * 60 * 1000;
const cache = {};
const isLocal = location.hostname === 'localhost' || location.hostname === '127.0.0.1';

async function apiFetch(path) {
  const now = Date.now();
  if (cache[path] && now - cache[path].ts < CACHE_TTL) return cache[path].data;
  const res = await fetch(`/proxy${path}`, { headers: {} });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json();
  cache[path] = { data, ts: now };
  return data;
}

async function staticFetch(file) {
  const now = Date.now();
  if (cache[file] && now - cache[file].ts < CACHE_TTL) return cache[file].data;
  const res = await fetch(file);
  if (!res.ok) throw new Error(`File error ${res.status}`);
  const data = await res.json();
  cache[file] = { data, ts: now };
  return data;
}

const API = {
  hasKey() {
    return isLocal
      ? CONFIG.API_KEY && CONFIG.API_KEY !== 'YOUR_API_KEY_HERE'
      : true; // GitHub Pages always has data files
  },

  async getMatches() {
    return isLocal
      ? apiFetch(`/competitions/${CONFIG.COMPETITION_CODE}/matches`)
      : staticFetch('data/matches.json');
  },

  async getStandings() {
    return isLocal
      ? apiFetch(`/competitions/${CONFIG.COMPETITION_CODE}/standings`)
      : staticFetch('data/standings.json');
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
          played: 0, wins: 0, draws: 0, losses: 0,
          goalsFor: 0, goalsAgainst: 0, points: 0,
          yellowCards: 0, redCards: 0, ownGoals: 0,
          zeroZeroMatches: 0, lateGoals: 0,
          biggestDefeat: 0, fouls: 0
        };
      }
    }

    for (const m of matches) {
      if (m.status !== 'FINISHED') continue;
      const h = m.homeTeam, a = m.awayTeam;
      const hs = m.score.fullTime.home, as = m.score.fullTime.away;
      if (hs === null || as === null) continue;

      ensureTeam(h.id, h.name, h.shortName);
      ensureTeam(a.id, a.name, a.shortName);

      stats[h.id].played++;
      stats[a.id].played++;
      stats[h.id].goalsFor += hs;
      stats[h.id].goalsAgainst += as;
      stats[a.id].goalsFor += as;
      stats[a.id].goalsAgainst += hs;

      if (hs > as) { stats[h.id].wins++; stats[h.id].points += 3; stats[a.id].losses++; }
      else if (hs < as) { stats[a.id].wins++; stats[a.id].points += 3; stats[h.id].losses++; }
      else { stats[h.id].draws++; stats[h.id].points++; stats[a.id].draws++; stats[a.id].points++; }

      if (hs === 0 && as === 0) { stats[h.id].zeroZeroMatches++; stats[a.id].zeroZeroMatches++; }

      if (hs > as) stats[a.id].biggestDefeat = Math.max(stats[a.id].biggestDefeat, hs - as);
      if (as > hs) stats[h.id].biggestDefeat = Math.max(stats[h.id].biggestDefeat, as - hs);

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

    // Merge in event-based stats from API-Football (cards, fouls, own goals, late goals)
    for (const [teamName, ext] of Object.entries(extStats)) {
      const entry = Object.values(stats).find(s => s.name === teamName);
      if (entry) {
        entry.yellowCards = ext.yellowCards || 0;
        entry.redCards    = ext.redCards    || 0;
        entry.fouls       = ext.fouls       || 0;
        entry.ownGoals    = ext.ownGoals    || 0;
        entry.lateGoals   = ext.lateGoals   || 0;
      }
    }

    return stats;
  }
};
