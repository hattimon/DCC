# DCC Web 0.3.3

## Polski

- DCC Web wznawia dostęp pod tą samą domeną zrok, gdy poprzedni udział pozostawił zajętą rezerwację. Usuwa tylko zweryfikowany osierocony udział należący do zapisanego środowiska DCC.
- Zgoda na wznowienie pozostaje zapisana po błędzie dostawcy. Updater 1.1.8 może przenieść ważną zgodę także wtedy, gdy tunel jest już zatrzymany podczas aktualizacji Web.

## English

- DCC Web recovers the same zrok address when a stale share still occupies its reservation. Cleanup is limited to a verified stale share owned by the saved DCC environment.
- Recovery consent survives a provider failure. Container Updater 1.1.8 can transfer existing consent when the tunnel is already stopped during a Web update.

[DCC-Web-0.3.3-source.zip](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.3.3/DCC-Web-0.3.3-source.zip)
