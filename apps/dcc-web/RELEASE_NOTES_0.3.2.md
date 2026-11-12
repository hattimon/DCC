# DCC Web 0.3.2

EN: Adds a scoped Docker network-namespace relay for local container panels without joining DCC Web to application networks or creating per-panel zrok tunnels. Improves SSH HTTP, chunked and SSE forwarding for Paramiko channels without `read1()`, and tightens redirect and stream cleanup. MCP container reads now expose selected safe metadata instead of arbitrary commands, arguments, environment variables, labels, bind mount sources or health logs. Preserves validated `<html>` / `<body>` attributes and language when rendering service panels, fixing the Container Updater 1.1.4 `Invalid language tag` failure.

PL: Dodaje izolowany przekaźnik w przestrzeni sieciowej wybranego lokalnego kontenera, bez podłączania DCC Web do sieci aplikacji ani tworzenia osobnych tuneli zrok. Poprawia przekazywanie HTTP, chunked i SSE przez kanały SSH Paramiko bez `read1()` oraz zamykanie połączeń i przekierowań. MCP zwraca wyłącznie wybrane metadane kontenerów, pomijając polecenia, argumenty, zmienne środowiskowe, etykiety, ścieżki źródłowe montowań i logi healthchecków. Zachowuje bezpieczne atrybuty `<html>` / `<body>` i język dokumentu, usuwając błąd `Invalid language tag` w Container Updater 1.1.4.

The public gateway uses the existing DCC Web address. Apps requiring their own browser origin still need a separately configured HTTPS host. / Brama używa istniejącego adresu DCC Web. Aplikacje wymagające własnego originu w przeglądarce potrzebują osobnego, skonfigurowanego hosta HTTPS.

Source package: [DCC-Web-0.3.2-source.zip](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.3.2/DCC-Web-0.3.2-source.zip).
