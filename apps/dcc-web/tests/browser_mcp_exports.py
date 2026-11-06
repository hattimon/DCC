"""End-to-end MCP export checks against the isolated review_server.py fixture.

Run review_server.py on localhost before invoking this script. It uses only
synthetic profiles and the fixture administrator, never a real Docker host.
"""

import argparse
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright


CLIENT_FILES = {
    "OpenAI Codex": ("AGENTS.md", ".codex/config.toml"),
    "Claude Code": ("CLAUDE.md", ".mcp.json"),
    "Claude Desktop": ("DCC_INSTRUCTIONS.md", "claude_desktop_config.json"),
    "Cursor": (".cursor/rules/dcc.mdc", ".cursor/mcp.json"),
    "Windsurf": (".windsurf/rules/dcc.md", "mcp_config.json"),
    "VS Code / GitHub Copilot": (".github/copilot-instructions.md", ".vscode/mcp.json"),
    "Generic MCP": ("DCC_INSTRUCTIONS.md", "mcp.json"),
}


def downloaded_bytes(page, selector):
    with page.expect_download() as event:
        page.locator(selector).click()
    download = event.value
    return download.suggested_filename, Path(download.path()).read_bytes()


def create_grant(page, client, number):
    name = f"Browser MCP QA {number}-{uuid4().hex[:8]}"
    page.locator("#grant-create").click()
    form = page.locator("#modal")
    form.locator('[name="name"]').fill(name)
    form.locator('[name="client"]').select_option(label=client)
    form.locator('[name="profiles"][value="local"]').check()
    form.locator('button[type="submit"]').click()
    expect(form).to_contain_text("Token", timeout=10000)
    token_text = form.locator("pre.inspect").inner_text()
    assert len(token_text) >= 40
    form.locator("[data-close]").first.click()
    expect(page.locator("#content tr").filter(has_text=name)).to_be_visible(timeout=10000)
    return name, token_text


def check_export(page, name, client, token, screenshot_dir):
    row = page.locator("#content tr").filter(has_text=name)
    grant_id = row.locator("[data-export]").get_attribute("data-export")
    row.locator("[data-export]").click()
    modal = page.locator("#modal")
    expect(modal.locator('[data-download-zip]')).to_have_attribute('href', __import__('re').compile('platform='))
    modal.locator('details').first.locator('summary').click()
    expect(modal.locator("[data-agent-preview]")).to_be_visible()
    instruction_path, config_path = CLIENT_FILES[client]
    assert modal.locator("[data-instruction-path]").inner_text() == instruction_path
    standard = modal.locator("[data-agent-preview]").inner_text()
    assert "DCC MCP" in standard and "list_containers" in standard
    assert "authorized indirect access" not in standard
    assert token not in modal.inner_text()
    assert modal.locator("[data-copy-instructions]").count() == 1
    if client == "Claude Desktop":
        modal.locator("[data-copy-instructions]").click()
        expect(page.locator("#toast")).to_have_text("Skopiowano do schowka")
        clipboard = page.evaluate("navigator.clipboard.readText()").replace("\r\n", "\n")
        assert clipboard == standard

    filename, instruction = downloaded_bytes(page, "[data-download-agent]")
    assert filename == Path(instruction_path).name, (
        client, filename, instruction_path,
        page.request.get(f"{page.url.split('/#', 1)[0]}/api/mcp/instructions/{grant_id}").json().get("filename"),
    )
    assert instruction.decode("utf-8") == standard
    config_name, config_content = downloaded_bytes(page, "[data-download-config]")
    # Chromium removes the initial dot from a downloaded root-level filename.
    # Verify that the server still advertises the correct Claude Code filename,
    # which the project ZIP must preserve verbatim.
    origin = page.url.split("/#", 1)[0]
    response = page.request.get(f"{origin}/api/mcp/config/{grant_id}?download=1")
    assert response.ok
    assert f"filename={Path(config_path).name}" in response.headers["content-disposition"]
    expected_download_name = config_path.lstrip(".") if config_path.startswith(".") and "/" not in config_path else Path(config_path).name
    assert config_name == expected_download_name, (client, config_name, config_path)
    assert token.encode() not in config_content

    if client == "OpenAI Codex":
        modal.locator("[data-variant]").select_option("chatgpt-web")
        expect(modal.locator("[data-agent-preview]")).to_contain_text("DCC MCP connection required")
        web_name, web_content = downloaded_bytes(page, "[data-download-agent]")
        assert web_name == "AGENTS.chatgpt-web.md"
        assert "Do not bypass" in web_content.decode("utf-8")
        assert modal.locator("[data-instruction-path]").inner_text() == "AGENTS.md"
        instruction = web_content

    zip_name, zip_bytes = downloaded_bytes(page, "[data-download-zip]")
    assert zip_name.endswith("-chatgpt-web.zip") if client == "OpenAI Codex" else zip_name.endswith(".zip")
    with ZipFile(BytesIO(zip_bytes)) as archive:
        assert set(archive.namelist()) == {instruction_path, config_path, "README.md"}
        assert archive.read(instruction_path) == instruction
        assert archive.read(config_path) == config_content
        readme = archive.read("README.md").decode("utf-8")
        assert instruction_path in readme and config_path in readme
        assert "English" in readme and "Polski" in readme
        assert "DCC_MCP_TOKEN" in readme
        assert token not in readme
    if screenshot_dir and client == "OpenAI Codex":
        modal.evaluate("dialog => dialog.scrollTop = 0")
        page.screenshot(path=str(screenshot_dir / "mcp-export-pl.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        mobile_zip = modal.locator("[data-download-zip]")
        mobile_zip.scroll_into_view_if_needed()
        expect(mobile_zip).to_be_in_viewport()
        page.screenshot(path=str(screenshot_dir / "mcp-export-mobile.png"))
        page.set_viewport_size({"width": 1440, "height": 960})
    modal.locator("[data-close]").first.click()
    return grant_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8790")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)

    failures = []
    completed = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 960},
                                      permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        page.on("pageerror", lambda error: failures.append(str(error)))
        page.on("console", lambda message: failures.append(message.text) if message.type == "error" else None)
        page.goto(args.url + "/login?lang=PL")
        page.get_by_label("Nazwa użytkownika", exact=True).fill("review-admin")
        page.get_by_label("Hasło", exact=True).fill("Review-only-password-4488")
        page.get_by_role("button", name="Otwórz DCC Web").click()
        polish = page.locator('#language-switch [data-language="PL"]')
        polish.click()
        expect(polish).to_have_attribute("aria-pressed", "true")
        page.goto(args.url + "/#mcp")
        expect(page.locator("#grant-create")).to_be_visible(timeout=15000)
        expect(page).to_have_title("DCC Web — Docker workspace")

        first_id = None
        for number, client in enumerate(CLIENT_FILES, 1):
            name, token = create_grant(page, client, number)
            identifier = check_export(page, name, client, token, args.out)
            if first_id is None:
                first_id = identifier
            completed += 1
            print(f"PASS {client}: grant, preview, downloads, ZIP")

        english = page.locator('#language-switch [data-language="EN"]')
        english.click()
        expect(english).to_have_attribute("aria-pressed", "true")
        row = page.locator(f'[data-export="{first_id}"]')
        row.click()
        modal = page.locator("#modal")
        expect(modal.get_by_role("heading", name="AI / MCP export")).to_be_visible()
        expect(modal.locator("[data-download-zip]")).to_have_text("Download project package (ZIP)")
        expect(modal.locator("[data-platform]")).to_be_visible()
        expect(modal).to_contain_text('The ZIP never contains the token')
        modal.locator("[data-close]").first.click()
        completed += 1
        print("PASS English UI translations")

        # Edit the original read grant, preserve its token and choose terminal
        # devices independently. This never executes against a real host.
        page.locator(f'[data-grant-edit="{first_id}"]').click()
        modal.locator('[name=mode][value=write]').check()
        modal.locator('[name=profiles][value=mcp-ssh-qa]').check()
        modal.locator('[name=allow_host_terminal]').check()
        modal.locator('[name=terminal_profiles][value=mcp-ssh-qa]').check()
        assert modal.locator('[name=tools][value=container_remove]').count()==0
        assert modal.locator('[name=allow_destructive]').count()==1
        modal.locator('[name=current_password]').fill('Review-only-password-4488')
        modal.locator('[type=submit]').click()
        expect(page.locator('#toast')).to_contain_text('token is unchanged')
        metadata=page.request.get(args.url+'/api/mcp/grants').json()['grants']
        edited=next(grant for grant in metadata if grant['id']==first_id)
        assert edited['allow_host_terminal'] and edited['terminal_profiles']==['mcp-ssh-qa']
        assert 'host_exec' in edited['tools'] and 'local' in edited['profiles']
        page.locator(f'[data-grant-edit="{first_id}"]').click()
        expect(modal.locator('[name=allow_host_terminal]')).to_be_checked()
        expect(modal.locator('[name=terminal_profiles][value=mcp-ssh-qa]')).to_be_checked()
        if args.out: page.screenshot(path=str(args.out/'mcp-grant-edit-en.png'))
        modal.locator('[data-close]').first.click()
        completed+=1
        print('PASS grant edit and separate terminal device scope')

        page.locator(f'[data-grant-action="revoke"][data-id="{first_id}"]').click()
        modal.get_by_role("checkbox").check()
        modal.get_by_role("button", name="Revoke access").click()
        expect(page.locator(f'[data-export="{first_id}"]')).to_have_count(0)
        for endpoint in ("config", "instructions", "bundle"):
            assert page.request.get(f"{args.url}/api/mcp/{endpoint}/{first_id}").status == 404
        completed += 1
        print("PASS revoked grant blocks every export")
        browser.close()

    assert not failures, f"Browser console errors: {failures}"
    print(f"PASS {completed} browser scenarios, zero console errors")


if __name__ == "__main__":
    main()
