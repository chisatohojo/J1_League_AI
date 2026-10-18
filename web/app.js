import { PredictionProbabilityBar } from "./components/prediction-probability-bar.js";
import { validateDashboard, highestProbabilityOutcomes, actualOutcome, formatKickoff } from "./dashboard-data.js";
import { teamColor } from "./team-colors.js";
import { validateRetrospective, selectDisplayPrediction, RETROSPECTIVE_TYPE } from "./retrospective-data.js";

function element(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function outcomeLabel(outcome, match) {
  return outcome === "draw" ? "Draw · 引き分け" : outcome === "home" ? match.homeTeam.name : match.awayTeam.name;
}

export function MatchCard(match, { previous, demo, overlay = null }) {
  const display = selectDisplayPrediction(match, overlay);
  const reconstruction = display?.kind === RETROSPECTIVE_TYPE;
  const prediction = display?.value ?? null;
  const finished = match.status ? match.status === "completed" : previous;
  const pending = match.status === "candidate";
  const card = element("article", `match-card${prediction === null ? " no-prediction" : ""}${reconstruction ? " retrospective-card" : ""}`);
  if (display) card.dataset.predictionType = display.kind;
  card.dataset.matchId = match.id;
  if (match.status) card.dataset.status = match.status;
  card.setAttribute("aria-label", `${match.homeTeam.name} 対 ${match.awayTeam.name}`);
  const top = element("div", "card-topline");
  const time = element("time", "kickoff", formatKickoff(match.kickoffAt));
  time.dateTime = match.kickoffAt;
  top.append(time, element("span", "match-state", demo ? "DEMO" : pending ? "結果確認中" : finished ? "FULL TIME" : "PRE MATCH"));

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
      const score = finished ? `${match.result.homeScore} − ${match.result.awayScore}` : "VS";
      fixture.append(element("div", finished ? "fixture-score" : "fixture-versus", score));
    }
  }
  if (prediction === null) {
    card.append(top, fixture, element("p", "no-prediction-note", finished || pending ? "AI予測なし" : "AI予測は未生成"));
    return card;
  }
  const heading = element("p", "bar-heading", "WIN PROBABILITY");
  const probabilities = prediction.probabilities;
  const bar = PredictionProbabilityBar({
    homeProbability: probabilities.home, drawProbability: probabilities.draw, awayProbability: probabilities.away,
    homeColor: teamColor(match.homeTeam.id), awayColor: teamColor(match.awayTeam.id),
    homeLabel: match.homeTeam.name, awayLabel: match.awayTeam.name,
  });
  const outcomes = reconstruction ? [prediction.predictedOutcome] : highestProbabilityOutcomes(probabilities);
  const details = element("div", "prediction-details");
  const pick = element("div", "detail-item");
  pick.append(element("span", "detail-label", "AI PICK"),
    element("strong", "pick-value", outcomes.map(outcome => outcomeLabel(outcome, match)).join(" / ")));
  if (outcomes.length > 1) pick.append(element("span", "tie-note", "同率最高 · HIT/MISS判定対象外"));
  details.append(pick);
  if (finished) {
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
  const saved = element("p", "saved-note", reconstruction ? "当時の試合前保存予測ではありません"
    : demo ? "架空の予想・結果を使ったUIプレビュー" : "試合前に保存された予想を表示");
  if (reconstruction) {
    const badge = element("strong", "retrospective-label", "後日再現予測");
    const time = element("time", "recalculated-at", "再計算: " + new Intl.DateTimeFormat("ja-JP", {
      timeZone:"Asia/Tokyo", year:"numeric", month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit", hour12:false,
    }).format(new Date(prediction.calculatedAt)) + " JST");
    time.dateTime = prediction.calculatedAt; time.title = prediction.calculatedAt;
    card.append(top, fixture, badge, heading, bar, details, time, saved);
  } else {
    saved.title = `予想保存時刻: ${prediction.generatedAt}`;
    card.append(top, fixture, heading, bar, details, saved);
  }
  return card;
}

export function renderDashboard(data, { demo = false, overlay = null } = {}) {
  validateDashboard(data, { demo });
  if (overlay) validateRetrospective(overlay, data);
  const rounds = data.schemaVersion === 2;
  document.body.classList.toggle("round-view", rounds);
  const empty = data.previousRound.matches.length + data.nextRound.matches.length === 0;
  const notice = document.querySelector("#data-status");
  const message = demo ? "UI DEMO / 架空データのプレビューです。実データではありません。"
    : empty ? "Champion専用の保存済み表示データは未接続です。研究データは使用していません。"
      : overlay ? "CHAMPION A / 公式日程・試合前保存予測・後日再現予測を表示しています。種別をカードに明示しています。"
      : rounds ? "CHAMPION A / 公式日程と保存済み予測を表示しています。予測なしの試合に確率は補完しません。"
        : "CHAMPION A / 保存済みの正式運用予想のみを表示しています。";
  notice.replaceChildren(element("span", "notice-message", message));
  if (!demo && data.updatedAt) {
    notice.append(element("span", "notice-updated", `公式データ観測: ${formatKickoff(data.updatedAt)} JST`));
  }
  if (overlay) {
    notice.append(element("p", "retrospective-notice", "確認用画面 / 保存済みの試合前予測を優先し、未保存の確定試合には後日再現予測を表示。ライブ成績とは合算しません。"));
    if (overlay.diagnostics.length) notice.append(element("p", "overlay-diagnostics",
      `再現表示を保留: ${overlay.diagnostics.length}件（公式情報との不一致）`));
  }
  document.querySelector("#preview-link").href = demo ? "/" : "/?demo=1";
  document.querySelector("#preview-link").textContent = demo ? "通常画面へ戻る ↗" : "UIデモを見る ↗";
  for (const [key, previous, selector] of [["previousRound", true, "previous"], ["nextRound", false, "next"]]) {
    const round = data[key];
    document.querySelector(`#${selector}-title`).textContent = rounds
      ? round.label : previous ? "前節の予想結果" : "次節の予想";
    if (!previous) document.querySelector('nav a[href="#next-round"]').textContent = rounds && round.kind === "current" ? "今節の試合" : "次節の予想";
    document.querySelector(`#${selector}-label`).textContent = `${round.label} · ${round.matches.length} MATCHES`;
    const container = document.querySelector(`#${selector}-matches`);
    const cards = [];
    let day = null;
    for (const match of round.matches) {
      if (rounds) {
        const matchDay = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(match.kickoffAt));
        if (matchDay !== day) {
          const divider = element("h3", "match-date-divider");
          const date = element("time", "", new Intl.DateTimeFormat("ja-JP", { timeZone: "Asia/Tokyo", month: "long", day: "numeric", weekday: "short" }).format(new Date(match.kickoffAt)));
          date.dateTime = matchDay;
          divider.append(date); cards.push(divider); day = matchDay;
        }
      }
      cards.push(MatchCard(match, { previous, demo, overlay }));
    }
    if (cards.length === 0) {
      const placeholder = element("div", "empty-state");
      placeholder.append(element("span", "empty-symbol", previous ? "01" : "02"),
        element("h3", "", previous ? "保存済み予想と結果を待っています" : "次節の保存済み予想を待っています"),
        element("p", "", "Champion専用のデータ接続後に表示します。ここで新しい予測は生成しません。"));
      container.replaceChildren(placeholder);
    } else container.replaceChildren(...cards);
  }
  notice.dataset.state = demo ? "demo" : empty ? "empty" : "operational";
  renderHistory(data, overlay);
  document.querySelector("#previous-round .section-note").textContent = overlay
    ? "試合前保存予測と後日再現予測を区別して、正式結果と照合。"
    : "試合前の保存済み予想と、実際の結果を並べて確認。";
}

function renderHistory(data, overlay) {
  const existing = document.getElementById("retrospective-history");
  if (!overlay) { existing?.remove(); return; }
  const selected = existing?.querySelector("select")?.value;
  const opened = existing?.open ?? false;
  const panel = element("details", "history-section"); panel.id = "retrospective-history";
  panel.open = opened;
  panel.append(element("summary", "", "過去の節を見る · 後日再現予測を含む履歴"));
  panel.append(element("p", "history-note", "試合前保存予測と後日再現予測は別の種別です。成績は合算しません。当時の公式掲載状況は未立証です。"));
  const label = element("label", "history-select-label", "表示する節 ");
  const select = element("select", ""); select.id = "history-round";
  for (const section of overlay.historyRounds) {
    const option = element("option", "", `${section.label} · ${section.matches.length}試合`);
    option.value = String(section.number); select.append(option);
  }
  select.value = overlay.historyRounds.some(r => String(r.number) === selected) ? selected : String(data.previousRound.number ?? overlay.historyRounds[0].number);
  if (!select.value) select.value = String(overlay.historyRounds[0].number);
  label.append(select); panel.append(label);
  const container = element("div", "match-grid"); container.id = "history-matches"; panel.append(container);
  function show() {
    if (!panel.open) { container.replaceChildren(); return; }
    const section = overlay.historyRounds.find(r => String(r.number) === select.value);
    const cards = []; let day = null;
    for (const match of section.matches) {
      const matchDay = new Intl.DateTimeFormat("sv-SE", { timeZone:"Asia/Tokyo", year:"numeric", month:"2-digit", day:"2-digit" }).format(new Date(match.kickoffAt));
      if (matchDay !== day) { cards.push(element("h3", "match-date-divider", matchDay)); day = matchDay; }
      cards.push(MatchCard(match, { previous:true, demo:false, overlay }));
    }
    container.replaceChildren(...cards);
  }
  select.addEventListener("change", show); panel.addEventListener("toggle", show);
  if (existing) existing.replaceWith(panel); else document.querySelector(".rounds").append(panel);
  show();
}

async function fetchOverlay(data) {
  const response = await fetch("/api/retrospective", { cache:"no-store", credentials:"same-origin" });
  if (!response.ok) throw new Error("後日再現データを接続できません。通常画面は ?retrospective=1 を外して開けます。");
  return validateRetrospective(await response.json(), data);
}

async function connectLiveUpdates(initialData, initialOverlay = null) {
  const response = await fetch("/api/update-status", { cache: "no-store", credentials: "same-origin" });
  if (!response.ok) return;
  const initialStatus = await response.json();
  if (initialStatus.pollEnabled !== true) return;
  const interval = initialStatus.pollSeconds;
  if (!Number.isInteger(interval) || interval < 10 || interval > 3600) return;
  const panel = document.querySelector("#update-status");
  const message = document.querySelector("#update-message");
  const button = document.querySelector("#reload-dashboard");
  let signature = JSON.stringify([initialData, initialOverlay]), busy = false;
  panel.hidden = false;
  function show(status) {
    if (!["idle", "updating", "ready", "error"].includes(status.state)) throw new Error("更新状態が不正です");
    panel.dataset.state = status.state;
    const labels = { idle: "定期更新を待っています", updating: "公式データを確認・更新しています",
      ready: "更新済み", error: "更新できませんでした。前回の正常な表示を保持しています" };
    message.textContent = (initialOverlay ? "確認用表示 / " : "") + labels[status.state] + (status.lastSuccessAt
      ? (initialOverlay ? " · 表示JSON生成: " : " · 最終成功: ") + formatKickoff(status.lastSuccessAt) + " JST" : "");
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
      const overlay = initialOverlay ? await fetchOverlay(data) : null;
      show(status);
      if (JSON.stringify([data, overlay]) !== signature) {
        renderDashboard(data, { overlay });
        signature = JSON.stringify([data, overlay]);
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
    const overlay = !demo && new URLSearchParams(location.search).get("retrospective") === "1" ? await fetchOverlay(data) : null;
    renderDashboard(data, { demo, overlay });
    if (!demo) connectLiveUpdates(data, overlay).catch(() => {});
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
