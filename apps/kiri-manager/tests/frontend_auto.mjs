import assert from "node:assert/strict";
import test from "node:test";
import {automaticConnection, wizard, connections, profileForm} from "../frontend/assets/connections.js";
import {detail} from "../frontend/assets/inventory.js";
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

test("SSH form never renders stored credential values and supports pinned host key", () => {
  const profile = {name: "Remote", host: "linux", runtime: "docker", transport: "ssh",
    ssh_host: "example.invalid", ssh_port: 22, ssh_username: "operator", ssh_cli: "docker",
    ssh_known_hosts: "public-key", has_credentials: true, credentials: {password: "TEST-SECRET"}};
  const html = profileForm(profile, []);
  assert.match(html, /name="ssh_known_hosts"/);
  assert.match(html, /name="ssh_password" type="password"/);
  assert.doesNotMatch(html, /TEST-SECRET/);
});

test("container controls depend on state and management mode", () => {
  const item = {name: "demo-container", state: "exited", id: "a".repeat(64)};
  assert.match(detail("containers", item, true), /data-key="remove"/);
  assert.match(detail("containers", item, true), /data-key="start"/);
  assert.doesNotMatch(detail("containers", {...item, state: "running"}, true), /data-key="remove"/);
  assert.doesNotMatch(detail("containers", item, false), /data-action="container-action"/);
  assert.doesNotMatch(detail("containers", {...item, name: "dcc-kiri-manager"}, true), /data-action="container-action"/);
});
