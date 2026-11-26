# DCC Kiri Manager 0.1.3

- Manage container lifecycle: start, stop, restart, pause, resume and remove stopped containers with explicit confirmation; named volumes are preserved.
- Create SSH profiles for Kiri and Docker with pinned host keys, password or private-key authentication, and encrypted credentials at rest.
- Migrate settings transactionally to schema 3 with a schema 2 backup, private master key, bilingual forms and actionable connection diagnostics.
- Verified on disposable GitHub-hosted Linux AMD64 and ARM64 runners with Kiri 0.2.2 and Docker, including lifecycle, SSH, volume retention, image upgrade and rollback.
- Windows/WSL access on a user's own engine is not covered by the isolated runner results; see the compatibility matrix.

---

- Zarządzanie cyklem życia kontenerów: start, stop, restart, pauza, wznowienie i usuwanie zatrzymanych kontenerów po potwierdzeniu; wolumeny nazwane są zachowane.
- Profile SSH dla Kiri i Docker z przypiętymi kluczami hostów, uwierzytelnianiem hasłem lub kluczem prywatnym oraz szyfrowaniem poświadczeń w spoczynku.
- Transakcyjna migracja ustawień do schematu 3 z kopią schematu 2, prywatnym kluczem głównym, formularzami PL/EN i czytelną diagnostyką połączeń.
- Weryfikacja na izolowanych runnerach GitHub Actions Linux AMD64 i ARM64 z Kiri 0.2.2 i Dockerem obejmuje operacje, SSH, zachowanie wolumenów, aktualizację obrazu i rollback.
- Wyniki izolowanych runnerów nie potwierdzają dostępu Windows/WSL do silnika użytkownika; szczegóły zawiera macierz zgodności.

See [security](https://github.com/hattimon/DCC/blob/kiri-manager-v0.1.3/apps/kiri-manager/docs/security.md), [API](https://github.com/hattimon/DCC/blob/kiri-manager-v0.1.3/apps/kiri-manager/docs/api.md), [installation](https://github.com/hattimon/DCC/blob/kiri-manager-v0.1.3/apps/kiri-manager/docs/installation.md) and [compatibility](https://github.com/hattimon/DCC/blob/kiri-manager-v0.1.3/apps/kiri-manager/docs/compatibility.md).
