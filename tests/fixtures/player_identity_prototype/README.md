# Player identity prototype fixtures

`sfpr01_display_names_only.html` is a reduced, network-free structural fixture
based on the official 2024 C Osaka SFPR01 result. It preserves the relevant
`th.name-c` structure and exact displayed full-width spaces, but is not a saved
raw page or a complete player list.

Official source:
`https://data.j-league.or.jp/SFPR01/search?competition_frame_id=1&competition_frame_id_ex=1&competition_id=589&competition_id_ex=589&competition_year=2024&competition_year_ex=2024&dataSize=1&pageStartNo=0&selectedCompetitionName=%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&selectedCompetitionYear=2024%E5%B9%B4&selectedTeamName=%EF%BC%A3%E5%A4%A7%E9%98%AA&team_id=20&team_id_ex=20`

The fixture intentionally contains no `SFIX04` link or `player_id`, matching
the identity-relevant structure observed in the official result. Tests never
access the network.
