import { PredictionProbabilityBar } from "./components/prediction-probability-bar.js";
import { validateDashboard, highestProbabilityOutcomes, actualOutcome, formatKickoff } from "./dashboard-data.js";
import { teamColor } from "./team-colors.js";
import { validateWeekend, verifyWeekendBinding } from "./weekend-data.js";

function element(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function outcomeLabel(outcome, match) {
  return outcome === "draw" ? "Draw · 引き分け" : outcome === "home" ? match.homeTeam.name : match.awayTeam.name;
}

/** One compact row; picks and ties always use the original saved precision. */
export function SummaryRow(match, { previous, demo }) {
  const row = element("tr", "summary-row");
  row.dataset.matchId = match.id;
  const cell = (label, content, className = "") => {
    const td = element("td", className);
    td.dataset.label = label;
    td.append(typeof content === "string" ? document.createTextNode(content) : content);
    row.append(td);
    return td;
  };
  const time = element("time", "", `${formatKickoff(match.kickoffAt)} JST`);
  time.dateTime = match.kickoffAt;
  cell("日時（JST）", time, "summary-time");
  cell("HOME", match.homeTeam.name, "summary-home-team");
  cell("AWAY", match.awayTeam.name, "summary-away-team");
  if (!previous && !match.prediction) {
    cell("AI PICK", match.warning || "予測未作成", "summary-pick");
    cell("HOME / DRAW / AWAY", "— 確率未保存", "summary-probabilities");
    return row;
  }
  const picks = highestProbabilityOutcomes(match.prediction.probabilities);
  cell("AI PICK", `${demo ? "DEMO · " : ""}${picks.map(p => outcomeLabel(p, match)).join(" / ")}${picks.length > 1 ? "（同率最高）" : ""}`, "summary-pick");
  if (previous) {
    const actual = actualOutcome(match.result);
    cell("スコア", `${match.result.homeScore} − ${match.result.awayScore}`);
    cell("実結果", actual.toUpperCase());
    const badge = element("span", `outcome-badge ${picks.length > 1 ? "tied" : picks[0] === actual ? "hit" : "miss"}`,
      picks.length > 1 ? "— 判定対象外（同率最高）" : picks[0] === actual ? "✓ HIT" : "× MISS");
    cell("判定", badge, "summary-verdict");
  } else {
    const p = match.prediction.probabilities;
    const bar = PredictionProbabilityBar({homeProbability:p.home, drawProbability:p.draw, awayProbability:p.away,
      homeColor:teamColor(match.homeTeam.id), awayColor:teamColor(match.awayTeam.id), homeLabel:match.homeTeam.name, awayLabel:match.awayTeam.name});
    cell("HOME / DRAW / AWAY", bar, "summary-probabilities");
    row.title = `Champion A · 予想保存: ${formatKickoff(match.prediction.generatedAt)} JST${match.fixtureStatus === "completed" ? " · 試合終了" : ""}`;
  }
  return row;
}

function renderSummary(data, {demo, view, weekend}) {
  const active = ["previous", "next"].includes(view);
  document.body.dataset.view = active ? view : "home";
  document.title = `${demo ? "DEMO / " : ""}J1AI — ${active ? view === "previous" ? "前節の答え合わせ" : "週末の予想" : "Matchday"}`;
  document.querySelector("#round-summary").hidden = !active;
  document.querySelector("#home-dashboard").hidden = active;
  document.querySelector("#home-shortcuts").hidden = active;
  const home = demo ? "/?demo=1" : "/";
  document.querySelector("#summary-home").href = home;
  document.querySelector(".brand").href = home;
  for (const [i, name] of ["next", "previous"].entries()) {
    document.querySelectorAll(".summary-shortcut")[i].href = `/?${demo ? "demo=1&" : ""}view=${name}`;
  }
  for (const [i, name] of ["previous", "next"].entries()) {
    document.querySelectorAll("header nav a")[i].href = active ? `/?${demo ? "demo=1&" : ""}view=${name}` : `#${name}-round`;
  }
  const host = document.querySelector("#summary-matches");
  host.replaceChildren();
  if (!active) return;
  const previous = view === "previous";
  const round = !previous && weekend ? {label:weekend.period ? `週末の予想 · ${weekend.period.join("〜")}` : "日程未確認", matches:weekend.matches} : data[previous ? "previousRound" : "nextRound"];
  document.querySelector("#summary-title").textContent = previous ? "前節の答え合わせ" : "週末の予想";
  document.querySelector("#summary-label").textContent = `${round.label} · ${round.matches.length}件${demo ? " · DEMO" : ""}`;
  document.querySelector("#summary-range").textContent = `表示範囲：${round.label}。公式カレンダーの対象日・期間（JST）で選ばれた保存済み${round.matches.length}試合です。${previous ? "" : "未終了試合のみを表示します。"}節全体を網羅する一覧ではありません。${demo ? " 架空データのDEMOです。" : ""}`;
  if (!previous) {
    const saved = round.matches.filter(m => m.prediction).length;
    document.querySelector("#summary-range").textContent = weekend
      ? `表示範囲：${round.label}（JST）。公式対象${round.matches.length}試合 / 保存済み${saved}件 / 未保存・保留${round.matches.length-saved}件。${weekend.period ? "土日両日を表示。金曜・月曜の試合は追加しません。" : "確認可能な対象日程がありません。"} 表示用データ更新: ${formatKickoff(weekend.updatedAt)} JST`
      : `${round.label}。期間（JST）の保存済み${round.matches.length}試合・未終了試合のみ。節全体を網羅しません。${demo ? "DEMO · 架空データ。" : "日程未確認（週末sidecar未接続）。"}未保存予想は補完しません。`;
    if (weekend?.excludedSavedFixtureIds.length) document.querySelector("#summary-range").textContent += ` 警告：改日程により週末対象外の保存済み予測${weekend.excludedSavedFixtureIds.length}件。保存値は変更していません。`;
  }
  if (!round.matches.length) {
    host.append(element("p", "empty-state", weekend ? "日程未確認：確認可能な週末日程がありません。" : "この表示範囲の保存済みデータはありません。新しい予想や結果を補完しません。"));
    return;
  }
  const table = element("table", "summary-table");
  const caption = element("caption", "sr-only", `${round.label} / ${previous ? "予想と実結果" : "保存済み予想"}${demo ? " / DEMO" : ""}`);
  const head = element("thead", "");
  const headings = element("tr", "");
  for (const label of ["日時（JST）", "HOME", "AWAY", "AI PICK", ...(previous ? ["スコア", "実結果", "判定"] : ["勝利確率 HOME / DRAW / AWAY"])]) {
    const th = element("th", "", label); th.scope = "col"; headings.append(th);
  }
  head.append(headings);
  const body = element("tbody", "");
  if (!previous && weekend?.period) {
    for (const [index, day] of weekend.period.entries()) {
      const group = element("tr", "summary-day"); const heading = element("th", "", `${day}（${index === 0 ? "土" : "日"}曜日）`);
      heading.colSpan = 5; heading.scope = "rowgroup"; group.append(heading); body.append(group);
      const matches = round.matches.filter(m => new Intl.DateTimeFormat("en-CA", {timeZone:"Asia/Tokyo", year:"numeric", month:"2-digit", day:"2-digit"}).format(new Date(m.kickoffAt)) === day);
      body.append(...matches.map(match => SummaryRow(match, {previous, demo})));
      if (!matches.length) { const line = element("tr", ""); const cell = element("td", "", "確認済み対象試合なし"); cell.colSpan=5;line.append(cell);body.append(line); }
    }
  } else body.append(...round.matches.map(match => SummaryRow(match, {previous, demo})));
  table.append(caption, head, body); host.append(table);
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

export function renderDashboard(data, { demo = false, view = new URLSearchParams(location.search).get("view"), weekend = null } = {}) {
  validateDashboard(data, { demo });
  if (weekend) { if (demo) throw new Error("DEMOに運用週末データは接続できません"); validateWeekend(weekend, data); }
  const empty = data.previousRound.matches.length + data.nextRound.matches.length === 0;
  const notice = document.querySelector("#data-status");
  const message = demo ? "UI DEMO / 架空データのプレビューです。実データではありません。"
    : empty ? "Champion専用の保存済み表示データは未接続です。研究データは使用していません。"
      : "CHAMPION A / 保存済みの正式運用予想のみを表示しています。";
  notice.replaceChildren(element("span", "notice-message", message));
  if (!demo && data.updatedAt) {
    notice.append(element("span", "notice-updated", `表示用データ更新: ${formatKickoff(data.updatedAt)} JST`));
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
  document.querySelector("#preview-link").href = demo ? `/${view === "next" || view === "previous" ? `?view=${view}` : ""}` : `/?demo=1${view === "next" || view === "previous" ? `&view=${view}` : ""}`;
  renderSummary(data, {demo, view, weekend});
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
    let weekend = null;
    if (!demo && new URLSearchParams(location.search).get("view") === "next") {
      const response = await fetch("/api/weekend", {cache:"no-store", credentials:"same-origin"});
      if (response.status !== 404) {
        if (!response.ok) throw new Error("週末日程を読み取れません。表示を保留します。");
        weekend = await verifyWeekendBinding(await response.json(), data);
      }
    }
    renderDashboard(data, { demo, weekend });
  } catch (error) {
    // Fail closed. Never fall back to synthetic or research predictions on API/schema failure.
    document.querySelector("#data-status").dataset.state = "error";
    document.querySelector("#data-status").textContent = "表示を停止しました。データの接続・契約を確認してください。";
    const notice = document.querySelector("#dashboard-error");
    notice.hidden = false;
    notice.textContent = error.message;
    for (const id of ["previous-matches", "next-matches", "summary-matches"]) document.getElementById(id).replaceChildren();
  }
}

start();
