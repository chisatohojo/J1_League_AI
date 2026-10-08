import { DRAW_COLOR } from "../team-colors.js";

/**
 * @typedef {Object} ProbabilityBarProps
 * @property {number} homeProbability Percentage, not a fraction.
 * @property {number} drawProbability Percentage, not a fraction.
 * @property {number} awayProbability Percentage, not a fraction.
 * @property {string} homeColor Six-digit hex UI accent.
 * @property {string} awayColor Six-digit hex UI accent.
 * @property {string} homeLabel
 * @property {string} awayLabel
 */

/** Pure display mapping. Never mutates the props or persisted probabilities. */
export function buildProbabilityView(props) {
  const values = [props.homeProbability, props.drawProbability, props.awayProbability];
  const total = values.reduce((sum, value) => sum + value, 0);
  if (values.some(value => !Number.isFinite(value) || value < 0 || value > 100)
      || Math.abs(total - 100) > 1 + 1e-9) {
    throw new RangeError("Probability percentages must be finite, nonnegative and total near 100");
  }
  if (![props.homeColor, props.awayColor].every(color => /^#[\da-f]{6}$/i.test(color))) {
    throw new TypeError("Team colors must be six-digit hex colors");
  }

  const widths = values.map(value => value / total * 100);
  // Largest remainder at 0.1 percentage-point precision; deterministic HOME/DRAW/AWAY ties.
  const units = widths.map(width => Math.floor(width * 10));
  const order = widths.map((width, index) => ({ index, remainder: width * 10 - units[index] }))
    .sort((a, b) => b.remainder - a.remainder || a.index - b.index);
  for (let left = 1000 - units.reduce((sum, value) => sum + value, 0), i = 0; left > 0; left--, i++) {
    units[order[i % 3].index]++;
  }
  return ["home", "draw", "away"].map((outcome, index) => ({
    outcome,
    width: widths[index],
    original: values[index],
    display: values[index] > 0 && units[index] === 0 ? "<0.1%" : `${units[index] / 10}%`,
    color: [props.homeColor, DRAW_COLOR, props.awayColor][index],
    label: [props.homeLabel, "引き分け", props.awayLabel][index],
  }));
}

function textColor(hex) {
  const rgb = hex.slice(1).match(/../g).map(value => parseInt(value, 16) / 255)
    .map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] > 0.179 ? "#101c2c" : "#ffffff";
}

/** A single continuous stacked bar, shared by result and upcoming cards. */
export function PredictionProbabilityBar(props, { document = globalThis.document } = {}) {
  const view = buildProbabilityView(props);
  const figure = document.createElement("figure");
  figure.className = "prediction-probability";
  figure.setAttribute("role", "img");
  figure.setAttribute("aria-label", view.map(item =>
    `${item.outcome.toUpperCase()} ${item.label} ${item.original}%`).join("、"));

  const track = document.createElement("div");
  track.className = "probability-bar";
  track.setAttribute("aria-hidden", "true");
  for (const item of view) {
    const segment = document.createElement("div");
    segment.className = "probability-segment";
    segment.dataset.outcome = item.outcome;
    segment.dataset.labelWide = String(item.width >= 18);
    segment.dataset.labelRoomy = String(item.width >= 12);
    segment.style.width = `${item.width}%`;
    segment.style.backgroundColor = item.color;
    segment.style.color = textColor(item.color);
    segment.title = `${item.outcome.toUpperCase()} · ${item.label} ${item.original}%`;
    const value = document.createElement("span");
    value.className = "segment-value";
    value.textContent = item.display;
    segment.append(value);
    track.append(segment);
  }
  const caption = document.createElement("figcaption");
  caption.className = "probability-labels";
  for (const item of view) {
    const label = document.createElement("div");
    label.className = "probability-label";
    label.dataset.outcome = item.outcome;
    const name = document.createElement("span");
    name.textContent = item.outcome.toUpperCase();
    const number = document.createElement("strong");
    number.textContent = item.display;
    label.append(name, number);
    caption.append(label);
  }
  figure.append(track, caption);
  return figure;
}
