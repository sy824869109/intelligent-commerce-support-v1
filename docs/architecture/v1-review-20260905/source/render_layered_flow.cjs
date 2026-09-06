/** Reproducible offline chart QA. Only writes generated PNGs and a separate QA folder.
 * Usage: node render_layered_flow.cjs <playwright-module> <qa-directory>
 * Uses a fresh headless Chrome context, never a personal browser profile.
 */
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.argv[2] || 'playwright');
const root = path.resolve(__dirname, '..');
const qa = path.resolve(process.argv[3] || path.join(root, 'qa-local'));
const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, 'layered-flow-manifest.json'), 'utf8'));

(async () => {
  fs.mkdirSync(qa, {recursive: true});
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  const result = {diagrams: [], viewer: {}, errors: [], requests: []};
  try {
    const page = await browser.newPage({viewport: {width: 1200, height: 1000}, deviceScaleFactor: 1});
    page.on('pageerror', err => result.errors.push(err.message));
    page.on('request', req => {if (/^https?:/.test(req.url())) result.requests.push(req.url());});
    for (const f of manifest) {
      await page.setContent('<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;width:1200px">' + fs.readFileSync(path.join(root, f.stem + '.svg'), 'utf8') + '</body></html>');
      await page.evaluate(() => document.fonts.ready);
      const layout = await page.evaluate(() => {
        const failures = [], collisions = [], overlaps = [];
        const boxes = [...document.querySelectorAll('[data-box]')].map(n => ({node: n, rect: n.dataset.box.split(',').map(Number)}));
        for (const {node, rect: [x,y,w,h]} of boxes) {
          for (const t of node.querySelectorAll('text')) {
            const b = t.getBBox();
            if (b.x < x + 6 || b.x + b.width > x + w - 6 || b.y < y + 3 || b.y + b.height > y + h - 3) failures.push({node: node.id, text: t.textContent, rect: {x:b.x,y:b.y,w:b.width,h:b.height}});
          }
        }
        for (let i=0;i<boxes.length;i++) for (let j=i+1;j<boxes.length;j++) {
          const [x,y,w,h]=boxes[i].rect, [a,b,c,d]=boxes[j].rect;
          if (Math.min(x+w,a+c)>Math.max(x,a) && Math.min(y+h,b+d)>Math.max(y,b)) overlaps.push([i,j]);
        }
        for (const edge of document.querySelectorAll('path.flow-edge')) {
          const len = edge.getTotalLength();
          for (let t=5;t<len-5;t+=8) {
            const p=edge.getPointAtLength(t);
            for (const {node,rect:[x,y,w,h]} of boxes) if(p.x>x+5 && p.x<x+w-5 && p.y>y+5 && p.y<y+h-5) collisions.push(node.id);
          }
        }
        return {mainNodes: document.querySelectorAll('.node').length, allBoxes: boxes.length, failures, collisions, overlaps};
      });
      result.diagrams.push({key:f.key,...layout});
      if (layout.failures.length || layout.collisions.length || layout.overlaps.length || layout.mainNodes !== f.nodes.length) throw new Error(JSON.stringify(result.diagrams.at(-1)));
      await page.screenshot({path:path.join(root, f.stem+'.png'), fullPage:true, timeout:60000});
      // Two readable samples per chart; the complete generated PNG is also retained.
      await page.screenshot({path:path.join(qa,f.key+'-top.png'),clip:{x:0,y:0,width:1200,height:Math.min(1300,f.height)}});
      await page.screenshot({path:path.join(qa,f.key+'-end.png'),fullPage:true,clip:{x:0,y:Math.max(0,f.height-1300),width:1200,height:1300}});
    }
    await page.setViewportSize({width:1440,height:1100});
    await page.goto(pathToFileURL(path.join(root,'V1分层流程与示例.html')).href);
    for (const f of manifest) {
      await page.locator('nav [data-open="'+f.key+'"]').click();
      const panel = page.locator('[data-panel="'+f.key+'"]');
      if (!await panel.isVisible() || await page.locator('[data-panel]:visible').count() !== 1) throw new Error('Panel visibility: '+f.key);
      const marker = await panel.locator('.flow-edge').first().evaluate(el => getComputedStyle(el).markerEnd);
      if (!marker.includes('#arrow-'+f.key)) throw new Error('Cross-panel marker CSS leaked: '+f.key+' '+marker);
      await panel.locator('select').selectOption(f.nodes.at(-1));
      await panel.locator('.jump').click();
      const box = await panel.locator('[id="'+f.nodes.at(-1)+'"]').boundingBox();
      // Near the document end the browser legitimately clamps scrolling; the
      // requested node must be visible, not necessarily aligned to y=0.
      if (!box || box.y < -2 || box.y + box.height > 1102) throw new Error('Node jump: '+f.key+' '+JSON.stringify(box));
      await panel.locator('.actual').click();
      if (Math.abs((await panel.locator('svg').boundingBox()).width - 1200) > 1) throw new Error('Actual size failed');
      await panel.locator('.fit').click();
      // Exercise every SVG drilldown link, not only sidebar navigation.
      const targets = await panel.locator('[data-open]').evaluateAll(els=>[...new Set(els.map(e=>e.dataset.open))]);
      for (const target of targets) {
        await page.locator('nav [data-open="'+f.key+'"]').click();
        await panel.locator('[data-open="'+target+'"]').first().click();
        if (!await page.locator('[data-panel="'+target+'"]').isVisible()) throw new Error('Drilldown '+f.key+' -> '+target);
      }
      for (const ext of ['svg','png']) if(!fs.existsSync(path.join(root,f.stem+'.'+ext))) throw new Error('Missing download');
    }
    await page.locator('nav [data-open="overview"]').click();
    await page.locator('[data-panel="overview"] select').selectOption('A01');
    await page.screenshot({path:path.join(qa,'viewer-desktop.png')});
    await page.setViewportSize({width:390,height:844});
    await page.reload();
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
    if(overflow) throw new Error('Mobile page overflow (chart itself should scroll)');
    await page.screenshot({path:path.join(qa,'viewer-mobile.png'),fullPage:false});
    result.viewer={navigation:manifest.length, allDrilldownLinks:'passed', nodeJump:'passed', zoom:'passed', mobile:'passed', downloads:manifest.length*2};
    if(result.errors.length || result.requests.length) throw new Error('Browser errors / unexpected network: '+JSON.stringify(result));
    console.log(JSON.stringify(result,null,2));
  } finally {
    fs.writeFileSync(path.join(qa,'verification.json'),JSON.stringify(result,null,2)+'\n');
    await browser.close();
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
