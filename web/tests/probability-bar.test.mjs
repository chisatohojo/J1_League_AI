import test from "node:test";
import assert from "node:assert/strict";
import { buildProbabilityView, PredictionProbabilityBar } from "../components/prediction-probability-bar.js";
import { DRAW_COLOR, FALLBACK_TEAM_COLOR, teamColor } from "../team-colors.js";

const props = {
  homeProbability: 31, drawProbability: 25, awayProbability: 44,
  homeColor: "#2459b5", awayColor: "#c83c44", homeLabel: "FC東京", awayLabel: "浦和レッズ",
};
class Element {
  constructor(tagName) { this.tagName = tagName; this.children = []; this.attributes = {}; this.dataset = {}; this.style = {}; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(name, value) { this.attributes[name] = value; }
}
const document = { createElement: tagName => new Element(tagName) };

test("31 / 25 / 44 produces one continuous ordered bar, correct widths and specified colors", () => {
  const bar = PredictionProbabilityBar(props, { document });
  assert.equal(bar.tagName, "figure");
  assert.equal(bar.children.length, 2);
  const [track, labels] = bar.children;
  assert.equal(track.className, "probability-bar");
  assert.deepEqual(track.children.map(node => node.dataset.outcome), ["home", "draw", "away"]);
  assert.deepEqual(track.children.map(node => node.style.width), ["31%", "25%", "44%"]);
  assert.deepEqual(track.children.map(node => node.style.backgroundColor), [props.homeColor, DRAW_COLOR, props.awayColor]);
  assert.equal(DRAW_COLOR, "#64748b");
  assert.deepEqual(labels.children.map(node => node.children[0].textContent), ["HOME", "DRAW", "AWAY"]);
  assert.deepEqual(labels.children.map(node => node.children[1].textContent), ["31%", "25%", "44%"]);
  assert.match(bar.attributes["aria-label"], /HOME FC東京 31%.*DRAW 引き分け 25%.*AWAY 浦和レッズ 44%/);
});

test("0% preserves all three slots without filling nonexistent probability", () => {
  const view = buildProbabilityView({ ...props, homeProbability: 0, drawProbability: 100, awayProbability: 0 });
  assert.deepEqual(view.map(item => item.width), [0, 100, 0]);
  assert.deepEqual(view.map(item => item.display), ["0%", "100%", "0%"]);
});

test("tiny positive probability stays nonzero in width and visibly labeled", () => {
  const bar = PredictionProbabilityBar({ ...props, homeProbability: 0.001, drawProbability: 99.999, awayProbability: 0 }, { document });
  const tiny = bar.children[0].children[0];
  assert.equal(tiny.dataset.labelWide, "false");
  assert.equal(tiny.dataset.labelRoomy, "false");
  assert.equal(parseFloat(tiny.style.width), 0.001);
  assert.equal(bar.children[1].children[0].children[1].textContent, "<0.1%");
});

for (const values of [[33, 33, 33], [33.3333, 33.3333, 33.3333], [10.01, 19.99, 70], [0, 50.00001, 49.99999]]) {
  test(`display-only rounding totals 100: ${values.join(" / ")}`, () => {
    const input = Object.freeze({ ...props, homeProbability: values[0], drawProbability: values[1], awayProbability: values[2] });
    const before = JSON.stringify(input);
    const view = buildProbabilityView(input);
    assert.ok(Math.abs(view.reduce((sum, item) => sum + item.width, 0) - 100) < 1e-10);
    assert.equal(Math.round(view.reduce((sum, item) => sum + parseFloat(item.display), 0) * 10), 1000);
    assert.equal(JSON.stringify(input), before);
    assert.deepEqual(view.map(item => item.original), values);
  });
}

for (const values of [[-1, 50, 51], [NaN, 20, 80], [Infinity, 0, 0], [0, 0, 0], [30, 30, 30], [101, 0, 0]]) {
  test(`reject invalid probabilities: ${values}`, () => assert.throws(() => buildProbabilityView({
    ...props, homeProbability: values[0], drawProbability: values[1], awayProbability: values[2],
  }), RangeError));
}

test("color inputs cannot inject arbitrary CSS; label values are text nodes", () => {
  assert.throws(() => PredictionProbabilityBar({ ...props, homeColor: "red;display:none" }, { document }), TypeError);
  const bar = PredictionProbabilityBar({ ...props, homeLabel: "<script>bad</script>" }, { document });
  assert.match(bar.attributes["aria-label"], /<script>bad<\/script>/);
  assert.equal(bar.children[0].children[0].children[0].tagName, "span");
});

test("team colors are mapped by stable ID with explicit fallback", () => {
  assert.equal(teamColor("team_0003"), props.homeColor);
  assert.equal(teamColor("team_0030"), props.awayColor);
  assert.equal(teamColor("unknown"), FALLBACK_TEAM_COLOR);
});
