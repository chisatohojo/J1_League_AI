import { PredictionProbabilityBar } from "./components/prediction-probability-bar.js";
import { validateDashboard, highestProbabilityOutcomes, actualOutcome, formatKickoff } from "./dashboard-data.js";
import { teamColor } from "./team-colors.js";

function element(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function outcomeLabel(outcome, match) {
  return outcome === "draw" ? "Draw · 引き分け" : outcome === "home" ? match.homeTeam.name : match.awayTeam.name;
}

export function MatchCard(match, { previous, demo }) {
  const card = element("article", "match-card");
  card.dataset.matchId = match.id;
  card.setAttribute("aria-label", `${match.homeTeam.name} 対 ${match.awayTeam.name}`);
  const top = element("div", "card-topline");
  const time = element("time", "kickoff", formatKickoff(match.kickoffAt));
  time.dateTime = match.kickoffAt;
  top.append(time, element("span", "match-state", demo ? "DEMO" : previous ? "FULL TIME" : "PRE MATCH"));

  const fixture = element("div", "fixture");
  for (const side of ["home", "away"]) {
    const team = match[`${side}Team`];
    const teamNode = element("div", `fixture-team ${side}`);
    const accent = element("span", "team-accent");
    accent.style.backgroundColor = teamColor(team.id);
    accent.setAttribute("aria-hidden", "true");
    teamNode.append(accent, element("span", "venue-label", side.toUpperCase()), element("h3", "team-name", team.name));
    fixture.append(teamNode);
    if (side === "home") {
      const score = previous ? `${match.result.homeScore} − ${match.result.awayScore}` : "VS";
      fixture.append(element("div", previous ? "fixture-score" : "fixture-versus", score));
    }
  }
  const heading = element("p", "bar-heading", "WIN PROBABILITY");
  const probabilities = match.prediction.probabilities;
  const bar = PredictionProbabilityBar({
    homeProbability: probabilities.home, drawProbability: probabilities.draw, awayProbability: probabilities.away,
    homeColor: teamColor(match.homeTeam.id), awayColor: teamColor(match.awayTeam.id),
    homeLabel: match.homeTeam.name, awayLabel: match.awayTeam.name,
  });
  const outcomes = highestProbabilityOutcomes(probabilities);
  const details = element("div", "prediction-details");
  const pick = element("div", "detail-item");
  pick.append(element("span", "detail-label", "AI PICK"),
    element("strong", "pick-value", outcomes.map(outcome => outcomeLabel(outcome, match)).join(" / ")));
  if (outcomes.length > 1) pick.append(element("span", "tie-note", "同率最高 · HIT/MISS判定対象外"));
  details.append(pick);
  if (previous) {
    const actual = actualOutcome(match.result);
    const result = element("div", "detail-item result-item");
    result.append(element("span", "detail-label", "RESULT"), element("strong", "result-value", actual.toUpperCase()));
    details.append(result);
    const hit = outcomes.length === 1 && outcomes[0] === actual;
    details.append(element("span", `outcome-badge ${outcomes.length > 1 ? "tied" : hit ? "hit" : "miss"}`,
      outcomes.length > 1 ? "— 同率" : hit ? "✓ HIT" : "× MISS"));
  } else {
    details.append(element("span", "prediction-note", "最も確率の高い結果"));
  }
  const saved = element("p", "saved-note", demo ? "架空の予想・結果を使ったUIプレビュー" : "試合前に保存された予想を表示");
  saved.title = `予想保存時刻: ${match.prediction.generatedAt}`;
  card.append(top, fixture, heading, bar, details, saved);
  return card;
}

export function renderDashboard(data, { demo = false } = {}) {
  validateDashboard(data, { demo });
  const empty = data.previousRound.matches.length + data.nextRound.matches.length === 0;
  const notice = document.querySelector("#data-status");
  const message = demo ? "UI DEMO / 架空データのプレビューです。実データではありません。"
    : empty ? "Champion専用の保存済み表示データは未接続です。研究データは使用していません。"
      : "CHAMPION A / 保存済みの正式運用予想のみを表示しています。";
  notice.replaceChildren(element("span", "notice-message", message));
  if (!demo && data.updatedAt) {
    notice.append(element("span", "notice-updated", `公式データ観測: ${formatKickoff(data.updatedAt)} JST`));
  }
  document.querySelector("#preview-link").href = demo ? "/" : "/?demo=1";
  document.querySelector("#preview-link").textContent = demo ? "通常画面へ戻る ↗" : "UIデモを見る ↗";
  for (const [key, previous, selector] of [["previousRound", true, "previous"], ["nextRound", false, "next"]]) {
    const round = data[key];
    document.querySelector(`#${selector}-label`).textContent = `${round.label} · ${round.matches.length} MATCHES`;
    const container = document.querySelector(`#${selector}-matches`);
    const cards = round.matches.map(match => MatchCard(match, { previous, demo }));
    if (cards.length === 0) {
      const placeholder = element("div", "empty-state");
      placeholder.append(element("span", "empty-symbol", previous ? "01" : "02"),
        element("h3", "", previous ? "保存済み予想と結果を待っています" : "次節の保存済み予想を待っています"),
        element("p", "", "Champion専用のデータ接続後に表示します。ここで新しい予測は生成しません。"));
      container.replaceChildren(placeholder);
    } else container.replaceChildren(...cards);
  }
  notice.dataset.state = demo ? "demo" : empty ? "empty" : "operational";
}

async function connectLiveUpdates(initialData) {
  const response = await fetch("/api/update-status", { cache: "no-store", credentials: "same-origin" });
  if (!response.ok) return;
  const initialStatus = await response.json();
  if (initialStatus.pollEnabled !== true) return;
  const interval = initialStatus.pollSeconds;
  if (!Number.isInteger(interval) || interval < 10 || interval > 3600) return;
  const panel = document.querySelector("#update-status");
  const message = document.querySelector("#update-message");
  const button = document.querySelector("#reload-dashboard");
  let signature = JSON.stringify(initialData), busy = false;
  panel.hidden = false;
  function show(status) {
    if (!["idle", "updating", "ready", "error"].includes(status.state)) throw new Error("更新状態が不正です");
    panel.dataset.state = status.state;
    const labels = { idle: "定期更新を待っています", updating: "公式データを確認・更新しています",
      ready: "更新済み", error: "更新できませんでした。前回の正常な表示を保持しています" };
    message.textContent = labels[status.state] + (status.lastSuccessAt
      ? " · 最終成功: " + formatKickoff(status.lastSuccessAt) + " JST" : "");
  }
  show(initialStatus);
  async function reload() {
    if (busy) return;
    busy = true; button.disabled = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const options = { cache: "no-store", credentials: "same-origin", signal: controller.signal };
      const [dataResponse, statusResponse] = await Promise.all([
        fetch("/api/dashboard", options), fetch("/api/update-status", options)]);
      if (!dataResponse.ok || !statusResponse.ok) throw new Error("再読込に失敗しました");
      const [data, status] = await Promise.all([dataResponse.json(), statusResponse.json()]);
      validateDashboard(data);
      show(status);
      if (JSON.stringify(data) !== signature) {
        renderDashboard(data);
        signature = JSON.stringify(data);
      }
    } catch {
      panel.dataset.state = "error";
      message.textContent = "再読込できませんでした。前回の正常な表示を保持しています";
    } finally {
      clearTimeout(timeout); busy = false; button.disabled = false;
    }
  }
  button.addEventListener("click", reload);
  async function poll() { await reload(); setTimeout(poll, interval * 1000); }
  setTimeout(poll, interval * 1000);
}

async function start() {
  try {
    const demo = new URLSearchParams(location.search).get("demo") === "1";
    let data;
    if (demo) {
      data = (await import("./demo-data.js")).DEMO_DATA;
    } else {
      const response = await fetch("/api/dashboard", { cache: "no-store", credentials: "same-origin" });
      if (!response.ok) throw new Error("表示用APIからデータを取得できませんでした");
      data = await response.json();
    }
    renderDashboard(data, { demo });
    if (!demo) connectLiveUpdates(data).catch(() => {});
  } catch (error) {
    // Fail closed. Never fall back to synthetic or research predictions on API/schema failure.
    document.querySelector("#data-status").dataset.state = "error";
    document.querySelector("#data-status").textContent = "表示を停止しました。データの接続・契約を確認してください。";
    const notice = document.querySelector("#dashboard-error");
    notice.hidden = false;
    notice.textContent = error.message;
    for (const id of ["previous-matches", "next-matches"]) document.getElementById(id).replaceChildren();
  }
}

start();
