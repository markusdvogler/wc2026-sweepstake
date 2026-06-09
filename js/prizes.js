const PRIZE_DEFINITIONS = [
  {
    id: 'most_goals',
    name: 'The Goal Diggers',
    desc: 'Team with most goals scored',
    icon: '⚽',
    stat: s => s.goalsFor,
    order: 'desc'
  },
  {
    id: 'most_yellow',
    name: 'The Warning',
    desc: 'Team with most yellow cards',
    icon: '🟨',
    stat: s => s.yellowCards,
    order: 'desc'
  },
  {
    id: 'most_red',
    name: 'The Red Mist',
    desc: 'Team with most red cards',
    icon: '🟥',
    stat: s => s.redCards,
    order: 'desc'
  },
  {
    id: 'least_conceded',
    name: 'The Clean Sheet Kings',
    desc: 'Team with least goals conceded',
    icon: '🧤',
    stat: s => s.goalsAgainst,
    order: 'asc'
  },
  {
    id: 'most_conceded',
    name: 'The Dirty Sheet Kings',
    desc: 'Team with most goals conceded',
    icon: '🤦',
    stat: s => s.goalsAgainst,
    order: 'desc'
  },
  {
    id: 'zero_zero',
    name: 'The Goalless Guardians',
    desc: 'Team with most 0-0 matches',
    icon: '😴',
    stat: s => s.zeroZeroMatches,
    order: 'desc'
  },
  {
    id: 'most_fouls',
    name: 'The Rugby Players',
    desc: 'Team with most fouls',
    icon: '🏉',
    stat: s => s.fouls,
    order: 'desc',
    note: 'Foul data may not be available via API'
  },
  {
    id: 'biggest_defeat',
    name: 'The Hangover',
    desc: 'Team with largest defeat in one game',
    icon: '😵',
    stat: s => s.biggestDefeat,
    order: 'desc'
  },
  {
    id: 'own_goals',
    name: 'The Deflectors',
    desc: 'Team with most own goals',
    icon: '🙈',
    stat: s => s.ownGoals,
    order: 'desc'
  },
  {
    id: 'late_goals',
    name: 'The Late Show',
    desc: 'Team with most goals after 85th minute',
    icon: '⏱️',
    stat: s => s.lateGoals,
    order: 'desc'
  },
  {
    id: 'least_points',
    name: 'The Losers',
    desc: 'Team with the least points',
    icon: '💀',
    stat: s => s.points,
    order: 'asc'
  },
  {
    id: 'upgraders',
    name: 'The Upgraders',
    desc: 'Lowest ranked team to reach Round of 32',
    icon: '🚀',
    stat: null, // Calculated separately
    order: 'special'
  }
];

function calcPrizeLeaders(teamStats, participants, teamsData, advancedTeamIds) {
  const statsArr = Object.values(teamStats);
  const results = [];

  for (const prize of PRIZE_DEFINITIONS) {
    let top3 = [];

    if (prize.order === 'special') {
      if (advancedTeamIds && advancedTeamIds.length > 0 && participants.length > 0) {
        const ranked = [];
        for (const p of participants) {
          const team = teamsData.find(t => t.name === p.team || t.code === p.teamCode);
          if (team && advancedTeamIds.includes(p.teamCode)) {
            ranked.push({ participant: p.name, team: p.team, value: `Rank #${team.fifaRanking}`, _sort: team.fifaRanking });
          }
        }
        ranked.sort((a, b) => b._sort - a._sort);
        top3 = ranked.slice(0, 3).map(({ _sort, ...r }) => r);
      }
    } else if (statsArr.length > 0) {
      // For asc prizes, only include teams that have played (avoids 48-way tie at 0)
      const eligible = prize.order === 'asc'
        ? statsArr.filter(s => s.played > 0)
        : statsArr.filter(s => prize.stat(s) > 0);

      if (eligible.length > 0) {
        const sorted = [...eligible].sort((a, b) =>
          prize.order === 'asc' ? prize.stat(a) - prize.stat(b) : prize.stat(b) - prize.stat(a)
        );

        // Take top 3, keeping tied teams at the same position
        const topVal   = prize.stat(sorted[0]);
        const rank2Val = sorted[1] ? prize.stat(sorted[1]) : null;
        const rank3Val = sorted[2] ? prize.stat(sorted[2]) : null;

        const toEntry = s => {
          const participant = participants.find(p => p.teamCode === s.shortName || p.team === s.name);
          return { team: s.name, participant: participant?.name || '?', value: prize.stat(s) };
        };

        const rank1 = sorted.filter(s => prize.stat(s) === topVal).map(toEntry);
        const rank2 = rank2Val !== null && rank2Val !== topVal
          ? sorted.filter(s => prize.stat(s) === rank2Val).map(toEntry) : [];
        const rank3 = rank3Val !== null && rank3Val !== topVal && rank3Val !== rank2Val
          ? sorted.filter(s => prize.stat(s) === rank3Val).map(toEntry) : [];

        top3 = [
          ...rank1.map(e => ({ ...e, rank: 1 })),
          ...rank2.map(e => ({ ...e, rank: 2 })),
          ...rank3.map(e => ({ ...e, rank: 3 })),
        ];
      }
    }

    results.push({ ...prize, top3 });
  }

  return results;
}
