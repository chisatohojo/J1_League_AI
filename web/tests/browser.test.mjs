import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { existsSync } from 'node:fs';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import http from 'node:http';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { syntheticRetrospective, syntheticGeneration } from './retrospective-fixture.mjs';
import { validateRetrospective, selectDisplayPrediction } from '../retrospective-data.js';

const webRoot = fileURLToPath(new URL('../', import.meta.url));
const browserPath = [
  process.env.J1AI_BROWSER_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].find((candidate) => candidate && existsSync(candidate));

class DevTools {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    socket.addEventListener('message', ({ data }) => {
      const message = JSON.parse(data);
      if (!message.id) return;
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if (message.error) pending.reject(new Error(JSON.stringify(message.error)));
      else pending.resolve(message.result);
    });
    socket.addEventListener('close', () => {
      for (const pending of this.pending.values()) {
        pending.reject(new Error('Browser DevTools connection closed'));
      }
      this.pending.clear();
    });
  }

  static async connect(url) {
    const socket = new WebSocket(url);
    await new Promise((resolve, reject) => {
      socket.addEventListener('open', resolve, { once: true });
      socket.addEventListener('error', reject, { once: true });
    });
    return new DevTools(socket);
  }

  async send(method, params = {}) {
    const id = this.nextId++;
    const result = new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
    this.socket.send(JSON.stringify({ id, method, params }));
    return result;
  }

  async evaluate(expression) {
    const response = await this.send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (response.exceptionDetails) {
      throw new Error(response.exceptionDetails.exception?.description
        ?? response.exceptionDetails.text);
    }
    return response.result.value;
  }

  async until(expression, description, timeout = 10000) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      if (await this.evaluate(expression)) return;
      await delay(50);
    }
    throw new Error(`Timed out waiting for ${description}`);
  }

  close() {
    this.socket.close();
  }
}

async function startBrowser() {
  const profile = await mkdtemp(path.join(tmpdir(), 'j1ai-browser-'));
  const child = spawn(browserPath, [
    '--headless=new',
    '--disable-gpu',
    '--disable-background-networking',
    '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost',
    '--no-first-run',
    '--no-default-browser-check',
    '--remote-debugging-port=0',
    `--user-data-dir=${profile}`,
    'about:blank',
  ], { windowsHide: true, stdio: 'ignore' });
  let startupError;
  child.once('error', (error) => { startupError = error; });
  const stop = async () => {
    if (child.exitCode === null) {
      const exited = once(child, 'exit');
      child.kill();
      await exited;
    }
    // This exact directory was created by mkdtemp above; never remove a supplied path.
    assert.equal(path.dirname(path.resolve(profile)), path.resolve(tmpdir()));
    assert.ok(path.basename(profile).startsWith('j1ai-browser-'));
    await rm(profile, { recursive: true, force: true, maxRetries: 20, retryDelay: 100 });
  };
  try {
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
      if (startupError) throw startupError;
      if (child.exitCode !== null) throw new Error('Headless browser exited during startup');
      try {
        const activePort = await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8');
        const port = activePort.split('\n')[0].trim();
        const response = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {
          method: 'PUT',
        });
        const page = await response.json();
        const client = await DevTools.connect(page.webSocketDebuggerUrl);
        await client.send('Page.enable');
        await client.send('Runtime.enable');
        return { client, stop };
      } catch (error) {
        if (error.code !== 'ENOENT' && Date.now() + 100 >= deadline) throw error;
      }
      await delay(100);
    }
    throw new Error('Headless browser did not expose its local DevTools endpoint');
  } catch (error) {
    await stop();
    throw error;
  }
}

async function startServer(initialPayload) {
  let payload = initialPayload;
  let apiStatus = 200;
  let updateStatus = null;
  let overlay = null;
  let presentation = null;
  const server = http.createServer(async (request, response) => {
    try {
      const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
      if(pathname==='/api/presentation') {
        response.writeHead(presentation?200:404,{'Content-Type':'application/json'});
        response.end(JSON.stringify(presentation));return;
      }
      if (pathname === '/api/retrospective') {
        response.writeHead(overlay ? 200 : 404, { 'Content-Type':'application/json' });
        response.end(JSON.stringify(overlay));
        return;
      }
      if (pathname === '/api/update-status' && updateStatus) {
        response.writeHead(200, { 'Content-Type': 'application/json' });
        response.end(JSON.stringify(updateStatus));
        return;
      }
      if (pathname === '/api/dashboard') {
        response.writeHead(apiStatus, { 'Content-Type': 'application/json' });
        response.end(JSON.stringify(payload));
        return;
      }
      const relative = pathname === '/' ? 'index.html' : decodeURIComponent(pathname.slice(1));
      const target = path.resolve(webRoot, relative);
      if (!target.startsWith(`${path.resolve(webRoot)}${path.sep}`)) {
        response.writeHead(403).end();
        return;
      }
      const contents = await readFile(target);
      const contentTypes = {
        '.html': 'text/html; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.js': 'text/javascript; charset=utf-8',
        '.svg': 'image/svg+xml',
      };
      response.writeHead(200, { 'Content-Type': contentTypes[path.extname(target)]
        ?? 'application/octet-stream' });
      response.end(contents);
    } catch {
      response.writeHead(404).end();
    }
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return {
    origin: `http://127.0.0.1:${server.address().port}`,
    setPayload(next, status = 200) { payload = next; apiStatus = status; },
    setUpdateStatus(next) { updateStatus = next; },
    setOverlay(next) { overlay = next; },
    setPresentation(next) { presentation=next; },
    stop: () => new Promise((resolve, reject) => server.close((error) => {
      if (error) reject(error);
      else resolve();
    })),
  };
}

async function captureScreenshot(client, name) {
  if (!process.env.J1AI_SCREENSHOT_DIR) return;
  const outputDirectory = path.resolve(process.env.J1AI_SCREENSHOT_DIR);
  await mkdir(outputDirectory, { recursive: true });
  const { data } = await client.send('Page.captureScreenshot', { format: 'png' });
  await writeFile(path.join(outputDirectory, name), Buffer.from(data, 'base64'));
}

async function navigate(client, url, condition) {
  await client.send('Page.navigate', { url });
  await client.until(`location.href === ${JSON.stringify(url)}
    && document.readyState === 'complete' && (${condition})`, 'dashboard render');
}

async function viewport(client, width) {
  await client.send('Emulation.setDeviceMetricsOverride', {
    width,
    height: 1100,
    deviceScaleFactor: 1,
    mobile: width < 600,
  });
}

// Integration cases are below. Only synthetic fixtures are served; repository
// prediction CSVs, model artifacts, outcomes, and sealed research data are never read.

function syntheticMatch(id, probabilities, completed = false) {
  const match = {
    id,
    homeTeam: { id: 'team_0003', name: 'FC東京' },
    awayTeam: { id: 'team_0030', name: '浦和レッズ' },
    kickoffAt: completed ? '2030-10-02T19:00:00+09:00' : '2030-10-09T19:00:00+09:00',
    prediction: {
      source: 'saved_pre_match',
      generatedAt: '2030-10-01T12:00:00+09:00',
      probabilities,
    },
  };
  if (completed) match.result = { homeScore: 1, awayScore: 2 };
  return match;
}

function dashboardPayload(previous = [], next = []) {
  return {
    schemaVersion: 1,
    mode: 'operational',
    model: { name: 'Champion A', version: 'operational_champion_20260922_v1' },
    updatedAt: '2030-10-08T10:00:00+09:00',
    previousRound: { label: '前節 (合成テスト)', matches: previous },
    nextRound: { label: '次節 (合成テスト)', matches: next },
  };
}

const renderedBars = `Array.from(document.querySelectorAll('.probability-bar')).map(bar => ({
  display: getComputedStyle(bar).display,
  direction: getComputedStyle(bar).flexDirection,
  segments: Array.from(bar.children).map(segment => ({
    outcome: segment.dataset.outcome,
    width: Number.parseFloat(segment.style.width),
    color: getComputedStyle(segment).backgroundColor,
    left: segment.getBoundingClientRect().left,
    right: segment.getBoundingClientRect().right,
  })),
  labels: Array.from(bar.parentElement.querySelectorAll('.probability-label')).map(label => ({
    outcome: label.dataset.outcome,
    text: label.textContent,
    visible: getComputedStyle(label).display !== 'none'
      && getComputedStyle(label).visibility !== 'hidden'
      && label.getBoundingClientRect().width > 0
      && label.getBoundingClientRect().height > 0,
  })),
}))`;

function assertBar(bar, expectedWidths) {
  assert.equal(bar.display, 'flex');
  assert.equal(bar.direction, 'row');
  assert.deepEqual(bar.segments.map((segment) => segment.outcome), ['home', 'draw', 'away']);
  assert.equal(bar.segments.length, 3, 'one continuous stack, not three separate bars');
  for (const [index, segment] of bar.segments.entries()) {
    assert.ok(Math.abs(segment.width - expectedWidths[index]) < 0.001,
      `CSSOM width ${segment.width}% follows expected ${expectedWidths[index]}%`);
    if (index) {
      assert.ok(Math.abs(segment.left - bar.segments[index - 1].right) < 1,
        'segments must meet without gaps');
    }
  }
  assert.deepEqual(bar.labels.map((label) => label.outcome), ['home', 'draw', 'away']);
  assert.ok(bar.labels.every((label) => label.visible && /\d.*%/.test(label.text)),
    'external numeric labels remain visible, including zero/tiny segments');
  assert.equal(bar.segments[1].color, 'rgb(100, 116, 139)', 'draw segment stays neutral gray');
}

test('home dashboard browser integration (synthetic data only)', {
  skip: !browserPath && 'Install local Chrome/Edge or set J1AI_BROWSER_PATH to run browser checks',
  timeout: 120000,
}, async (context) => {
  const server = await startServer(dashboardPayload());
  let browser;
  try {
    browser = await startBrowser();
  } catch (error) {
    await server.stop();
    throw error;
  }
  context.after(async () => {
    await browser.client.send('Browser.close').catch(() => {});
    browser.client.close();
    await browser.stop();
    await server.stop();
  });
  const { client } = browser;
  await viewport(client, 1280);

  await context.test('empty source never silently becomes fabricated Champion data', async () => {
    await navigate(client, `${server.origin}/?case=empty`,
      `document.querySelector('#data-status')?.dataset.state === 'empty'`);
    assert.equal(await client.evaluate(`document.querySelectorAll('.match-card').length`), 0);
    assert.equal(await client.evaluate(`document.querySelector('#dashboard-error').hidden`), true);
    assert.match(await client.evaluate(`document.body.textContent`), /ST2[\s\S]*SEALED/);
  });

  await context.test('explicit demo has previous/next cards sharing the same bar', async () => {
    await navigate(client, `${server.origin}/?demo=1`,
      `document.querySelector('#data-status')?.dataset.state === 'demo'`);
    const status = await client.evaluate(`document.querySelector('#data-status').textContent`);
    assert.match(status, /デモ|DEMO/i);
    assert.match(status, /実データではありません/);
    const sections = await client.evaluate(`['previous-matches', 'next-matches'].map(id => {
      const cards = document.querySelectorAll('#' + id + ' .match-card');
      return Array.from(cards).map(card => card.querySelectorAll('.probability-bar').length);
    })`);
    assert.ok(sections.every((bars) => bars.length > 0 && bars.every((count) => count === 1)));
    assert.equal(await client.evaluate(`document.querySelectorAll('.probability-bar').length`),
      sections.flat().length);
    await captureScreenshot(client, 'j1ai-home-desktop.png');
    await viewport(client, 375);
    await captureScreenshot(client, 'j1ai-home-mobile.png');
    for (const width of [320, 375, 1280]) {
      await viewport(client, width);
      assert.ok(await client.evaluate(`document.documentElement.scrollWidth <= window.innerWidth`),
        `full dashboard has no horizontal overflow at ${width}px`);
      assert.ok(await client.evaluate(`Array.from(document.querySelectorAll('.match-card, .probability-label'))
        .every(element => element.getBoundingClientRect().left >= 0
          && element.getBoundingClientRect().right <= innerWidth)`),
      `cards and numeric labels stay inside ${width}px viewport`);
      const bars = await client.evaluate(renderedBars);
      assert.ok(bars.every((bar) => bar.labels.length === 3 && bar.labels.every((label) => label.visible)));
    }
  });

  await context.test('saved probabilities are displayed unchanged and research stays sealed', async () => {
    server.setPayload(dashboardPayload(
      [syntheticMatch('previous-1', { home: 31, draw: 25, away: 44 }, true)],
      [syntheticMatch('next-1', { home: 44, draw: 25, away: 31 })],
    ));
    await navigate(client, `${server.origin}/?case=saved`,
      `document.querySelector('#data-status')?.dataset.state === 'operational'`);
    const bars = await client.evaluate(renderedBars);
    assert.equal(bars.length, 2);
    assertBar(bars[0], [31, 25, 44]);
    assertBar(bars[1], [44, 25, 31]);
    assert.ok(bars[0].labels[0].text.includes('31%'));
    assert.ok(bars[0].labels[1].text.includes('25%'));
    assert.ok(bars[0].labels[2].text.includes('44%'));
    assert.match(await client.evaluate(`document.querySelector('#previous-matches').textContent`),
      /HIT/);
    const research = await client.evaluate(`document.querySelector('#research-status, .research-status').textContent`);
    assert.match(research, /ST2/);
    assert.match(research, /SEALED/);
    assert.doesNotMatch(research, /Accuracy|Log\s*Loss|Brier|HIT|MISS|\d+\s*%/i);
    assert.doesNotMatch(await client.evaluate(`document.querySelector('#data-status').textContent`), /デモ/);
  });

  await context.test('RESULT names and draws preserve picks, probabilities and HIT/MISS in both prediction types', async () => {
    for (const [score, expectedSide] of [[{homeScore:2,awayScore:1},'home'],[{homeScore:1,awayScore:2},'away'],[{homeScore:0,awayScore:0},'draw']]) {
      const {data,overlay}=syntheticRetrospective();
      const longHome='ホームクラブの非常に長い正式名称'.repeat(9);
      const longAway='AwayFootballClubWithAVeryLongName'.repeat(5);
      const targets=[data.previousRound.matches[0],data.previousRound.matches[2]];
      for (const match of targets) {
        match.homeTeam.name=longHome;match.awayTeam.name=longAway;match.result=structuredClone(score);
        const historic=overlay.historyRounds[0].matches.find(m=>m.id===match.id);
        Object.assign(historic,structuredClone(match));
        const entry=overlay.entries.find(e=>e.fixtureKey===match.id);
        if(entry) {entry.result=structuredClone(score);entry.reconstruction.hit=expectedSide==='home';}
      }
      const unchanged=JSON.stringify({data,overlay});
      server.setPayload(data);server.setOverlay(overlay);
      await navigate(client,`${server.origin}/?retrospective=1&case=result-${expectedSide}`,
        "document.querySelectorAll('.result-value').length===18");
      for (const match of targets) {
        const display=selectDisplayPrediction(match,overlay);
        const id=JSON.stringify(match.id);
        const card=await client.evaluate(`(()=>{const c=Array.from(document.querySelectorAll('#previous-matches .match-card')).find(c=>c.dataset.matchId===${id});return {
          label:c.querySelector('.result-value').textContent,pick:c.querySelector('.pick-value').textContent,
          badge:c.querySelector('.outcome-badge').textContent,bar:c.querySelector('.prediction-probability').getAttribute('aria-label')};})()`);
        assert.equal(card.label,expectedSide==='draw'?'引き分け':expectedSide==='home'?longHome:longAway);
        const predicted=display.kind==='saved_pre_match'?'away':'home';
        assert.equal(card.pick,predicted==='home'?longHome:longAway);
        assert.equal(card.badge,predicted===expectedSide?'✓ HIT':'× MISS');
        for(const side of ['home','draw','away']) assert.ok(card.bar.includes(`${display.value.probabilities[side]}%`));
      }
      for(const width of [1280,375,320]) {
        await viewport(client,width);
        assert.ok(await client.evaluate("document.documentElement.scrollWidth<=innerWidth"));
        assert.ok(await client.evaluate(`Array.from(document.querySelectorAll('.result-value')).every(n=>{
          const card=n.closest('.match-card').getBoundingClientRect(),box=n.getBoundingClientRect();
          return box.left>=card.left && box.right<=card.right && n.scrollWidth<=n.clientWidth+1;
        })`),'long RESULT names wrap within their cards');
      }
      assert.equal(JSON.stringify({data,overlay}),unchanged);
    }
    server.setOverlay(null);
  });

  await context.test('zero/tiny/rounded bars stay legible and responsive without changing inputs', async () => {
    const probabilities = [[31, 25, 44], [0, 100, 0], [0.1, 99.8, 0.1], [33, 33, 33]];
    await client.evaluate(`(async () => {
      const { PredictionProbabilityBar } = await import('/components/prediction-probability-bar.js');
      const input = ${JSON.stringify(probabilities)};
      const snapshot = JSON.stringify(input);
      document.querySelectorAll('.match-card').forEach(card => card.remove());
      const host = document.createElement('div');
      host.id = 'component-tests';
      host.style.cssText = 'width:100%;max-width:600px;margin:0 auto;padding:16px;box-sizing:border-box;';
      input.forEach(([homeProbability, drawProbability, awayProbability]) => {
        host.append(PredictionProbabilityBar({homeProbability, drawProbability, awayProbability,
          homeColor:'#2459b5',awayColor:'#c83c44',homeLabel:'FC東京',awayLabel:'浦和レッズ'}));
      });
      document.querySelector('main').append(host);
      if (JSON.stringify(input) !== snapshot) throw new Error('Probability inputs mutated');
    })()`);
    for (const width of [320, 375, 1280]) {
      await viewport(client, width);
      const bars = await client.evaluate(renderedBars);
      assert.equal(bars.length, 4);
      const expected = [[31, 25, 44], [0, 100, 0], [0.1, 99.8, 0.1],
        [100 / 3, 100 / 3, 100 / 3]];
      bars.forEach((bar, index) => {
        assertBar(bar, expected[index]);
        assert.equal(bar.segments[0].color, 'rgb(36, 89, 181)');
        assert.equal(bar.segments[2].color, 'rgb(200, 60, 68)');
      });
      assert.ok(await client.evaluate(`document.documentElement.scrollWidth <= window.innerWidth`),
        `no horizontal page overflow at ${width}px`);
      assert.ok(await client.evaluate(`Array.from(document.querySelectorAll('.probability-label'))
        .every(label => label.getBoundingClientRect().left >= 0
          && label.getBoundingClientRect().right <= innerWidth)`),
      `visible numeric labels stay inside ${width}px viewport`);
    }
  });

  await context.test('official rounds render all ten games across days and all prediction/result states', async () => {
    const data = dashboardPayload();
    data.schemaVersion = 2;
    for (const [key, number] of [['previousRound', 1], ['nextRound', 2]]) {
      const matches = Array.from({length:10}, (_,i) => {
        const completed = number === 1 || i < 8;
        const match = syntheticMatch(`round-${number}-${String(i).padStart(2,'0')}`, {home:31,draw:25,away:44}, completed);
        match.round = number;
        match.status = completed ? 'completed' : 'scheduled';
        match.homeTeam.id = `team_${String(2*i+1).padStart(4,'0')}`;
        match.awayTeam.id = `team_${String(2*i+2).padStart(4,'0')}`;
        match.kickoffAt = `2030-10-0${number === 1 ? (i < 2 ? 2 : i < 6 ? 3 : 4) : (i < 8 ? 8 : 9)}T19:00:00+09:00`;
        if (number === 1 ? i >= 2 : i !== 0 && i !== 9) match.prediction = null;
        if (!completed) match.result = null;
        if (number === 2 && i === 1) { match.status = 'candidate'; match.result = null; }
        return match;
      });
      data[key] = {label:`${number===1?'前節':'今節'} · 第${number}節`,number,
        kind:number===1?'previous':'current',matches};
    }
    server.setPayload(data);
    await navigate(client, server.origin+'/?case=rounds', "document.querySelectorAll('.match-card').length === 20");
    assert.match(await client.evaluate("document.querySelector('#previous-title').textContent"), /第1節/);
    assert.match(await client.evaluate("document.querySelector('#next-title').textContent"), /今節.*第2節/);
    assert.deepEqual(await client.evaluate("['previous','next'].map(s=>document.querySelectorAll('#'+s+'-matches .match-card').length)"), [10,10]);
    assert.deepEqual(await client.evaluate("['previous','next'].map(s=>document.querySelectorAll('#'+s+'-matches .match-date-divider').length)"), [3,2]);
    assert.equal(await client.evaluate("document.querySelectorAll('.probability-bar').length"), 4);
    assert.match(await client.evaluate("document.querySelector('#next-matches [data-match-id=\"round-2-00\"]').textContent"), /HIT/);
    assert.match(await client.evaluate("document.querySelector('#next-matches [data-match-id=\"round-2-08\"]').textContent"), /AI予測は未生成/);
    assert.match(await client.evaluate("document.querySelector('#previous-matches .no-prediction').textContent"), /AI予測なし/);
    assert.equal(await client.evaluate("document.querySelector('#next-matches [data-status=candidate] .fixture-score')"), null);
    assert.match(await client.evaluate("document.querySelector('#next-matches [data-status=candidate]').textContent"), /結果確認中/);
    assert.equal(await client.evaluate("document.querySelectorAll('.no-prediction .probability-bar, .no-prediction .pick-value, .no-prediction .outcome-badge').length"), 0);
    for (const width of [1280,1024,375,320]) {
      await viewport(client,width);
      const columns = await client.evaluate("getComputedStyle(document.querySelector('.match-grid')).gridTemplateColumns.split(' ').length");
      assert.equal(columns,width>760?2:1);
      assert.ok(await client.evaluate("document.documentElement.scrollWidth <= innerWidth"));
    }
  });

  await context.test('independent retrospective overlay preserves four saved predictions and reload types', async () => {
    const {data,overlay} = syntheticRetrospective();
    server.setPayload(data); server.setOverlay(overlay);
    server.setUpdateStatus({ state:'ready',startedAt:null,finishedAt:null,lastSuccessAt:data.updatedAt,
      errorCode:null,pollEnabled:true,pollSeconds:60 });
    const injection = await client.send('Page.addScriptToEvaluateOnNewDocument', { source:`
      window.__nativeSetTimeout = window.setTimeout;
      window.setTimeout = function(callback, interval, ...args) {
        if (interval === 60000) { window.__poll60 = callback; return 0; }
        return window.__nativeSetTimeout(callback, interval, ...args);
      };` });
    await navigate(client, server.origin+'/?retrospective=1', "document.querySelectorAll('[data-prediction-type=retrospective_reconstruction]').length === 16");
    await client.until("typeof window.__poll60 === 'function'",'60-second timer registered');
    assert.equal(await client.evaluate("document.querySelectorAll('[data-prediction-type=saved_pre_match]').length"),4);
    assert.equal(await client.evaluate("document.querySelectorAll('.retrospective-label').length"),16);
    assert.equal(await client.evaluate("document.querySelectorAll('.probability-bar').length"),20);
    assert.equal(await client.evaluate("document.querySelectorAll('.retrospective-card .outcome-badge.hit').length"),16);
    assert.match(await client.evaluate("document.querySelector('.retrospective-card').textContent"),/当時の試合前保存予測ではありません/);
    assert.equal(await client.evaluate("document.querySelector('.recalculated-at').dateTime"),'2026-10-18T05:00:00Z');
    const before=await client.evaluate("document.querySelector('#previous-matches').innerHTML");
    // Invoke the registered 60-second callback; no artificial timestamp enters a predictor.
    await client.evaluate("window.__poll60()");
    await client.until("!document.querySelector('#reload-dashboard').disabled",'scheduled display reload');
    assert.equal(await client.evaluate("document.querySelector('#previous-matches').innerHTML"),before);
    await client.evaluate("document.querySelector('#retrospective-history').open=true");
    await client.until("document.querySelectorAll('#history-matches .match-card').length===10",'history round');
    await client.evaluate("document.querySelector('#history-round').value='10';document.querySelector('#history-round').dispatchEvent(new Event('change'))");
    assert.equal(await client.evaluate("document.querySelectorAll('#history-matches [data-prediction-type=saved_pre_match]').length"),2);
    assert.equal(await client.evaluate("document.querySelectorAll('#history-matches [data-prediction-type=retrospective_reconstruction]').length"),8);
    for(const width of [1280,375]) {
      await viewport(client,width);
      assert.ok(await client.evaluate("document.documentElement.scrollWidth <= innerWidth"));
      assert.equal(await client.evaluate("getComputedStyle(document.querySelector('.match-grid')).gridTemplateColumns.split(' ').length"),width>760?2:1);
    }
    await captureScreenshot(client,'retrospective-mobile.png');
    const broken=structuredClone(overlay);broken.entries[0].reconstruction.type='saved_pre_match';server.setOverlay(broken);
    await client.evaluate("document.querySelector('#reload-dashboard').click()");
    await client.until("document.querySelector('#update-status').dataset.state==='error'",'bad overlay keeps last valid view');
    assert.equal(await client.evaluate("document.querySelector('#previous-matches').innerHTML"),before);
    server.setOverlay(null);server.setUpdateStatus(null);
    await client.send('Page.removeScriptToEvaluateOnNewDocument',{identifier:injection.identifier});
  });

  await context.test('coherent 98-result generations follow result updates and ten saved predictions',async()=>{
    server.setPresentation(syntheticGeneration());
    const injection=await client.send('Page.addScriptToEvaluateOnNewDocument',{source:`
      const original=window.setTimeout;window.setTimeout=function(callback,ms,...args){
        if(ms===60000){window.__generationPoll=callback;return 0;}return original(callback,ms,...args);};`});
    await navigate(client,server.origin+'/?retrospective=1',"document.querySelectorAll('#previous-matches .match-card,#next-matches .match-card').length===20");
    await client.until("typeof window.__generationPoll==='function'",'60-second generation poll');
    assert.equal(await client.evaluate("document.querySelectorAll('[data-prediction-type=saved_pre_match]').length"),4);
    assert.equal(await client.evaluate("document.querySelectorAll('[data-prediction-type=retrospective_reconstruction]').length"),16);
    for(const stage of [1,2]) {
      server.setPresentation(syntheticGeneration(stage));
      await client.evaluate("window.__generationPoll()");
      await client.until("!document.querySelector('#reload-dashboard').disabled",'coherent generation reload');
      assert.equal(await client.evaluate("document.querySelectorAll('[data-prediction-type=saved_pre_match]').length"),stage===1?4:12);
      assert.equal(await client.evaluate("document.querySelectorAll('[data-prediction-type=retrospective_reconstruction]').length"),stage===1?16:8);
      assert.equal(await client.evaluate("document.querySelectorAll('.outcome-badge.hit').length"),stage===1?20:10);
      assert.equal(await client.evaluate("document.querySelectorAll('#next-matches .result-value').length"),stage===1?10:0);
    }
    const before=await client.evaluate("document.querySelector('.rounds').innerHTML");
    const invalid=syntheticGeneration(2);invalid.overlay=syntheticGeneration().overlay;
    server.setPresentation(invalid);await client.evaluate("window.__generationPoll()");
    await client.until("document.querySelector('#update-status').dataset.state==='error'",'mismatched generation held');
    assert.equal(await client.evaluate("document.querySelector('.rounds').innerHTML"),before);
    server.setPresentation(syntheticGeneration());await client.evaluate("window.__generationPoll()");
    await client.until("!document.querySelector('#reload-dashboard').disabled",'rollback rejected');
    assert.equal(await client.evaluate("document.querySelector('.rounds').innerHTML"),before);
    server.setPresentation(null);await client.send('Page.removeScriptToEvaluateOnNewDocument',{identifier:injection.identifier});
  });

  await context.test('live updates replace valid cards and preserve them on failure', async () => {
    const initial = dashboardPayload(
      [syntheticMatch('live-previous', { home: 31, draw: 25, away: 44 }, true)],
      [syntheticMatch('live-next', { home: 44, draw: 25, away: 31 })]);
    server.setPayload(initial);
    server.setUpdateStatus({ state: 'ready', startedAt: null, finishedAt: null,
      lastSuccessAt: '2026-10-01T09:00:00+09:00', errorCode: null, pollEnabled: true, pollSeconds: 10 });
    await navigate(client, server.origin + '/?case=live-updates',
      "document.querySelector('#data-status')?.dataset.state === 'operational'");
    await client.until("document.querySelector('#update-status')?.hidden === false", 'update controls');
    const changed = structuredClone(initial);
    changed.previousRound.matches[0].prediction.probabilities = { home: 62, draw: 20, away: 18 };
    server.setPayload(changed);
    await client.until("document.querySelector('.probability-label strong')?.textContent === '62%'",
      'automatic refresh without navigation', 16000);
    assert.equal(await client.evaluate("document.querySelectorAll('.match-card').length"), 2);
    const before = await client.evaluate("document.querySelector('#previous-matches').innerHTML");
    server.setPayload({ ...changed, research: { ST2: { accuracy: .99 } } });
    await client.evaluate("document.querySelector('#reload-dashboard').click()");
    await client.until("document.querySelector('#update-status')?.dataset.state === 'error'", 'retain previous cards on invalid JSON');
    assert.equal(await client.evaluate("document.querySelector('#previous-matches').innerHTML"), before);
    assert.doesNotMatch(await client.evaluate("document.querySelector('#main').textContent"), /0\.99|99%/);
    server.setPayload(changed);
    server.setUpdateStatus({ state: 'error', startedAt: null, finishedAt: null,
      lastSuccessAt: '2026-10-01T09:00:00+09:00', errorCode: 'update_failed', pollEnabled: true, pollSeconds: 10 });
    await client.evaluate("document.querySelector('#reload-dashboard').click()");
    await client.until("document.querySelector('#update-message')?.textContent.includes('更新できませんでした')", 'safe update error status');
    assert.equal(await client.evaluate("document.querySelector('#previous-matches').innerHTML"), before);
    server.setUpdateStatus(null);
  });

  await context.test('invalid API payload hard fails instead of falling back to demo', async () => {
    server.setPayload({ ...dashboardPayload(), research: { ST2: { accuracy: 0.99 } } });
    await navigate(client, `${server.origin}/?case=invalid`,
      `document.querySelector('#data-status')?.dataset.state === 'error'`);
    assert.equal(await client.evaluate(`document.querySelector('#dashboard-error').hidden`), false);
    assert.equal(await client.evaluate(`document.querySelectorAll('.match-card').length`), 0);
    assert.doesNotMatch(await client.evaluate(`document.querySelector('#data-status').textContent`), /デモ/);
    assert.doesNotMatch(await client.evaluate(`document.body.textContent`), /0\.99|99%/);
  });

  await context.test('API transport failure does not expose demo as operational output', async () => {
    server.setPayload({ error: 'Synthetic transport failure' }, 503);
    await navigate(client, `${server.origin}/?case=unavailable`,
      `document.querySelector('#data-status')?.dataset.state === 'error'`);
    assert.equal(await client.evaluate(`document.querySelector('#dashboard-error').hidden`), false);
    assert.equal(await client.evaluate(`document.querySelectorAll('.match-card').length`), 0);
  });
});

test('explicit loopback retrospective preview (read-only, opt-in)', {
  skip: !process.env.J1AI_RETROSPECTIVE_PREVIEW_URL && 'No explicit isolated preview URL supplied',
  timeout: 100000,
}, async (context) => {
  const url = new URL(process.env.J1AI_RETROSPECTIVE_PREVIEW_URL);
  assert.equal(url.protocol,'http:'); assert.equal(url.hostname,'127.0.0.1');
  assert.equal(url.pathname,'/'); assert.equal(url.search,'?retrospective=1');
  const [data,overlay] = await Promise.all(['/api/dashboard','/api/retrospective'].map(async route => {
    const response=await fetch(new URL(route,url),{signal:AbortSignal.timeout(5000)});
    assert.equal(response.status,200); return response.json();
  }));
  validateRetrospective(overlay,data);
  // The live revision advances; derive expected identities from the validated pair,
  // then compare every rendered card. Synthetic 4/16 fixtures remain fixed above.
  const matches=[...data.previousRound.matches,...data.nextRound.matches];
  const displays=matches.map(match=>selectDisplayPrediction(match,overlay));
  assert.ok(displays.every(Boolean),'This explicit preview check requires predictions on all twenty cards');
  let browser=await startBrowser();
  context.after(async()=>{
    if (browser) { await browser.client.send('Browser.close').catch(()=>{}); browser.client.close(); await browser.stop(); }
  });
  async function inspect(client) {
    await navigate(client,url.href,"document.querySelectorAll('#previous-matches .match-card,#next-matches .match-card').length===20");
    await client.until("document.querySelector('#update-status').hidden===false",'preview reload controls');
    const snapshot=await client.evaluate(`Array.from(document.querySelectorAll('#previous-matches .match-card,#next-matches .match-card')).map(card=>({
      id:card.dataset.matchId,type:card.dataset.predictionType,
      teams:Array.from(card.querySelectorAll('.team-name')).map(n=>n.textContent),
      score:card.querySelector('.fixture-score')?.textContent ?? null,
      resultLabel:card.querySelector('.result-value')?.textContent ?? null,
      bar:card.querySelector('.prediction-probability')?.getAttribute('aria-label'),
      result:card.querySelector('.outcome-badge')?.textContent ?? null,
      note:card.querySelector('.saved-note')?.textContent,title:card.querySelector('.saved-note')?.title,
      recalculatedAt:card.querySelector('.recalculated-at')?.dateTime ?? null
    }))`);
    for(const kind of ['saved_pre_match','retrospective_reconstruction'])
      assert.equal(snapshot.filter(c=>c.type===kind).length,displays.filter(d=>d.kind===kind).length);
    for(const match of matches) {
      const card=snapshot.find(c=>c.id===match.id), display=selectDisplayPrediction(match,overlay);
      assert.ok(card); assert.equal(card.type,display.kind);
      assert.deepEqual(card.teams,[match.homeTeam.name,match.awayTeam.name]);
      for(const side of ['home','draw','away']) assert.ok(card.bar.includes(`${display.value.probabilities[side]}%`));
      if(match.result) {
        assert.equal(card.score,`${match.result.homeScore} − ${match.result.awayScore}`);
        const outcome=match.result.homeScore===match.result.awayScore?'draw':match.result.homeScore>match.result.awayScore?'home':'away';
        assert.equal(card.resultLabel,outcome==='draw'?'引き分け':outcome==='home'?match.homeTeam.name:match.awayTeam.name);
      } else {assert.equal(card.score,null);assert.equal(card.resultLabel,null);}
      if(display.kind==='retrospective_reconstruction') {
        assert.equal(card.recalculatedAt,display.value.calculatedAt);
        assert.equal(card.note,'当時の試合前保存予測ではありません');
        assert.equal(card.result,display.value.hit?'✓ HIT':'× MISS');
      } else {
        assert.equal(card.note,'試合前に保存された予想を表示');
        assert.equal(card.title,`予想保存時刻: ${match.prediction.generatedAt}`);
        if(match.result) {
          const sides=['home','draw','away'], values=sides.map(side=>display.value.probabilities[side]);
          const picks=sides.filter((side,i)=>values[i]===Math.max(...values));
          const actual=match.result.homeScore===match.result.awayScore?'draw':match.result.homeScore>match.result.awayScore?'home':'away';
          assert.equal(card.result,picks.length>1?'— 同率':picks[0]===actual?'✓ HIT':'× MISS');
        }
      }
    }
    return snapshot;
  }
  const before=await inspect(browser.client);
  await browser.client.send('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});
  await captureScreenshot(browser.client,'retrospective-real-desktop.png');
  const seen=[];
  await browser.client.evaluate("document.querySelector('#retrospective-history').open=true");
  for(const section of overlay.historyRounds) {
    await browser.client.evaluate(`document.querySelector('#history-round').value=${JSON.stringify(String(section.number))};document.querySelector('#history-round').dispatchEvent(new Event('change'))`);
    await browser.client.until("document.querySelectorAll('#history-matches .match-card').length===10",'history cards');
    const selected=await browser.client.evaluate("Array.from(document.querySelectorAll('#history-matches .match-card')).map(c=>({id:c.dataset.matchId,status:c.dataset.status,type:c.dataset.predictionType}))");
    assert.deepEqual(selected.map(c=>c.id),section.matches.map(m=>m.id));
    seen.push(...selected.filter(c=>c.status==='completed').map(c=>c.id));
  }
  const expectedCompleted=overlay.historyRounds.flatMap(section=>section.matches)
    .filter(match=>match.status==='completed').map(match=>match.id);
  assert.deepEqual([...new Set(seen)].sort(),[...new Set(expectedCompleted)].sort());
  await browser.client.evaluate("document.querySelector('#retrospective-history').open=false");
  await browser.client.send('Emulation.setDeviceMetricsOverride',{width:375,height:812,deviceScaleFactor:1,mobile:true});
  assert.ok(await browser.client.evaluate("document.documentElement.scrollWidth<=innerWidth"));
  await captureScreenshot(browser.client,'retrospective-real-mobile.png');
  await browser.client.send('Emulation.clearDeviceMetricsOverride');
  await browser.client.evaluate(`window.__previewReads=0;const savedFetch=window.fetch;window.fetch=function(input,...args){
    if(['/api/dashboard','/api/presentation'].includes(String(input)))window.__previewReads++;return savedFetch.call(this,input,...args);};`);
  await delay(61000);
  assert.ok(await browser.client.evaluate("window.__previewReads>=1"),'actual 60-second poll read the display API');
  assert.equal(await browser.client.evaluate("document.querySelector('#update-status').dataset.state"),'ready');
  // Reopening the browser uses another owned temporary profile and the same retained server.
  await browser.client.send('Browser.close').catch(()=>{});browser.client.close();await browser.stop();browser=null;
  browser=await startBrowser();
  assert.deepEqual(await inspect(browser.client),before);
});
