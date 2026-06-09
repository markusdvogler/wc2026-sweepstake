let participants = [];
let teamsData = [];
let teamStats = {};
let allMatches = [];
let standingsData = [];

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
  const base = isLocal ? `/flags/w${size}` : `https://flagcdn.com/w${size}`;
  return `<img src="${base}/${iso2}.png" width="${size}" class="inline rounded-sm align-middle" alt="${t?.name ?? ''}">`;
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

function renderParticipants(filter = '') {
  document.getElementById('participants-loading').classList.add('hidden');

  // Sort alphabetically by name
  const sorted = [...participants].sort((a, b) => a.name.localeCompare(b.name));

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
  document.getElementById('draw-banner').classList.add('hidden');
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

// ---- Standings ----
async function loadStandings() {
  if (!API.hasKey()) {
    document.getElementById('standings-loading').classList.add('hidden');
    document.getElementById('standings-no-api').classList.remove('hidden');
    return;
  }
  try {
    const data = await API.getStandings();
    standingsData = data.standings || [];
    document.getElementById('standings-loading').classList.add('hidden');
    document.getElementById('standings-content').classList.remove('hidden');
    renderStandings();
  } catch (e) {
    document.getElementById('standings-loading').classList.add('hidden');
    document.getElementById('standings-no-api').classList.remove('hidden');
  }
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
    teamStats = await API.getTeamStats();
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
  const prizeResults = calcPrizeLeaders(teamStats, participants, teamsData, null);
  const container = document.getElementById('prizes-grid');
  container.innerHTML = prizeResults.map(p => {
    const w = p.winner;
    const hasWinner = w && (typeof w.value !== 'number' || w.value > 0);
    return `
      <div class="prize-card bg-slate-800 border border-slate-700 rounded-xl p-4">
        <div class="flex items-center gap-3 mb-3">
          <span class="text-2xl">${p.icon}</span>
          <div>
            <p class="font-semibold text-sm">${p.name}</p>
            <p class="text-xs text-slate-500">${p.desc}</p>
          </div>
        </div>
        ${hasWinner ? `
          <div class="bg-slate-700 rounded-lg px-3 py-2">
            <p class="font-bold text-white text-sm">${flagImg(w.team)} ${w.team}</p>
            <p class="text-xs text-slate-400">${w.participant !== '?' ? `Held by ${w.participant}` : 'Participant TBD'}</p>
            <p class="text-green-400 font-bold text-lg mt-1">${w.value}</p>
          </div>
        ` : `
          <div class="bg-slate-700/50 rounded-lg px-3 py-2 text-center">
            <p class="text-xs text-slate-500">${p.note || 'No data yet'}</p>
          </div>
        `}
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
    const { matches } = await API.getMatches();
    if (matches && matches.length > 0) {
      indicator.textContent = '● Live data';
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
  const loaded = { matches: false, standings: false, prizes: false };
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.id.replace('tab-', '');
      if (name === 'matches' && !loaded.matches) { loaded.matches = true; loadMatches(); }
      if (name === 'standings' && !loaded.standings) { loaded.standings = true; loadStandings(); }
      if (name === 'prizes' && !loaded.prizes) { loaded.prizes = true; loadPrizes(); }
    });
  });
}

init();
