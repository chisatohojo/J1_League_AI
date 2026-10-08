// Provisional UI accents keyed by existing TeamMaster IDs, not official brand assets.
// Updating these colors never changes names, model inputs, or saved probabilities.
export const DRAW_COLOR = "#64748b";
export const FALLBACK_TEAM_COLOR = "#475569";
export const TEAM_COLORS = Object.freeze({
  team_0001: "#d3a91c", team_0002: "#c83f78", team_0003: "#2459b5",
  team_0004: "#214478", team_0005: "#245297", team_0006: "#7650a4",
  team_0007: "#44839a", team_0008: "#a52f43", team_0009: "#d4ae23",
  team_0010: "#2582a1", team_0011: "#97344e", team_0012: "#365daa",
  team_0013: "#7843a0", team_0014: "#284787", team_0015: "#378358",
  team_0016: "#3376a7", team_0017: "#315c98", team_0018: "#c3443f",
  team_0019: "#d57032", team_0020: "#2b64ab", team_0021: "#9c344c",
  team_0022: "#d67635", team_0023: "#ac3845", team_0024: "#cba52c",
  team_0025: "#d77d32", team_0026: "#40855b", team_0027: "#366294",
  team_0028: "#32805b", team_0029: "#4995af", team_0030: "#c83c44",
  team_0031: "#3370b2", team_0032: "#438aab", team_0033: "#315cb1",
});

export function teamColor(teamId) {
  return TEAM_COLORS[teamId] ?? FALLBACK_TEAM_COLOR;
}
