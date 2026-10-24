const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const frontend = process.env.FRONTEND_URL;
const api = process.env.API_URL;
const output = process.env.ARGO_BROWSER_OUTPUT || "/tmp/argo-browser-results";
fs.mkdirSync(output, { recursive: true });
const report = { target: frontend, checks: [], warnings: [], exceptions: [], apiErrors: [] };
let browser, page;
async function check(name, fn) {
  try { await fn(); report.checks.push({name, status:"pass"}); console.log("PASS " + name); return true; }
  catch (e) { report.checks.push({name, status:"fail", error:e.message}); console.log("FAIL " + name + ": " + e.message); return false; }
}
function observe(p) {
  p.on("pageerror", e => report.exceptions.push(e.message));
  p.on("response", r => {
    if (r.url().startsWith(api + "/api/") && r.status() >= 400)
      report.apiErrors.push({url:r.url(), status:r.status()});
  });
}
async function shot(p, name) {
  const bytes = await p.screenshot({path:path.join(output,name+".jpg"),type:"jpeg",quality:45,animations:"disabled"});
  console.log("ARGO_SCREENSHOT " + name + " " + bytes.toString("base64"));
}
async function overflow(p, label) {
  const sizes=await p.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
  if(sizes.document>sizes.viewport+2) report.warnings.push(label+" horizontal overflow: "+JSON.stringify(sizes));
}
async function main() {
  browser = await chromium.launch({headless:true});
  const ctx = await browser.newContext({viewport:{width:1440,height:1000},locale:"en-US",acceptDownloads:true,reducedMotion:"reduce"});
  page = await ctx.newPage(); page.setDefaultTimeout(45000); observe(page);
  const expected=JSON.parse(fs.readFileSync("data/recent-activity.json","utf8"));
  const summaryPromise=page.waitForResponse(r=>r.url()===api+"/api/v1/intelligence/summary"&&r.status()===200,{timeout:120000}).catch(()=>null);
  await page.goto(frontend,{waitUntil:"domcontentloaded",timeout:120000});
  const recent=page.locator('section[aria-labelledby="recent-activity-title"]');
  await check("Desktop overview renders the approved snapshot and weekly changes",async()=>{
    await recent.getByText(expected.event_count.toLocaleString("en-US"),{exact:true}).waitFor();
    await recent.getByText(expected.active_contributors.toLocaleString("en-US"),{exact:true}).waitFor();
    await recent.getByRole("heading",{name:"What changed this week?",exact:true}).waitFor();
    const text=await recent.innerText();
    for(const change of Object.values(expected.weekly.changes)) assert(text.includes(change.percent+"%"));
    assert(text.includes(expected.weekly.current.start)&&text.includes(expected.weekly.previous.start));
    await overflow(page,"Desktop");
    await page.evaluate(()=>scrollTo(0,0)); await shot(page,"desktop-overview");
  });
  await check("Daily counts expand to all 28 covered days",async()=>{
    const toggle=recent.getByText("Exact daily counts",{exact:true}); await toggle.click();
    const details=toggle.locator("xpath=ancestor::details[1]");
    assert.equal(await details.locator("li").count(),expected.daily.length);
    await details.locator("li").first().waitFor(); await toggle.click();
  });
  for(const [label,key] of [["Repository drivers","repository_drivers"],["Event-category drivers","category_drivers"]]) {
    await check(label+" opens and reconciles",async()=>{
      const toggle=recent.getByText(label,{exact:true}); await toggle.click();
      const details=toggle.locator("xpath=ancestor::details[1]"); await details.getByRole("table").waitFor();
      const rows=await details.locator("tbody tr").all(); assert.equal(rows.length,expected.weekly[key].length);
      let total=0;
      for(const row of rows) { const cells=await row.locator("td").allTextContents(); total+=Number(cells.at(-1).replaceAll(",","")); }
      assert.equal(total,expected.weekly.changes.events.delta); await toggle.click();
    });
  }
  await check("Quality evidence and freshness are visible",async()=>{
    const heading=recent.getByRole("heading",{name:"Data quality & freshness",exact:true}); await heading.waitFor();
    assert.match(await recent.innerText(),/28\/28 covered days/);
    for(const item of expected.quality.checks) await recent.getByText(item.name+": pass (0 failures)",{exact:false}).waitFor();
    await heading.evaluate(el=>el.scrollIntoView({block:"center"})); await shot(page,"desktop-quality");
  });
  await check("Historical contributor summary renders after its separate response",async()=>{
    const response=await summaryPromise; assert(response,"Summary response did not complete");
    const summary=(await response.json()).summary; assert(summary); await page.getByText(summary,{exact:true}).waitFor();
  });
  await check("Investigation link opens the published case study",async()=>{
    const link=recent.getByRole("link",{name:"Read the activity concentration investigation",exact:true});
    assert.match(await link.getAttribute("href"),/\/blob\/main\/docs\/investigations\/activity-concentration\.md$/);
    const popupPromise=page.waitForEvent("popup"); await link.click(); const popup=await popupPromise;
    try {
      await popup.waitForLoadState("domcontentloaded",{timeout:90000});
      assert.match(popup.url(),/github\.com\/yash-rai-93\/argo-data-platform/);
      await popup.getByRole("heading",{name:"Activity concentration and weekly participation",exact:true}).waitFor();
    } finally { await popup.close(); }
  });
  await check("ML Engine navigation and registry render",async()=>{
    await page.getByRole("button",{name:"ML Engine",exact:true}).click();
    await page.getByRole("heading",{name:"Model Registry & Metric Drift",exact:true}).waitFor();
    await page.getByRole("button",{name:"Export Report (PDF)",exact:true}).waitFor();
  });
  await check("Settings navigation renders governance results",async()=>{
    const responsePromise=page.waitForResponse(r=>r.url()===api+"/api/v1/metrics/governance/health"&&r.status()===200);
    await page.getByRole("button",{name:"Settings",exact:true}).click(); const data=await(await responsePromise).json();
    assert.equal(data.status,"pass"); await page.getByRole("heading",{name:"Data Governance",exact:true}).waitFor();
    await page.getByText(data.tests[0].name,{exact:true}).waitFor();
  });
  const retained=await check("Retention queue supports selection and keyboard dismissal",async()=>{
    await page.getByRole("button",{name:/^Retention/}).click();
    const row=page.getByRole("button",{name:/^Open profile for /}).first(); await row.waitFor(); await row.click();
    await page.getByRole("button",{name:"Clear selection",exact:true}).waitFor(); await page.keyboard.press("Escape");
    assert.equal(await page.getByRole("button",{name:"Clear selection",exact:true}).isVisible(),false); await row.click();
  });
  if(retained) {
    await check("Threshold slider updates the confusion matrix",async()=>{
      const slider=page.getByRole("slider");
      await page.waitForFunction(()=>{const el=document.querySelector('input[type="range"]');return el&&!el.disabled;});
      const before=await slider.inputValue();
      const tp=page.getByText("True Positives",{exact:true}).locator("..").locator("p").first();
      const old=await tp.innerText(); await slider.focus(); await slider.press("End"); assert.notEqual(await slider.inputValue(),before);
      await page.waitForFunction(value=>{const p=Array.from(document.querySelectorAll("p")).find(el=>el.textContent==="True Positives");return p&&p.parentElement.querySelector("p").textContent!==value;},old);
    });
    await check("Scenario prediction renders survival and SHAP output",async()=>{
      const simulator=page.getByRole("heading",{name:"Contributor Churn Simulator",exact:true}).locator("xpath=ancestor::section[1]");
      const responsePromise=page.waitForResponse(r=>r.url()===api+"/api/v1/predict/churn"&&r.request().method()==="POST");
      await simulator.locator('button[type="button"]').first().click(); const response=await responsePromise; assert.equal(response.status(),200);
      const data=await response.json(); assert.equal(data.shap_attribution.length,16); assert(data.survival_curve.length);
      const heading=simulator.getByRole("heading",{name:"Projected Survival",exact:true}); await heading.waitFor();
      await simulator.getByText("Top 3 Deciding Factors",{exact:true}).waitFor();
      const chart=simulator.locator("svg.recharts-surface").first(); await chart.waitFor(); const box=await chart.boundingBox();
      assert(box&&box.width>50&&box.height>50);
      await heading.evaluate(el=>el.scrollIntoView({block:"center"})); await shot(page,"desktop-prediction");
    });
    await check("Edited prediction form submits successfully",async()=>{
      const input=page.locator("#days_since_last_event"); await input.fill(String(Number(await input.inputValue())+1));
      const responsePromise=page.waitForResponse(r=>r.url()===api+"/api/v1/predict/churn"&&r.request().method()==="POST");
      await page.getByRole("button",{name:"Predict Churn",exact:true}).click(); assert.equal((await responsePromise).status(),200);
      await page.getByRole("heading",{name:"Projected Survival",exact:true}).waitFor();
    });
    await check("Export failure shows retryable feedback",async()=>{
      await page.evaluate(()=>{
        window.__argoOriginalToDataURL=HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL=function(){throw new Error("Simulated export capture failure");};
      });
      try {
        await page.getByRole("button",{name:"Export Report (PDF)",exact:true}).click();
        const alert=page.getByRole("alert"); await alert.waitFor();
        assert.match(await alert.innerText(),/report could not be exported/i);
        assert(await page.getByRole("button",{name:"Export Report (PDF)",exact:true}).isEnabled());
      } finally {
        await page.evaluate(()=>{HTMLCanvasElement.prototype.toDataURL=window.__argoOriginalToDataURL;delete window.__argoOriginalToDataURL;});
      }
    });
    await check("PDF export downloads a valid document",async()=>{
      const downloadPromise=page.waitForEvent("download",{timeout:120000});
      await page.getByRole("button",{name:"Export Report (PDF)",exact:true}).click();
      const download=await downloadPromise; const target=path.join(output,"retention-report.pdf"); await download.saveAs(target);
      const bytes=fs.readFileSync(target); assert.equal(bytes.subarray(0,5).toString(),"%PDF-");
      assert(bytes.length>1000 && bytes.length<5*1024*1024, "PDF must be below 5 MiB");
      report.pdfBytes=bytes.length;
      const info=execFileSync("pdfinfo",[target],{encoding:"utf8"});
      report.pdfPages=Number(info.match(/^Pages:\s+(\d+)/m)[1]);
      assert(report.pdfPages>=2, "Long workspace must paginate at readable width");
      execFileSync("pdftoppm",["-f","1","-l","2","-r","110","-jpeg","-jpegopt","quality=60",target,path.join(output,"pdf-preview")]);
      for(const filename of fs.readdirSync(output).filter(name=>name.startsWith("pdf-preview")&&name.endsWith(".jpg"))) {
        console.log("ARGO_SCREENSHOT "+filename.replace(".jpg","")+" "+fs.readFileSync(path.join(output,filename)).toString("base64"));
      }
    });
  }
  const mobileCtx=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true,locale:"en-US",reducedMotion:"reduce"});
  const mobile=await mobileCtx.newPage(); mobile.setDefaultTimeout(45000); observe(mobile);
  await check("Mobile overview and recent-activity details are usable",async()=>{
    await mobile.goto(frontend,{waitUntil:"domcontentloaded",timeout:120000});
    const panel=mobile.locator('section[aria-labelledby="recent-activity-title"]');
    await panel.getByText(expected.event_count.toLocaleString("en-US"),{exact:true}).waitFor(); await overflow(mobile,"Mobile");
    await mobile.evaluate(()=>scrollTo(0,0)); await shot(mobile,"mobile-overview");
    const toggle=panel.getByText("Repository drivers",{exact:true}); await toggle.tap();
    await toggle.locator("xpath=ancestor::details[1]").getByRole("table").waitFor();
    await overflow(mobile,"Mobile expanded repository drivers"); await toggle.tap();
    await panel.getByRole("heading",{name:"Data quality & freshness",exact:true}).evaluate(el=>el.scrollIntoView({block:"start"}));
    await shot(mobile,"mobile-quality");
    if(!(await mobile.getByRole("button",{name:"ML Engine",exact:true}).isVisible()))
      report.warnings.push("Mobile tab navigation is hidden at 390px; previously deferred.");
  });
  assert.equal(report.exceptions.length,0,"Uncaught browser exceptions"); assert.equal(report.apiErrors.length,0,"Failed application API calls");
  await mobileCtx.close(); await ctx.close();
}
main().catch(e=>{report.fatal=e.stack;console.log("FATAL "+e.message);}).finally(async()=>{
  if(browser) await browser.close();
  fs.writeFileSync(path.join(output,"report.json"),JSON.stringify(report,null,2)); console.log("ARGO_REPORT "+JSON.stringify(report));
  if(report.fatal||report.checks.some(c=>c.status==="fail")) process.exitCode=1;
});
