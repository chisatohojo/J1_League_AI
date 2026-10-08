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

  async until(expression, description) {
    const deadline = Date.now() + 10000;
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
  const server = http.createServer(async (request, response) => {
    try {
      const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
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
