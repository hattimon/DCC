import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { mkdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = fileURLToPath(new URL("../", import.meta.url));
const output = resolve(root, "browser-artifacts");
const sizes = [[1920, 1080], [1440, 900], [1280, 800], [768, 1024], [390, 844], [360, 800]];
const capture = process.argv.includes("--capture");
const onlyPanel = process.argv.includes("--panel");
const onlySite = process.argv.includes("--site");
const timeout = 10000;
const tested = [];
await mkdir(join(output, "source"), {recursive: true});

async function fixture(run) {
  const server = spawn(process.env.KIRI_PYTHON || (process.platform === "win32" ? "python.exe" : "python3"),
    ["-B", join("tests", "browser_fixture.py")],
    {cwd: root, stdio: ["ignore", "pipe", "inherit"], windowsHide: true, env: {...process.env, PYTHONPATH: root}});
  const port = new Promise((resolvePort, reject) => {
    const timer = setTimeout(() => reject(Error("Fixture did not start")), 15000);
    createInterface({input: server.stdout}).on("line", (line) => {
      if (!line.startsWith("PORT=")) return;
      clearTimeout(timer);
      resolvePort(Number(line.slice(5)));
    });
    server.once("error", (error) => { clearTimeout(timer); reject(error); });
    server.once("exit", (code) => { clearTimeout(timer); reject(Error("Fixture exited " + code)); });
  });
  try { await run("http://127.0.0.1:" + await port); }
  finally { server.kill(); }
}

async function match(locator, expected) {
  await locator.waitFor({state: "visible", timeout});
  if (expected !== undefined) await locator.filter({hasText: expected}).waitFor({state: "visible", timeout});
}

async function nav(page, view) {
  if (await page.locator('header [data-action="menu"]').isVisible()) {
    await page.locator('header [data-action="menu"]').click();
  }
  await page.locator('#navigation a[href="#' + view + '"]').click();
  await page.waitForFunction((value) => location.hash === "#" + value, view);
}

async function login(page, base) {
  await page.goto(base);
  await page.getByLabel("Username").fill("admin");
  await page.locator('[name="password"]').fill("TEST-only-kiri-passphrase");
  await page.locator("#login-form button").click();
  await match(page.locator("#main h1"));
}

async function firstLogin(page, base) {
  assert.equal((await page.request.post(base + "/__fixture/reset?blank=1")).status(), 204);
  await page.goto(base);
  await match(page.getByRole("heading", {name: "First sign-in"}));
  await page.getByRole("button", {name: "Polski"}).click();
  await match(page.getByRole("heading", {name: "Pierwsze logowanie"}));
  assert.equal(await page.getByLabel("Nazwa użytkownika").inputValue(), "admin");
  const terminal = page.locator(".auth-help");
  assert.equal(await terminal.locator("pre").isVisible(), false);
  await terminal.locator("summary").click();
  await match(terminal.locator("pre"), "python -m backend.admin");
  await overflow(page, "terminal setup");
  await terminal.locator("summary").click();
  await page.getByLabel("Hasło", {exact: true}).fill("admin");
  await page.getByRole("button", {name: "Zaloguj się"}).click();
  await match(page.getByRole("heading", {name: "Zabezpiecz konto"}));
  assert.equal(await page.locator("#workspace").isVisible(), false);
  await page.reload();
  await match(page.getByRole("heading", {name: "Zabezpiecz konto"}));
  const password = "TEST-first-login-passphrase";
  await page.getByLabel("Nazwa użytkownika").fill("Operator");
  await page.getByLabel("Nowe hasło").fill(password);
  await page.getByLabel("Powtórz hasło").fill(password);
  await overflow(page, "first password");
  await page.getByRole("button", {name: "Zapisz i przejdź dalej"}).click();
  await match(page.locator("#main h1"));
  await page.locator('header [data-action="menu"]').click();
  await page.getByRole("button", {name: "Wyloguj"}).click();
  await match(page.getByRole("heading", {name: "Zaloguj się"}));
  assert.equal(await page.getByText("Zaloguj się jako admin z hasłem admin.").isVisible(), false);
  assert.equal(await terminal.locator("pre").isVisible(), false);
  await terminal.locator("summary").click();
  await match(terminal.locator("pre"), "--reset");
  await overflow(page, "terminal reset");
  await terminal.locator("summary").click();
  await page.getByLabel("Nazwa użytkownika").fill("Operator");
  await page.getByLabel("Hasło", {exact: true}).fill(password);
  await page.getByRole("button", {name: "Zaloguj się"}).click();
  await match(page.locator("#main h1"));
}

async function wizard(page, saveShots = false) {
  await match(page.getByRole("heading", {name: "Welcome to DCC Kiri Manager"}));
  await page.getByRole("button", {name: "Next"}).click();
  await page.getByRole("button", {name: "Back"}).click();
  await match(page.getByRole("heading", {name: "Welcome to DCC Kiri Manager"}));
  await page.getByRole("button", {name: "Next"}).click();
  await page.getByRole("button", {name: "Next"}).click();
  await match(page.getByText("bash setup-kiri-linux.sh --plan --grant-panel-access", {exact: true}));
  await match(page.getByText("bash setup-kiri-linux.sh --apply --grant-panel-access", {exact: true}));
  await page.getByLabel("Profile name").fill("Workshop · Local Kiri");
  await page.getByLabel("Socket alias").selectOption("test-engine");
  await page.getByText("How does socket access work?").click();
  await match(page.getByText("The mounted socket itself", {exact: false}));
  await page.getByText("How does socket access work?").click();
  if (saveShots) await shot(page, "wizard");
  await page.getByRole("button", {name: "Test connection"}).click();
  await match(page.getByText("Kiri identified", {exact: true}));
  await page.getByRole("button", {name: "Open overview"}).click();
  await match(page.getByRole("heading", {name: "Container inventory"}));
}

async function shot(page, name) {
  await page.screenshot({path: join(output, "source", name + ".png"), animations: "disabled"});
}

async function overflow(page, label) {
  const result = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  assert.ok(result.scroll <= result.width + 1, label + " overflows " + JSON.stringify(result));
}

async function theme(page, name, button) {
  if (await page.locator("html").getAttribute("data-theme") !== name) await page.locator(button).click();
  await page.waitForFunction((expected) => document.documentElement.dataset.theme === expected, name);
}

function validatePage(page, errors) {
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (entry) => {
    if (entry.type() !== "error") return;
    const message = entry.text();
    if (!message.includes("Failed to load resource")) errors.push(message);
  });
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname;
    // The fixture deliberately sends an offline-socket error in one recovery test.
    if (response.status() >= 400 && (!path.startsWith("/api/") || response.status() !== 503)) {
      errors.push(response.status() + " " + path);
    }
  });
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED") errors.push(request.failure()?.errorText + " " + request.url());
  });
}

async function scenario(browser, scope, width, height, test) {
  const context = await browser.newContext({viewport: {width, height}, reducedMotion: "reduce", hasTouch: width < 700, acceptDownloads: true});
  const page = await context.newPage();
  const errors = [];
  validatePage(page, errors);
  await context.tracing.start({screenshots: true, snapshots: true});
  try {
    await test(page);
    assert.deepEqual(errors, [], scope + " console or resource errors");
    await context.tracing.stop();
    tested.push({scope, width, height, result: "PASS"});
    console.log(scope + " " + width + "x" + height + " PASS");
  } catch (error) {
    await page.screenshot({path: join(output, scope + "-" + width + "-failure.png"), animations: "disabled"});
    await context.tracing.stop({path: join(output, scope + "-" + width + "-failure.zip")});
    if (errors.length) console.error(errors.join("\n"));
    throw error;
  } finally {
    await context.close();
  }
}

async function panelSize(page, base, width, height) {
  const save = capture && width === 1440;
  assert.equal((await page.request.post(base + "/__fixture/reset")).status(), 204);
  await login(page, base);
  await wizard(page, save);
  await match(page.locator("#demo"), "DEMO");
  await match(page.locator(".engine .badge"), "Engine online");
  await page.locator(".chart svg").first().waitFor();
  await overflow(page, "overview dark");
  if (save) {
    for (let i = 0; i < 4; i += 1) {
      await page.waitForTimeout(700);
      await page.getByRole("button", {name: "Refresh", exact: true}).click();
      await match(page.locator("#toast"), "Updated");
      await page.waitForFunction((count) => document.querySelector(".chart .trace").getAttribute("points").split(" ").length >= count, i + 2);
    }
    await page.waitForFunction(() => !document.querySelector("#toast").textContent);
    await shot(page, "dashboard-dark");
  }
  await theme(page, "light", '#quick [data-action="theme"]');
  await overflow(page, "overview light");
  if (save) await shot(page, "dashboard-light");
  await page.locator('#quick [data-key="pl"]').click();
  await match(page.locator("#main h1"), "Przegląd");
  await theme(page, "dark", '#quick [data-action="theme"]');
  if (save) {
    await shot(page, "dashboard-dark-pl");
    await theme(page, "light", '#quick [data-action="theme"]');
    await shot(page, "dashboard-light-pl");
    await theme(page, "dark", '#quick [data-action="theme"]');
  }
  await page.reload();
  await match(page.locator("#main h1"), "Przegląd");
  assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
  await page.locator('#quick [data-key="en"]').click();
  await match(page.locator("#main h1"), "Overview");

  const expected = {
    containers: "northstar-web", images: "nginx:1.27-alpine", volumes: "northstar_pg",
    networks: "northstar_default", compose: "northstar", diagnostics: "Diagnostic results",
  };
  for (const [view, phrase] of Object.entries(expected)) {
    await nav(page, view);
    await match(page.locator("#content"), phrase);
    await overflow(page, view);
    if (save) await shot(page, view);
    if (view === "containers") {
      await page.locator("#search").fill("northstar-web");
      await match(page.locator("#row-count"), "1 results");
      await page.getByRole("button", {name: "northstar-web"}).click();
      await match(page.getByRole("dialog"), "Health");
      await page.getByRole("button", {name: "Read logs"}).click();
      await match(page.locator("#log-output"), "[REDACTED]");
      assert.ok(!(await page.locator("#log-output").innerText()).includes("fixture-never-echo"));
      await page.keyboard.press("Escape");
      assert.equal(await page.getByRole("dialog").isVisible(), false);
      await page.locator("#search").fill("");
      if (capture && width === 390) {
        await page.locator("#search").blur();
        await shot(page, "mobile");
      }
    }
  }
  await nav(page, "monitoring");
  await match(page.getByRole("heading", {name: "Engine storage"}));
  await page.getByRole("button", {name: "Read image storage"}).click();
  await match(page.locator("#content"), "428.8 MiB");
  if (width === 1440) {
    await nav(page, "connections");
    await page.getByRole("button", {name: "New profile"}).click();
    await page.getByRole("button", {name: "Save"}).click();
    assert.equal(await page.locator("#profile-form [name='name']:invalid").count(), 1);
    await page.getByLabel("Profile name").fill("Offline fixture");
    await page.getByLabel("Socket alias").selectOption("offline-test");
    await page.getByRole("button", {name: "Save"}).click();
    await match(page.getByRole("heading", {name: "Offline fixture"}));
    await page.getByRole("button", {name: "Set active", exact: true}).click();
    await nav(page, "overview");
    await match(page.locator("#content"), "The Kiri socket is unavailable");
    await nav(page, "connections");
    await page.getByRole("button", {name: "Set active", exact: true}).click();
    await nav(page, "overview");
    await match(page.getByRole("heading", {name: "Container inventory"}));
    await nav(page, "settings");
    await page.getByLabel("Automatic refresh").selectOption("0");
    await page.getByRole("button", {name: "Save"}).click();
    await match(page.locator("#toast"), "Changes saved");
    await page.locator("#sign-out").click();
    await match(page.locator("#login-form"));
  }
  await page.screenshot({path: join(output, "panel-" + width + "x" + height + ".png"), animations: "disabled"});
}

async function siteSize(page, base, width, height) {
  await page.goto(base + "/project/");
  await match(page.locator("h1"), "DCC Kiri Manager");
  assert.equal(await page.locator("html").getAttribute("lang"), "en");
  await page.waitForFunction(() => document.querySelector("#hero-image").naturalWidth > 0);
  await overflow(page, "site dark");
  const signInHelp = page.locator(".install-help");
  assert.equal(await signInHelp.locator("code").isVisible(), false);
  await signInHelp.locator("summary").click();
  await match(signInHelp.locator("code"), "admin / admin");
  await overflow(page, "site sign-in help");
  await signInHelp.locator("summary").click();
  if (width < 700) {
    await page.locator("#menu").click();
    await match(page.locator("#navigation"));
    await page.keyboard.press("Escape");
    await page.locator("#menu").click();
    await page.locator("#navigation a[href='#screenshots']").click();
    assert.equal(await page.locator("#menu").getAttribute("aria-expanded"), "false");
  }
  const gallery = page.locator("[data-shot]");
  assert.equal(await gallery.count(), 10);
  await gallery.first().click();
  await match(page.getByRole("dialog"), "Overview (dark)");
  await page.keyboard.press("ArrowRight");
  await match(page.locator("#number"), "2 / 10");
  if (width < 700) {
    await page.locator("#large").dispatchEvent("pointerdown", {pointerType: "touch", clientX: 160});
    await page.locator("#large").dispatchEvent("pointerup", {pointerType: "touch", clientX: 45});
    await match(page.locator("#number"), "3 / 10");
  }
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.activeElement === document.querySelector("[data-shot]"));
  await theme(page, "light", "#theme");
  await overflow(page, "site light");
  await Promise.all([page.waitForURL("**/project/pl/"), page.locator("[data-language='pl']").click()]);
  await match(page.locator("h1"), "DCC Kiri Manager");
  assert.equal(await page.locator("html").getAttribute("lang"), "pl");
  assert.ok((await page.locator("meta[name='description']").getAttribute("content")).includes("Niezależny"));
  assert.equal(await page.locator("html").getAttribute("data-theme"), "light");
  await match(signInHelp.locator("summary"), "Pierwsze logowanie i reset hasła");
  assert.equal(await signInHelp.locator("code").isVisible(), false);
  await page.goto(base + "/project/");
  await page.waitForURL("**/project/pl/");
  await theme(page, "dark", "#theme");
  await page.waitForFunction(() => document.querySelector("#hero-image").naturalWidth > 0);
  await overflow(page, "site pl");
  await page.screenshot({path: join(output, "site-" + width + "x" + height + ".png"), animations: "disabled"});
}

let browser;
try {
  browser = await chromium.launch({headless: true});
  if (!onlySite) await fixture((base) => scenario(browser, "first-login", 390, 844, (page) => firstLogin(page, base)));
  await fixture(async (base) => {
    if (!onlySite) for (const [w, h] of sizes) await scenario(browser, "panel", w, h, (page) => panelSize(page, base, w, h));
    if (!onlyPanel) for (const [w, h] of sizes) await scenario(browser, "site", w, h, (page) => siteSize(page, base, w, h));
  });
} finally {
  await browser?.close();
  await writeFile(join(output, onlySite ? "site-results.json" : onlyPanel ? "panel-results.json" : "results.json"), JSON.stringify(tested, null, 2));
}
