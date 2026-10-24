import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

function fixture({ dnt, gpc, blockedStorage, failedImport } = {}) {
  const events = [], inits = [], storage = new Map();
  let imports = 0, resolve;
  const sdk = {
    init: (...args) => inits.push(args),
    track: (...args) => events.push(args),
    opt_in_tracking: options => assert.equal(typeof options.track, "function"),
    opt_out_tracking() {}, reset() {},
  };
  const testModule = { exports: {} };
  const source = fs.readFileSync("src/lib/analytics.ts", "utf8")
    .replace('await import("mixpanel-browser")', 'await mockImport()');
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const context = {
    exports: testModule.exports, module: testModule,
    process: { env: { NEXT_PUBLIC_MIXPANEL_TOKEN: "test-token" } },
    window: {}, navigator: { doNotTrack: dnt, globalPrivacyControl: gpc },
    localStorage: {
      getItem: key => { if (blockedStorage) throw Error("blocked"); return storage.get(key); },
      setItem: (key, value) => { if (blockedStorage) throw Error("blocked"); storage.set(key, value); },
    },
    mockImport: () => {
      imports++;
      if (failedImport) return Promise.reject(Error("offline"));
      return new Promise(r => { resolve = () => r({ default: sdk }); });
    },
  };
  vm.runInNewContext(code, context);
  return { api: testModule.exports, events, inits, imports: () => imports, release: () => resolve?.() };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test("no SDK or events before consent or after decline", async () => {
  const f = fixture();
  await f.api.trackDashboard(); await f.api.trackPrediction("manual");
  f.api.setConsent("denied"); await settle();
  assert.equal(f.imports(), 0); assert.equal(f.events.length, 0);
});
test("accept tracks a single visit and successful prediction metadata only", async () => {
  const f = fixture();
  f.api.setConsent("granted"); f.release(); await settle();
  await f.api.trackDashboard(); await f.api.trackDashboard();
  await f.api.trackPrediction("manual"); await f.api.trackPrediction("preset");
  assert.deepEqual(JSON.parse(JSON.stringify(f.events)), [
    ["dashboard_viewed", { platform: "web" }],
    ["prediction_completed", { platform: "web", prediction_source: "manual" }],
    ["prediction_completed", { platform: "web", prediction_source: "preset" }],
  ]);
  assert.equal(f.inits.length, 1);
  const config = f.inits[0][1];
  assert.equal(config.autocapture, false);
  assert.equal(config.track_pageview, false);
  assert.equal(config.record_sessions_percent, 0);
  assert.equal(config.ip, false);
  f.api.setConsent("denied");
  await f.api.trackPrediction("manual");
  assert.equal(f.events.length, 3);
});
test("withdrawal while SDK loads prevents initialization", async () => {
  const f = fixture(); f.api.setConsent("granted");
  f.api.setConsent("denied"); f.release(); await settle();
  assert.equal(f.inits.length, 0); assert.equal(f.events.length, 0);
});
test("DNT, GPC and blocked storage prevent SDK loading", async () => {
  for (const options of [{ dnt: "1" }, { gpc: true }, { blockedStorage: true }]) {
    const f = fixture(options); f.api.setConsent("granted");
    await f.api.trackPrediction("manual");
    assert.equal(f.imports(), 0);
  }
});
test("SDK import failure does not break the application", async () => {
  const f = fixture({ failedImport: true }); f.api.setConsent("granted");
  await settle(); await f.api.trackPrediction("manual");
  assert.equal(f.events.length, 0);
});
