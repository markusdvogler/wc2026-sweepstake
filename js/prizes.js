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
    let winner = null, value = null;

    if (prize.order === 'special') {
      // Lowest ranked team (highest FIFA ranking number) that advanced
      if (advancedTeamIds && advancedTeamIds.length > 0 && participants.length > 0) {
        let lowestRanked = null;
        let lowestRankNum = -1;
        for (const p of participants) {
          const team = teamsData.find(t => t.name === p.team || t.code === p.teamCode);
          if (team && advancedTeamIds.includes(p.teamCode)) {
            if (team.fifaRanking > lowestRankNum) {
              lowestRankNum = team.fifaRanking;
              lowestRanked = { participant: p.name, team: p.team, value: `Rank #${team.fifaRanking}` };
            }
          }
        }
        winner = lowestRanked;
      }
    } else if (statsArr.length > 0) {
      const sorted = [...statsArr].sort((a, b) =>
        prize.order === 'asc' ? prize.stat(a) - prize.stat(b) : prize.stat(b) - prize.stat(a)
      );
      const best = sorted[0];
      const statVal = prize.stat(best);

      // Find which participant has this team
      const participant = participants.find(p =>
        p.teamCode === best.shortName || p.team === best.name
      );

      winner = {
        team: best.name,
        participant: participant?.name || '?',
        value: statVal
      };
      value = statVal;
    }

    results.push({ ...prize, winner, value });
  }

  return results;
}
