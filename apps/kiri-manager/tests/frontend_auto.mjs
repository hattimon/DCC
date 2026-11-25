import assert from "node:assert/strict";
import test from "node:test";
import {automaticConnection, wizard, connections} from "../frontend/assets/connections.js";
import {setLanguage} from "../frontend/assets/i18n.js";

globalThis.document = {documentElement: {lang: "en"}};
const setup = (discovery) => ({step: 0, advanced: false, discovery,
  draft: {name: "", host: "linux", runtime: "docker", endpoint: ""}, result: null});

test("ready: Connect is visible and untrusted engine text is escaped", () => {
  setLanguage("en");
  const html = automaticConnection({status: "ready", engine: {version: '<img src=x>'}}, true);
  assert.match(html, /data-action="auto-connect"/);
  assert.match(html, /&lt;img src=x&gt;/);
  assert.doesNotMatch(html, /<img src=x>/);
  assert.doesNotMatch(html, /Socket alias/);
});

test("unconfigured and blocked: actionable help, no dead alias form", () => {
  for (const found of [{status: "unconfigured"}, {status: "blocked", reason: "permission_denied"}]) {
    const html = wizard(setup(found), []);
    assert.match(html, /data-action="auto-check"/);
    assert.match(html, /docs\.runkiri\.com\/install/);
    assert.doesNotMatch(html, /name="endpoint"/);
    assert.doesNotMatch(html, /data-action="wizard-test"/);
    assert.match(html, /data-action="wizard-advanced"/);
  }
});

test("PL and connections: connect label localized, skip only in onboarding", () => {
  setLanguage("pl");
  const found = {status: "ready", engine: {version: "0.2.2"}};
  const html = automaticConnection(found);
  assert.match(html, /Połącz z wykrytym Kiri/);
  assert.doesNotMatch(html, /data-action="auto-skip"/);
  assert.match(wizard(setup(found), []), /data-action="auto-skip"/);
  const listing = connections([], null, new Map(), [], "disconnected", found);
  assert.match(listing, /Połącz z wykrytym Kiri/);
  assert.doesNotMatch(listing, /data-action="auto-skip"/);
  setLanguage("en");
});
