# Shared App Store and catalogs

The canonical root `dcc-catalog.json` keeps all 67 entries. The official source is permanent. Additional GitHub repositories, direct HTTPS JSON URLs and uploaded JSON files use the same Desktop format, including both `dcc-catalog.json` and `catalog.json` filename fallbacks. Files are uploaded, not opened through arbitrary server filesystem paths.

Legacy `category` / `category_en` remain the primary values. Optional `categories` / `categories_en` add membership without duplicating application definitions. Both interfaces use the pure `dcc_catalog.py` helpers. Category order begins All → Installed → **DCC** → AI; DCC is bold. DCC Container Updater keeps `Aktualizacje 🔄` / `Updates 🔄` and adds DCC. Existing identifiers and installation configuration are retained. Balena-compatible applications also appear under Balena OS.

```json
{"apps":[{"name":"Example official extension","image":"example/extension:1","category":"Narzędzia","category_en":"Tools","categories":["DCC"]}]}
```

This example is documentation only; no fictitious extension has been added. Official DCC extensions should receive DCC plus their functional categories. A metadata/category change can be delivered by refreshing catalogs once the installed client supports those fields. Adding client behavior (for example multi-category support to an old client) requires a client update.

Sources can be validated, inspected, refreshed, enabled/disabled and deleted. Official catalog removal/disable is rejected. Refresh retains cached data on network/validation errors. CLI servers refresh hourly and offer manual refresh; uploaded files are refreshed by replacing the upload. Duplicate name/image entries merge once and preserve supplementary metadata when an older cache omits it.

Installation validates host architecture, RAM minimum, published ports, name collisions and an allowlist of container options. A preview displays the exact Docker argument array and warnings for socket/privileges/persistent data/dependencies. Each warning must be acknowledged before the confirmation is consumed. The host never automatically executes a script from catalog metadata. A source-build entry has a separate reviewed-source action; review the repository and Dockerfile before authorizing it. Docker builds themselves execute Dockerfile code and must be trusted.

Dependencies and GPU requirements listed by a catalog are displayed for review; dependency provisioning and physical GPU availability are not automatically resolved. Port checks compare current Docker mappings, so a later external port allocation can still cause Docker to reject an installation. Uninstall removes matching containers without `-v`; data only in the removed container writable layer is not persistent storage.

Installation forms show occupied Docker ports and suggest alternatives while typing. The optional automatic selector resolves conflicts in the preview; the chosen configuration is then fixed for installation. Checks cover Docker-published TCP/UDP ports, not arbitrary non-Docker listeners on every remote OS. Docker performs the final bind validation. Missing install permission is explained and an administrator can explicitly enable that one profile capability in the UI.
