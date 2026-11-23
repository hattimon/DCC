# DCC Web 0.3.6

## Polski

- Poprawiono argumenty poleceń Docker wykonywanych przez SSH, w tym formatowanie JSON i odczyt polityk restartu kontenerów.
- Dodano wybór zdalnej powłoki SSH: Linux/macOS/Balena (sh) lub Windows (PowerShell). Wybrana powłoka jest używana także w połączeniach Docker API przez SSH podczas aktualizacji kontenerów.
- Zachowano weryfikację kluczy hosta SSH, szyfrowane poświadczenia, istniejące profile oraz oddzielne testy SSH i Docker.

## English

- Fixed Docker CLI arguments over SSH, including JSON formatting and container restart policy inspection.
- Added an SSH remote-shell selector for Linux/macOS/Balena (sh) and Windows (PowerShell). Docker API operations over SSH now honor the selected shell too.
- Preserved strict SSH host-key verification, encrypted credentials, existing profiles, and separate SSH and Docker connection checks.

[DCC-Web-0.3.6-source.zip](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.3.6/DCC-Web-0.3.6-source.zip)
