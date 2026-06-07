// football-data.org API wrapper with caching
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes
const cache = {};

async function apiFetch(path) {
  const key = path;
  const now = Date.now();
  if (cache[key] && now - cache[key].ts < CACHE_TTL) return cache[key].data;

  // Route through local proxy to avoid CORS; falls back to direct call when deployed
  const isLocal = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  const url = isLocal
    ? `/proxy${path}`
    : `${CONFIG.API_BASE}${path}`;

  const headers = isLocal ? {} : { 'X-Auth-Token': CONFIG.API_KEY };
  const res = await fetch(url, { headers });

  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json();
  cache[key] = { data, ts: now };
  return data;
}

const API = {
  hasKey() {
    return CONFIG.API_KEY && CONFIG.API_KEY !== 'YOUR_API_KEY_HERE';
  },

  async getMatches() {
    return apiFetch(`/competitions/${CONFIG.COMPETITION_CODE}/matches`);
  },

  async getStandings() {
    return apiFetch(`/competitions/${CONFIG.COMPETITION_CODE}/standings`);
  },

  async getScorers() {
    return apiFetch(`/competitions/${CONFIG.COMPETITION_CODE}/scorers?limit=20`);
  },

  async getTeamMatches(teamId) {
    return apiFetch(`/competitions/${CONFIG.COMPETITION_CODE}/matches?team=${teamId}`);
  },

  // Build aggregated stats from all match data
  async getTeamStats() {
    const { matches } = await this.getMatches();
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

      // Biggest defeat
      if (hs > as) stats[a.id].biggestDefeat = Math.max(stats[a.id].biggestDefeat, hs - as);
      if (as > hs) stats[h.id].biggestDefeat = Math.max(stats[h.id].biggestDefeat, as - hs);

      // Bookings and goals from match events
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

    return stats;
  }
};
