/** Offline Chrome rendering plus geometry / guided-reader QA.
 * node render_panorama.cjs <playwright-module> <outside-repo-qa-dir>
 * Writes only generated panorama PNG and QA files; never uses a personal profile.
 */
const fs=require('node:fs'),path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.argv[2]||'playwright');
const out=path.resolve(__dirname,'..'),qa=path.resolve(process.argv[3]||path.join(out,'qa-local'));
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'panorama-manifest.json'),'utf8'));
const stem='14_V1全景技术流程图';
(async()=>{
 fs.mkdirSync(qa,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const report={layout:null,viewer:null,errors:[],network:[]};
 try{
  const page=await browser.newPage({viewport:{width:3200,height:1400},deviceScaleFactor:1});
  page.on('pageerror',e=>report.errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))report.network.push(r.url());});
  await page.setContent('<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;width:3200px">'+fs.readFileSync(path.join(out,stem+'.svg'),'utf8')+'</body></html>');
  await page.evaluate(()=>document.fonts.ready);
  report.layout=await page.evaluate(()=>{
   const boxes=[...document.querySelectorAll('[data-box]')].map(n=>({n,b:n.dataset.box.split(',').map(Number)}));
   const overflow=[],overlaps=[],collisions=[],labelCollisions=[];
   for(const {n,b:[x,y,w,h]} of boxes){for(const t of n.querySelectorAll('text')){const b=t.getBBox();if(b.x<x+6||b.x+b.width>x+w-6||b.y<y+2||b.y+b.height>y+h-2)overflow.push({id:n.id,text:t.textContent,box:{x:b.x,y:b.y,w:b.width,h:b.height}});}}
   for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){const[x,y,w,h]=boxes[i].b,[a,b,c,d]=boxes[j].b;if(Math.min(x+w,a+c)>Math.max(x,a)&&Math.min(y+h,b+d)>Math.max(y,b))overlaps.push([boxes[i].n.id,boxes[j].n.id]);}
   for(const e of document.querySelectorAll('.edge')){
    const hits=new Set(),len=e.getTotalLength();
    for(let t=6;t<len-6;t+=9){const p=e.getPointAtLength(t);for(const{n,b:[x,y,w,h]}of boxes)if(p.x>x+5&&p.x<x+w-5&&p.y>y+5&&p.y<y+h-5)hits.add(n.id);}
    for(const id of hits)collisions.push({edge:e.id,from:e.dataset.from,to:e.dataset.to,kind:e.dataset.kind,node:id});
   }
   for(const label of document.querySelectorAll('.edge-label')){const b=label.getBBox();for(const{n,b:[x,y,w,h]}of boxes)if(Math.min(x+w,b.x+b.width)>Math.max(x,b.x)&&Math.min(y+h,b.y+b.height)>Math.max(y,b.y))labelCollisions.push({text:label.textContent,node:n.id});}
   return {nodes:boxes.length,edges:document.querySelectorAll('.edge').length,overflow,overlaps,collisions,labelCollisions};
  });
  fs.writeFileSync(path.join(qa,'geometry.json'),JSON.stringify(report.layout,null,2));
  // Capture even failed layouts to support targeted, visual fixes.
  await page.screenshot({path:path.join(out,stem+'.png'),fullPage:true,timeout:60000});
  for(const[name,x,y,w,h]of[['entry',80,140,3000,1020],['commerce',120,1170,850,1860],['kf',970,1170,1260,1850],['human',2280,1170,800,2010],['commands',130,3230,2930,830],['publication',1020,4080,2050,700],['closure',120,4440,2950,1750],['resources',130,6210,2930,360]]){
   await page.screenshot({path:path.join(qa,name+'.png'),fullPage:true,clip:{x,y,width:w,height:h}});
  }
  if(report.layout.overflow.length||report.layout.overlaps.length||report.layout.collisions.length||report.layout.labelCollisions.length)throw new Error(JSON.stringify(report.layout));
  await page.setViewportSize({width:1600,height:1050});
  await page.goto(pathToFileURL(path.join(out,'V1全景技术流程图_逐步讲解.html')).href);
  const duplicateIds=await page.evaluate(()=>{const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);return ids.filter((id,i)=>ids.indexOf(id)!==i);});
  if(duplicateIds.length)throw new Error('Duplicate HTML/SVG IDs: '+duplicateIds.join(','));
  for(let i=0;i<data.phases.length;i++){
   await page.locator('#phases').selectOption(String(i));
   if((await page.locator('#counter').textContent())!==`${i+1} / ${data.phases.length}`)throw new Error('Counter '+i);
   const active=await page.locator('.node.active').count();if(active!==data.phases[i].ids.length)throw new Error('Active nodes '+i);
   const p=await page.locator('#viewport').boundingBox();
   const shown=await page.locator('.node.active').evaluateAll((els,v)=>els.some(el=>{const r=el.getBoundingClientRect();return r.right>v.x&&r.left<v.x+v.width&&r.bottom>v.y&&r.top<v.y+v.height;}),p);
   if(!shown)throw new Error('Viewport misses phase '+i);
   await page.screenshot({path:path.join(qa,`step-${String(i+1).padStart(2,'0')}.png`)});
  }
  await page.locator('#prev').click();await page.locator('#next').click();
  await page.locator('#all').click();if(await page.locator('#panorama').evaluate(e=>e.classList.contains('guided')))throw new Error('All view did not clear guidance');
  await page.locator('#actual').click();if((await page.locator('#zoom').textContent())!=='100%')throw new Error('100% zoom');
  await page.locator('#minus').click();await page.locator('#plus').click();
  await page.locator('#resources').uncheck();if(await page.locator('path.resource').first().isVisible())throw new Error('Resource toggle');await page.locator('#resources').check();
  await page.locator('#phases').selectOption('0');await page.locator('#user').click();if((await page.locator('#detail-title').textContent())!==data.nodes.find(n=>n.id==='user').title)throw new Error('Inspector');
  await page.locator('#phases').selectOption('4');await page.screenshot({path:path.join(qa,'viewer-kf.png')});
  await page.locator('#all').click();await page.screenshot({path:path.join(qa,'viewer-overview.png')});
  report.viewer={steps:data.phases.length,navigation:'passed',viewport:'passed',zoom:'passed',resourceToggle:'passed',nodeInspector:'passed'};
  if(report.errors.length||report.network.length)throw new Error('Script errors or external network');
  console.log(JSON.stringify(report,null,2));
 }finally{fs.writeFileSync(path.join(qa,'verification.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
