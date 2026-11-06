# DCC Web 0.2.9

## English

- Edit an MCP grant without replacing its active token. Host terminal access has a separate device selection, administrator reauthentication and live permission checks.
- Run bounded SSH/Balena host commands or interactive terminal sessions through explicitly granted MCP tools. Sessions close on disconnect or authorization changes; existing grants gain no new tools automatically.
- Clearer project ZIP setup for Windows, Linux and macOS. Exports contain no tokens, describe actual device/tool scope and require MCP-only device administration.
- Preserve managed Caddy HTTPS and the opt-in zrok update handoff supported by Container Updater 1.1.4. For compatible DCC Web images, the updater pauses and resumes the tunnel automatically; the administrator does not need to disable the public domain manually. MCP supports local stdio and optional HTTPS/OAuth, which remains off until explicitly enabled in DCC Web.

## Polski

- Edycja dostępu MCP zachowuje aktywny token. Terminal ma osobny wybór urządzeń, ponowne uwierzytelnienie administratora i bieżącą kontrolę uprawnień.
- Polecenia hosta SSH/Balena oraz interaktywny terminal przez jawnie przyznane narzędzia MCP. Rozłączenie lub zmiana uprawnień zamyka sesje; istniejące granty nie otrzymują nowych narzędzi automatycznie.
- Czytelniejsza konfiguracja ZIP dla Windows, Linux i macOS. Eksport nie zawiera tokena, opisuje rzeczywisty zakres urządzeń i wymaga zarządzania nimi wyłącznie przez MCP.
- Zachowany HTTPS Caddy i opcjonalne wznowienie tunelu zrok przez Container Updater 1.1.4. Przy zgodnych obrazach Updater sam wstrzymuje i wznawia tunel; administrator nie musi ręcznie wyłączać domeny publicznej. MCP obsługuje lokalne stdio oraz opcjonalne HTTPS/OAuth, które pozostaje wyłączone do czasu jawnego włączenia w DCC Web.
