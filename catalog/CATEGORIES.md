# DCC application category taxonomy / Taksonomia kategorii aplikacji DCC

The catalog should classify an app by what it does. `docker` and `balena` belong in
`engines`, not in the category name.

Katalog powinien klasyfikować aplikację według funkcji. `docker` i `balena` należą
do pola `engines`, a nie do nazwy kategorii.

| PL | EN | Examples / Przykłady |
|---|---|---|
| DCC | DCC | DCC Container Updater |
| AI / Agenci | AI / Agents | Agent Zero |
| AI / Runtime | AI / Runtime | Ollama |
| AI / UI | AI / UI | Open WebUI |
| AI / Wyszukiwanie | AI / Search | SearXNG, Vane |
| AI / Bazy wektorowe | AI / Vector Databases | Qdrant |
| AI / Monitoring | AI / Monitoring | Langfuse |
| AI / Developer | AI / Developer | Tabby, OpenHands |
| Automatyzacja / Low-code | Automation / Low-code | NocoDB |
| Administracja / Kontenery | Administration / Containers | Portainer |
| Administracja / Logi | Administration / Logs | Dozzle |
| Monitoring / Uptime | Monitoring / Uptime | Uptime Kuma, Gatus |
| Monitoring / Metryki | Monitoring / Metrics | Grafana, Prometheus, Beszel |
| Sieć / DNS | Network / DNS | Pi-hole, AdGuard Home |
| Sieć / Diagnostyka | Network / Diagnostics | OpenSpeedTest |
| Powiadomienia / Push | Notifications / Push | ntfy, Gotify |
| Bezpieczeństwo / Hasła | Security / Passwords | Vaultwarden |
| Bezpieczeństwo / Narzędzia | Security / Tools | CyberChef |
| Produktywność / Notatki | Productivity / Notes | Memos |
| Produktywność / Zadania | Productivity / Tasks | Vikunja |
| Produktywność / Zakładki | Productivity / Bookmarks | Linkding |
| Narzędzia / Pliki | Tools / Files | SFTPGo |
| Narzędzia / Dokumenty | Tools / Documents | Stirling PDF |
| Narzędzia / Developer | Tools / Developer | IT-Tools |
| Backup | Backup | Duplicati, Restic REST Server |
| Analityka | Analytics | Umami |
| Finanse / Budżet | Finance / Budgeting | Actual Budget |
| Bazy danych | Databases | PostgreSQL, MariaDB |
| Messaging | Messaging | RabbitMQ, NATS |
| Cache | Cache | Redis, Memcached |
| WWW / Proxy | Web / Proxy | Nginx, Caddy |
| Aplikacje WWW | Web Apps | WordPress, Nextcloud |
| Smart Home / IoT | Smart Home / IoT | Home Assistant, Node-RED, Mosquitto |
| Media | Media | Jellyfin, Plex |
| DevOps | DevOps | Gitea |
| Baza / System | Base / System | Alpine, Debian, Ubuntu |
| Runtime / Dev | Runtime / Dev | Node.js, Python, Go |

## Rule for Balena / Zasada dla Balena

An application may appear on a Balena host when its OCI/Docker image supports the
host architecture and its entry contains `"balena"` in `engines`.

Aplikacja może pojawić się na hoście Balena, jeżeli jej obraz OCI/Docker obsługuje
architekturę hosta, a wpis zawiera `"balena"` w `engines`.

## Official DCC extensions / Oficjalne rozszerzenia DCC

Every official Docker Control Center extension should be assigned to `DCC`
plus the functional categories that match its purpose. Do not create catalog
entries for planned extensions until they exist.

Każde oficjalne rozszerzenie Docker Control Center powinno należeć do kategorii
`DCC` oraz odpowiednich kategorii funkcjonalnych.

The legacy `category` / `category_en` fields remain the primary category.
Optional `categories` / `categories_en` arrays add further memberships without
creating a duplicate app; for example: `"category": "Aktualizacje 🔄",
"category_en": "Updates 🔄", "categories": ["DCC"], "categories_en": ["DCC"]`.
