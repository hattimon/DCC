# DCC Web 0.3.0

## English

- Keep retrying remote HTTPS after Internet, DNS or zrok outages instead of permanently stopping the tunnel after eight failed checks.
- Add optional automatic recovery after restarting DCC Web or the computer. Preserve this consent through an authorized Updater handoff and retry temporary launch failures. Disable access cancels recovery.
- Record safe connection-loss and recovery events in Web logs and the audit trail. Preserve MFA, isolated networking and HTTPS verification before reopening public access.

## Polski

- Ponawianie publicznego HTTPS po przerwie w Internecie, DNS lub zrok zamiast trwałego zatrzymania tunelu po ośmiu nieudanych próbach.
- Opcjonalne wznowienie po restarcie DCC Web lub komputera. Zgoda jest zachowywana przy zatwierdzonej aktualizacji przez Updater; chwilowy błąd uruchomienia jest ponawiany. Wyłączenie dostępu anuluje wznowienie.
- Bezpieczne zdarzenia utraty i odzyskania połączenia w logach Web oraz audycie. Zachowane MFA, izolacja sieci i weryfikacja HTTPS przed otwarciem dostępu publicznego.

Download / Pobierz: [DCC-Web-0.3.0-source.zip](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.3.0/DCC-Web-0.3.0-source.zip) · [SHA-256](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.3.0/DCC-Web-0.3.0-source.zip.sha256)

Docker: `ghcr.io/hattimon/dcc-web:0.3.0`. Compatible with / Zgodny z DCC Container Updater 1.1.4.
