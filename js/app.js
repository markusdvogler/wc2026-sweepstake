let participants = [];
let teamsData = [];
let participantSort = 'alpha'; // 'alpha' or 'rank'
let teamStats = {};
let allMatches = [];
let standingsData = [];
let advancedTeamCodes = [];

// ---- Tab navigation ----
function showTab(name) {
  document.querySelectorAll('[id^="view-"]').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.tab-btn').forEach(el => {
    el.classList.remove('tab-active');
    el.classList.add('tab-inactive');
  });
  document.getElementById(`view-${name}`).classList.remove('hidden');
  document.getElementById(`tab-${name}`).classList.remove('tab-inactive');
  document.getElementById(`tab-${name}`).classList.add('tab-active');
}

// ---- Helpers ----
function rankBadgeClass(rank) {
  if (rank <= 3) return 'rank-top3';
  if (rank <= 10) return 'rank-top10';
  return 'rank-rest';
}

// ISO 3166-1 alpha-2 codes for flagcdn.com
const FLAG_ISO2 = {
  ARG:'ar', FRA:'fr', ESP:'es', ENG:'gb-eng', BRA:'br', BEL:'be',
  NED:'nl', POR:'pt', COL:'co', GER:'de', URU:'uy', JPN:'jp',
  CRO:'hr', MAR:'ma', SEN:'sn', SUI:'ch', KOR:'kr', ECU:'ec',
  AUT:'at', TUR:'tr', AUS:'au', NOR:'no', SWE:'se', IRN:'ir',
  CIV:'ci', EGY:'eg', ALG:'dz', PAN:'pa', IRQ:'iq', SCO:'gb-sct',
  GHA:'gh', PAR:'py', TUN:'tn', USA:'us', MEX:'mx', CAN:'ca',
  RSA:'za', KSA:'sa', QAT:'qa', CZE:'cz', NZL:'nz', BIH:'ba',
  JOR:'jo', UZB:'uz', COD:'cd', CPV:'cv', HAI:'ht', CUW:'cw'
};

function flagImg(teamName, size = 20) {
  const t = teamsData.find(t => t.name === teamName || t.code === teamName);
  const iso2 = t ? FLAG_ISO2[t.code] : null;
  if (!iso2) return '<span class="text-slate-500 text-xs">🏳</span>';
  return `<img src="flags/${iso2}.png" width="${size}" height="${Math.round(size*0.75)}" class="inline rounded-sm align-middle flex-shrink-0" alt="">`;
}

function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function statusBadge(status, homeScore, awayScore) {
  if (status === 'FINISHED') {
    return `<span class="bg-green-900/50 text-green-400 text-xs px-2 py-0.5 rounded-full">FT</span>`;
  }
  if (status === 'IN_PLAY' || status === 'PAUSED') {
    return `<span class="bg-red-600 text-white text-xs px-2 py-0.5 rounded-full animate-pulse">LIVE</span>`;
  }
  return `<span class="bg-slate-700 text-slate-400 text-xs px-2 py-0.5 rounded-full">Upcoming</span>`;
}

// ---- Load participants ----
async function loadParticipants() {
  try {
    const [pRes, tRes] = await Promise.all([
      fetch('participants.json'),
      fetch('teams.json')
    ]);
    const pData = await pRes.json();
    const tData = await tRes.json();
    participants = pData.participants || [];
    teamsData = tData.teams || [];
  } catch (e) {
    participants = [];
    teamsData = [];
  }
  renderParticipants();
}

function toggleSort() {
  participantSort = participantSort === 'alpha' ? 'rank' : 'alpha';
  document.getElementById('sort-toggle').textContent =
    participantSort === 'alpha' ? 'Sort: A–Z' : 'Sort: FIFA Rank';
  renderParticipants(document.getElementById('search-participants').value);
}

function renderParticipants(filter = '') {
  document.getElementById('participants-loading').classList.add('hidden');

  // Sort by selected mode
  const sorted = [...participants].sort((a, b) => {
    if (participantSort === 'rank') {
      const tA = teamsData.find(t => t.name === a.team || t.code === a.teamCode);
      const tB = teamsData.find(t => t.name === b.team || t.code === b.teamCode);
      return (tA?.fifaRanking ?? 999) - (tB?.fifaRanking ?? 999);
    }
    return a.name.localeCompare(b.name);
  });

  const list = filter
    ? sorted.filter(p =>
        p.name.toLowerCase().includes(filter.toLowerCase()) ||
        (p.team || '').toLowerCase().includes(filter.toLowerCase())
      )
    : sorted;

  if (participants.length === 0) {
    document.getElementById('participants-empty').classList.remove('hidden');
    document.getElementById('participants-table').classList.add('hidden');
    return;
  }

  document.getElementById('participants-empty').classList.add('hidden');
  document.getElementById('participants-table').classList.remove('hidden');
  document.getElementById('participants-subtitle').textContent = `${participants.length} participants`;

  const tbody = document.getElementById('participants-tbody');
  tbody.innerHTML = list.map((p, i) => {
    const team = teamsData.find(t => t.name === p.team || t.code === p.teamCode);
    const rank = team?.fifaRanking ?? '?';
    return `
      <tr class="border-t border-slate-700/50 hover:bg-slate-750/50 transition-colors">
        <td class="px-4 py-3 text-slate-500 text-xs">${i + 1}</td>
        <td class="px-4 py-3 font-medium">${p.name}</td>
        <td class="px-4 py-3">
          <span class="flex items-center gap-2">
            ${flagImg(p.team, 24)}
            <span>${p.team || '<span class="text-slate-500 italic">TBD</span>'}</span>
          </span>
        </td>
        <td class="px-4 py-3 text-center">
          <span class="ranking-badge ${rankBadgeClass(rank)}">${rank}</span>
        </td>
      </tr>`;
  }).join('');
}

// ---- Matches ----
async function loadMatches() {
  if (!API.hasKey()) {
    document.getElementById('matches-loading').classList.add('hidden');
    document.getElementById('matches-no-api').classList.remove('hidden');
    return;
  }
  try {
    const data = await API.getMatches();
    allMatches = data.matches || [];
    document.getElementById('matches-loading').classList.add('hidden');
    document.getElementById('matches-content').classList.remove('hidden');
    renderMatches('all');
  } catch (e) {
    document.getElementById('matches-loading').classList.add('hidden');
    document.getElementById('matches-no-api').classList.remove('hidden');
  }
}

function renderMatches(stageFilter) {
  const list = stageFilter === 'all'
    ? allMatches
    : allMatches.filter(m => m.stage === stageFilter);

  // Group by matchday / round
  const groups = {};
  for (const m of list) {
    const key = m.stage === 'GROUP_STAGE' ? `Group Stage – Matchday ${m.matchday}` : m.stage?.replace(/_/g, ' ');
    if (!groups[key]) groups[key] = [];
    groups[key].push(m);
  }

  const container = document.getElementById('matches-content');
  container.innerHTML = Object.entries(groups).map(([round, matches]) => `
    <div>
      <h3 class="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2 px-1">${round}</h3>
      <div class="space-y-2">
        ${matches.map(m => {
          const finished = m.status === 'FINISHED';
          const live = m.status === 'IN_PLAY' || m.status === 'PAUSED';
          const homeFlag = flagImg(m.homeTeam?.name);
          const awayFlag = flagImg(m.awayTeam?.name);
          const hs = m.score?.fullTime?.home;
          const as = m.score?.fullTime?.away;
          const homeP = participants.find(p => p.team === m.homeTeam?.name);
          const awayP = participants.find(p => p.team === m.awayTeam?.name);
          return `
            <div class="bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 ${live ? 'border-red-600/50' : ''}">
              <div class="flex items-center justify-between gap-4">
                <div class="flex-1 text-right">
                  <p class="font-semibold">${homeFlag} ${m.homeTeam?.name || 'TBD'}</p>
                  ${homeP ? `<p class="text-xs text-slate-500">${homeP.name}</p>` : ''}
                </div>
                <div class="text-center min-w-[80px]">
                  ${finished || live
                    ? `<p class="text-2xl font-bold ${live ? 'text-red-400' : ''}">${hs ?? '-'} – ${as ?? '-'}</p>`
                    : `<p class="text-slate-500 font-medium">vs</p><p class="text-xs text-slate-600">${formatDate(m.utcDate)}</p>`
                  }
                  <div class="mt-1">${statusBadge(m.status)}</div>
                </div>
                <div class="flex-1 text-left">
                  <p class="font-semibold">${awayFlag} ${m.awayTeam?.name || 'TBD'}</p>
                  ${awayP ? `<p class="text-xs text-slate-500">${awayP.name}</p>` : ''}
                </div>
              </div>
              ${finished ? `<p class="text-xs text-slate-600 text-center mt-1">${formatDate(m.utcDate)}</p>` : ''}
            </div>`;
        }).join('')}
      </div>
    </div>
  `).join('');
}

// ---- Knockout Bracket ----
async function loadKnockouts() {
  try {
    if (allMatches.length === 0) {
      const data = await API.getMatches();
      allMatches = data.matches || [];
    }
    document.getElementById('knockouts-loading').classList.add('hidden');
    document.getElementById('knockouts-content').classList.remove('hidden');
    renderKnockouts();
  } catch (e) {
    document.getElementById('knockouts-loading').classList.add('hidden');
  }
}

const KO_STAGES = [
  { key: 'LAST_32',        label: 'Round of 32' },
  { key: 'LAST_16',        label: 'Round of 16' },
  { key: 'QUARTER_FINALS', label: 'Quarter Finals' },
  { key: 'SEMI_FINALS',    label: 'Semi Finals' },
  { key: 'FINAL',          label: 'Final' },
];

function bracketCard(m) {
  const finished = m.status === 'FINISHED';
  const live     = m.status === 'IN_PLAY' || m.status === 'PAUSED';
  const hs = m.score?.fullTime?.home;
  const as = m.score?.fullTime?.away;
  const winner = m.score?.winner;
  const homeName = m.homeTeam?.name || 'TBD';
  const awayName = m.awayTeam?.name || 'TBD';
  const homeFlag = m.homeTeam ? flagImg(homeName) : '';
  const awayFlag = m.awayTeam ? flagImg(awayName) : '';
  const homeP = participants.find(p => p.team === homeName);
  const awayP = participants.find(p => p.team === awayName);
  const homeWin = winner === 'HOME_TEAM';
  const awayWin = winner === 'AWAY_TEAM';
  const dimHome = finished && !homeWin ? 'text-slate-500' : 'text-white';
  const dimAway = finished && !awayWin ? 'text-slate-500' : 'text-white';
  const dateLine = !finished && !live
    ? `<p class="text-[10px] text-slate-500 text-center pt-1">${formatDate(m.utcDate)}</p>` : '';

  const row = (flag, name, p, score, dim, isWin) => `
    <div class="flex items-center justify-between gap-2 py-1 ${isWin ? 'font-bold' : ''}">
      <div class="flex items-center gap-1.5 min-w-0">
        <span class="shrink-0">${flag}</span>
        <span class="text-xs truncate ${dim}">${name}</span>
      </div>
      <span class="text-xs font-bold tabular-nums ${dim}">${score ?? ''}</span>
    </div>
    ${p ? `<p class="text-[10px] text-slate-500 truncate -mt-1 ml-6">${p.name}</p>` : ''}`;

  return `
    <div class="bg-slate-800 border ${live ? 'border-red-600/60' : 'border-slate-700'} rounded-lg px-3 py-2 w-52">
      ${row(homeFlag, homeName, homeP, finished || live ? hs : null, dimHome, homeWin)}
      <div class="border-t border-slate-700/60 my-0.5"></div>
      ${row(awayFlag, awayName, awayP, finished || live ? as : null, dimAway, awayWin)}
      ${dateLine}
    </div>`;
}

function renderKnockouts() {
  const bracket = document.getElementById('knockouts-bracket');
  bracket.innerHTML = KO_STAGES.map(stage => {
    const matches = allMatches
      .filter(m => m.stage === stage.key)
      .sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate));
    return `
      <div class="flex flex-col">
        <h3 class="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-3 text-center">${stage.label}</h3>
        <div class="flex-1 flex flex-col justify-around gap-3">
          ${matches.length > 0
            ? matches.map(bracketCard).join('')
            : `<div class="text-slate-600 text-xs italic text-center py-4">TBD</div>`
          }
        </div>
      </div>`;
  }).join('');

  // Third Place playoff
  const third = allMatches.filter(m => m.stage === 'THIRD_PLACE');
  const thirdContainer = document.getElementById('knockouts-third');
  if (third.length > 0) {
    thirdContainer.innerHTML = `
      <div class="max-w-xs">
        <h3 class="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">Third Place Playoff</h3>
        ${third.map(bracketCard).join('')}
      </div>`;
  } else {
    thirdContainer.innerHTML = '';
  }
}

// ---- Standings ----
async function loadStandings() {
  if (!API.hasKey()) {
    document.getElementById('standings-loading').classList.add('hidden');
    document.getElementById('standings-no-api').classList.remove('hidden');
    return;
  }
  try {
    // Computed from matches.json (single source of truth now)
    const { matches } = await API.getMatches();
    standingsData = computeStandings(matches || []);
    document.getElementById('standings-loading').classList.add('hidden');
    document.getElementById('standings-content').classList.remove('hidden');
    renderStandings();
  } catch (e) {
    document.getElementById('standings-loading').classList.add('hidden');
    document.getElementById('standings-no-api').classList.remove('hidden');
  }
}

// Compute group standings from match results. Mirrors football-data.org's
// /standings response shape so renderStandings() doesn't need changes.
function computeStandings(matches) {
  const groupOf = {};   // teamName -> "GROUP_A"
  const teamRef = {};   // teamName -> team object (id, name, tla, crest)
  for (const m of matches) {
    if (m.stage !== 'GROUP_STAGE' || !m.group) continue;
    for (const side of ['homeTeam', 'awayTeam']) {
      const t = m[side];
      if (!t || !t.name) continue;
      groupOf[t.name] = m.group;
      teamRef[t.name] = t;
    }
  }

  // Init each team's row
  const rows = {};
  for (const [name, group] of Object.entries(groupOf)) {
    rows[name] = {
      group, team: teamRef[name], position: 0,
      playedGames: 0, won: 0, draw: 0, lost: 0,
      goalsFor: 0, goalsAgainst: 0, goalDifference: 0, points: 0
    };
  }

  // Accumulate from finished AND live group-stage matches (live counts
  // provisionally — points / GD update minute-by-minute).
  for (const m of matches) {
    if (m.stage !== 'GROUP_STAGE') continue;
    const isFinished = m.status === 'FINISHED';
    const isLive     = m.status === 'IN_PLAY' || m.status === 'PAUSED';
    if (!isFinished && !isLive) continue;
    const home = m.homeTeam?.name, away = m.awayTeam?.name;
    const hs = m.score?.fullTime?.home, as = m.score?.fullTime?.away;
    if (!home || !away || hs == null || as == null) continue;
    const H = rows[home], A = rows[away];
    if (!H || !A) continue;
    if (isFinished) { H.playedGames++; A.playedGames++; }
    H.goalsFor += hs; H.goalsAgainst += as;
    A.goalsFor += as; A.goalsAgainst += hs;
    if (hs > as)      { H.won++;  A.lost++; H.points += 3; }
    else if (hs < as) { A.won++;  H.lost++; A.points += 3; }
    else              { H.draw++; A.draw++; H.points++; A.points++; }
  }
  for (const r of Object.values(rows)) r.goalDifference = r.goalsFor - r.goalsAgainst;

  // Group rows by group and sort
  const groups = {};
  for (const r of Object.values(rows)) {
    if (!groups[r.group]) groups[r.group] = [];
    groups[r.group].push(r);
  }
  const sorted = Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  return sorted.map(([group, table]) => {
    table.sort((a, b) =>
      b.points - a.points ||
      b.goalDifference - a.goalDifference ||
      b.goalsFor - a.goalsFor ||
      a.team.name.localeCompare(b.team.name)
    );
    table.forEach((r, i) => { r.position = i + 1; });
    return { group, table };
  });
}

function renderStandings() {
  const container = document.getElementById('standings-content');
  container.innerHTML = standingsData.map(group => `
    <div class="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
      <div class="bg-slate-750 px-4 py-2 border-b border-slate-700">
        <h3 class="font-semibold text-sm">${group.group?.replace('GROUP_', 'Group ') || 'Group'}</h3>
      </div>
      <table class="w-full text-xs">
        <thead>
          <tr class="text-slate-500 border-b border-slate-700/50">
            <th class="px-3 py-2 text-left">#</th>
            <th class="px-3 py-2 text-left">Team</th>
            <th class="px-3 py-2 text-center">P</th>
            <th class="px-3 py-2 text-center">W</th>
            <th class="px-3 py-2 text-center">D</th>
            <th class="px-3 py-2 text-center">L</th>
            <th class="px-3 py-2 text-center">GD</th>
            <th class="px-3 py-2 text-center font-bold">Pts</th>
          </tr>
        </thead>
        <tbody>
          ${(group.table || []).map((row, i) => {
            const flag = flagImg(row.team?.name);
            const participant = participants.find(p => p.team === row.team?.name);
            const qualified = i < 2;
            return `
              <tr class="border-t border-slate-700/30 ${qualified ? 'bg-green-900/10' : ''} hover:bg-slate-700/30">
                <td class="px-3 py-2 text-slate-500">${row.position}</td>
                <td class="px-3 py-2">
                  <p class="font-medium">${flag} ${row.team?.name}</p>
                  ${participant ? `<p class="text-slate-600">${participant.name}</p>` : ''}
                </td>
                <td class="px-3 py-2 text-center text-slate-400">${row.playedGames}</td>
                <td class="px-3 py-2 text-center text-slate-400">${row.won}</td>
                <td class="px-3 py-2 text-center text-slate-400">${row.draw}</td>
                <td class="px-3 py-2 text-center text-slate-400">${row.lost}</td>
                <td class="px-3 py-2 text-center text-slate-400">${row.goalDifference > 0 ? '+' : ''}${row.goalDifference}</td>
                <td class="px-3 py-2 text-center font-bold ${qualified ? 'text-green-400' : ''}">${row.points}</td>
              </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>
  `).join('');
}

// ---- Prizes ----
async function loadPrizes() {
  // Always show static prize cards
  renderStaticPrizes();

  if (!API.hasKey()) {
    document.getElementById('prizes-loading').classList.add('hidden');
    document.getElementById('prizes-no-api').classList.remove('hidden');
    return;
  }
  try {
    const [stats, eventStats, { matches }] = await Promise.all([
      API.getTeamStats(),
      API.getEventStats().catch(() => null),
      API.getMatches()
    ]);
    teamStats = stats;
    // A team has truly advanced once they're slotted into a knockout fixture
    // (real team name, not "TBD"). This becomes accurate only after group
    // stage ends and the bracket is set — exactly what we want.
    const knockoutStages = new Set(['LAST_32', 'LAST_16', 'QUARTER_FINALS', 'SEMI_FINALS', 'FINAL', 'THIRD_PLACE']);
    const advancedNames = new Set();
    for (const m of (matches || [])) {
      if (!knockoutStages.has(m.stage)) continue;
      if (m.homeTeam?.name) advancedNames.add(m.homeTeam.name);
      if (m.awayTeam?.name) advancedNames.add(m.awayTeam.name);
    }
    advancedTeamCodes = [...advancedNames]
      .map(name => teamsData.find(td => td.name === name)?.code)
      .filter(Boolean);

    document.getElementById('prizes-loading').classList.add('hidden');
    document.getElementById('prizes-grid').classList.remove('hidden');
    renderLivePrizes();

  } catch (e) {
    document.getElementById('prizes-loading').classList.add('hidden');
    document.getElementById('prizes-no-api').classList.remove('hidden');
  }
}

function renderStaticPrizes() {
  const container = document.getElementById('prizes-static-grid');
  if (!container) return;
  container.innerHTML = PRIZE_DEFINITIONS.map(p => `
    <div class="prize-card bg-slate-800 border border-slate-700 rounded-xl p-4">
      <div class="flex items-center gap-3 mb-2">
        <span class="text-2xl">${p.icon}</span>
        <div>
          <p class="font-semibold text-sm">${p.name}</p>
          <p class="text-xs text-slate-500">${p.desc}</p>
        </div>
      </div>
      <div class="mt-3 bg-slate-700/50 rounded-lg px-3 py-2 text-center">
        <p class="text-xs text-slate-500">Awaiting match data</p>
      </div>
      <div class="mt-2 text-right">
        <span class="text-xs font-bold text-green-400">5 CHF</span>
      </div>
    </div>
  `).join('');
}

function renderLivePrizes() {
  const MEDALS = { 1: '🥇', 2: '🥈', 3: '🥉' };
  const RANK_COLOURS = {
    1: 'border-amber-500/50 bg-amber-900/20',
    2: 'border-slate-500/50 bg-slate-700/60',
    3: 'border-orange-700/40 bg-orange-900/10'
  };
  const VALUE_COLOURS = { 1: 'text-amber-400', 2: 'text-slate-300', 3: 'text-orange-400' };

  const prizeResults = calcPrizeLeaders(teamStats, participants, teamsData, advancedTeamCodes);
  const container = document.getElementById('prizes-grid');
  container.innerHTML = prizeResults.map(p => {
    const hasData = p.top3 && p.top3.length > 0;
    const rows = hasData ? p.top3.map(e => {
      const medal = MEDALS[e.rank] || '';
      const rowClass = RANK_COLOURS[e.rank] || 'border-slate-700 bg-slate-700/40';
      const valClass = VALUE_COLOURS[e.rank] || 'text-slate-400';
      return `
        <div class="flex items-center justify-between border ${rowClass} rounded-lg px-3 py-2 gap-2">
          <div class="flex items-center gap-2 min-w-0">
            <span class="text-base shrink-0">${medal}</span>
            <div class="min-w-0">
              <p class="font-semibold text-white text-sm truncate">${flagImg(e.team)} ${e.team}</p>
              <p class="text-xs text-slate-400 truncate">${e.participant !== '?' ? e.participant : 'TBD'}</p>
            </div>
          </div>
          <span class="${valClass} font-bold text-base shrink-0">${e.value}</span>
        </div>`;
    }).join('') : '';

    return `
      <div class="prize-card bg-slate-800 border border-slate-700 rounded-xl p-4">
        <div class="flex items-center gap-3 mb-3">
          <span class="text-2xl">${p.icon}</span>
          <div>
            <p class="font-semibold text-sm">${p.name}</p>
            <p class="text-xs text-slate-500">${p.desc}</p>
          </div>
        </div>
        ${hasData ? `<div class="space-y-2">${rows}</div>` : `
          <div class="bg-slate-700/50 rounded-lg px-3 py-2 text-center">
            <p class="text-xs text-slate-500">${p.note || 'No data yet'}</p>
          </div>`}
        <div class="mt-2 text-right">
          <span class="text-xs font-bold text-green-400">5 CHF</span>
        </div>
      </div>`;
  }).join('');
}

// ---- Prize Rules Info ----
function renderPrizesInfo() {
  const container = document.getElementById('prizes-info-list');
  container.innerHTML = PRIZE_DEFINITIONS.map(p => `
    <div class="flex items-start gap-3 py-2 border-t border-slate-700/50">
      <span class="text-xl">${p.icon}</span>
      <div class="flex-1">
        <span class="font-medium text-white">${p.name}</span>
        <span class="text-slate-400"> – ${p.desc}</span>
      </div>
      <span class="font-bold text-green-400 whitespace-nowrap">5 CHF</span>
    </div>
  `).join('');
}

// ---- API status indicator ----
async function checkApiStatus() {
  const indicator = document.getElementById('api-status');
  try {
    const data = await API.getMatches();
    const lastUpdated = data && data.lastUpdated;
    if (lastUpdated) {
      const fmt = new Date(lastUpdated).toLocaleString('en-GB', {
        hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short',
        timeZone: 'Europe/Zurich'
      });
      indicator.textContent = `● Updated ${fmt} CEST`;
      indicator.className = 'text-xs px-2 py-1 rounded-full bg-green-900/50 text-green-400';
    } else {
      indicator.textContent = '● No data yet';
      indicator.className = 'text-xs px-2 py-1 rounded-full bg-slate-800 text-slate-400';
    }
  } catch (e) {
    indicator.textContent = '● Offline';
    indicator.className = 'text-xs px-2 py-1 rounded-full bg-red-900/50 text-red-400';
  }
}

// ---- Search ----
document.getElementById('search-participants').addEventListener('input', e => {
  renderParticipants(e.target.value);
});

// ---- Match filter ----
document.getElementById('match-filter').addEventListener('change', e => {
  renderMatches(e.target.value);
});

// ---- Init ----
async function init() {
  renderPrizesInfo();
  await loadParticipants();
  checkApiStatus();

  // Lazy-load other tabs when first visited
  const loaded = { matches: false, standings: false, prizes: false, knockouts: false };
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.id.replace('tab-', '');
      if (name === 'matches' && !loaded.matches) { loaded.matches = true; loadMatches(); }
      if (name === 'standings' && !loaded.standings) { loaded.standings = true; loadStandings(); }
      if (name === 'prizes' && !loaded.prizes) { loaded.prizes = true; loadPrizes(); }
      if (name === 'knockouts' && !loaded.knockouts) { loaded.knockouts = true; loadKnockouts(); }
    });
  });
}

init();
