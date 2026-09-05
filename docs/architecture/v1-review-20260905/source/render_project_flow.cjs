/** Render the code-native SVG with installed Chrome, then check text and navigation.
 * Usage: node render_project_flow.cjs <playwright-module> <QA-output-directory>
 * QA output is kept outside the deliverable directory; no personal profile is used.
 */
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.argv[2] || 'playwright');
const out = path.resolve(__dirname, '..');
const qa = path.resolve(process.argv[3] || path.join(out, 'qa-local'));
const stem = '05_平台端到端详细流程';

(async () => {
  fs.mkdirSync(qa, {recursive: true});
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 2000, height: 1300}, deviceScaleFactor: 1});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // A regular HTML surface avoids Chromium's standalone-SVG full-page capture
    // behavior; the diagram itself is inserted verbatim, with no image conversion.
    await page.setContent('<!doctype html><html><head><meta charset="utf-8"><style>svg{display:block}</style></head>' +
      '<body style="margin:0;width:2000px">' + fs.readFileSync(path.join(out, `${stem}.svg`), 'utf8') + '</body></html>');
    await page.evaluate(() => document.fonts.ready);
    const layout = await page.evaluate(() => {
      const failures = [];
      document.querySelectorAll('[data-box]').forEach(node => {
        const [x, y, w, h] = node.dataset.box.split(',').map(Number);
        node.querySelectorAll('text').forEach(text => {
          const box = text.getBBox();
          if (box.x < x + 7 || box.x + box.width > x + w - 7 || box.y < y + 3 || box.y + box.height > y + h - 3) {
            failures.push({node: node.id, text: text.textContent, box: {x: box.x, y: box.y, width: box.width, height: box.height}});
          }
        });
      });
      // Flow arrows may meet a node boundary, but must never pass through its body.
      const collisions = [];
      document.querySelectorAll('path.flow-edge').forEach((edge, index) => {
        const length = edge.getTotalLength();
        document.querySelectorAll('[data-box]').forEach(node => {
          const [x, y, w, h] = node.dataset.box.split(',').map(Number);
          for (let offset = 5; offset < length - 5; offset += 8) {
            const p = edge.getPointAtLength(offset);
            if (p.x > x + 6 && p.x < x + w - 6 && p.y > y + 6 && p.y < y + h - 6) {
              collisions.push({edge: index, node: node.id}); break;
            }
          }
        });
      });
      return {nodeCount: document.querySelectorAll('[data-box]').length, failures, collisions};
    });
    fs.writeFileSync(path.join(qa, 'layout.json'), JSON.stringify(layout, null, 2));
    if (layout.failures.length || layout.collisions.length) throw new Error(JSON.stringify(layout));
    await page.screenshot({path: path.join(out, `${stem}.png`), fullPage: true, timeout: 60000});
    // Independent section renders keep Chinese text readable during visual QA.
    for (const [name, y, height] of [['entry', 0, 1190], ['branches', 1190, 1520], ['response', 2710, 595], ['closure', 3305, 1280], ['resources', 4590, 670]]) {
      await page.screenshot({path: path.join(qa, `${name}.png`), fullPage: true, clip: {x: 0, y, width: 2000, height}});
    }
    await page.setViewportSize({width: 1440, height: 1000});
    await page.goto(pathToFileURL(path.join(out, 'V1平台端到端详细流程.html')).href);
    const initial = await page.locator('#zoom').textContent();
    await page.locator('#actual').click();
    if ((await page.locator('#zoom').textContent()) !== '100%') throw new Error('Actual-size control failed');
    await page.locator('#plus').click();
    if ((await page.locator('#zoom').textContent()) !== '115%') throw new Error('Zoom-in control failed');
    await page.locator('#minus').click();
    await page.locator('#fit').click();
    for (const id of ['entry', 'execution', 'kf', 'response', 'closure', 'resources']) {
      await page.locator(`[data-jump="${id}"]`).click();
      const visible = await page.evaluate(targetId => {
        const r = document.getElementById(targetId).getBoundingClientRect();
        const toolbar = document.querySelector('header').getBoundingClientRect();
        return r.top >= toolbar.bottom - 3 && r.top < innerHeight;
      }, id);
      if (!visible) throw new Error(`Section ${id} hidden under toolbar`);
    }
    await page.locator('[data-jump="entry"]').click();
    await page.screenshot({path: path.join(qa, 'viewer.png')});
    if (errors.length) throw new Error(errors.join('\n'));
    console.log(JSON.stringify({layout, viewer: '6 section links and zoom controls passed', initialZoom: initial, png: '2000 x 5260', errors}, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
