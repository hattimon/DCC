# DCC Web 0.2.7

## English

- Uses BalenaOS's documented SSH port `22222` as the Balena profile default. Existing Balena profiles on the former generic default `22` are migrated once; custom ports are preserved.
- Replaces generic failures for common SSH connection, authentication, host-key and SSH file errors with safe troubleshooting guidance.
- Explains when saved encrypted credentials cannot be decrypted, including the need to restore the matching DCC Web data volume and master key together.
- Moves legacy DCC Remote Access networks outside the collision-checked subnet pool, preventing the isolated network from capturing routes to remote hosts even before profiles are added. The tunnel sidecar stops during migration and must be enabled again after the update.

[Source ZIP](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.2.7/DCC-Web-0.2.7-source.zip) · [Profile configuration](https://github.com/hattimon/DCC/blob/dcc-web-v0.2.7/apps/dcc-web/docs/configuration.md)

## Polski

- Ustawia udokumentowany port SSH BalenaOS `22222`. Istniejące profile Balena ze starym domyślnym portem `22` są migrowane jednorazowo; porty niestandardowe pozostają bez zmian.
- Zastępuje ogólny błąd czytelną wskazówką dla typowych problemów SSH: łączności, uwierzytelniania, weryfikacji klucza hosta i plików SSH.
- Wyjaśnia, że zaszyfrowanych danych profilu nie można odszyfrować bez zgodnego wolumenu danych DCC Web i klucza głównego.
- Przenosi starszą sieć DCC Remote Access poza sprawdzoną pulę podsieci, aby izolowana sieć nie przejmowała tras do zdalnych hostów — także przed dodaniem profili. Sidecar tunelu zostaje zatrzymany podczas migracji i po aktualizacji trzeba ponownie włączyć dostęp.

[Paczka źródłowa](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.2.7/DCC-Web-0.2.7-source.zip) · [Konfiguracja profili](https://github.com/hattimon/DCC/blob/dcc-web-v0.2.7/apps/dcc-web/docs/configuration.pl.md)
