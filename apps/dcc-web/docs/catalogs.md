# Shared App Store and catalogs

The canonical root `dcc-catalog.json` keeps all 68 entries, including DCC Web. The official source is permanent. Additional GitHub repositories, direct HTTPS JSON URLs and uploaded JSON files use the same Desktop format, including both `dcc-catalog.json` and `catalog.json` filename fallbacks. Files are uploaded, not opened through arbitrary server filesystem paths.

Legacy `category` / `category_en` remain the primary values. Optional `categories` / `categories_en` add membership without duplicating application definitions. Both interfaces use the pure `dcc_catalog.py` helpers. Category order begins All → Installed → **DCC** → AI; DCC is bold. DCC Container Updater keeps `Aktualizacje 🔄` / `Updates 🔄` and adds DCC. Existing identifiers and installation configuration are retained. Balena-compatible applications also appear under Balena OS.

```json
{"apps":[{"name":"Example official extension","image":"example/extension:1","category":"Narzędzia","category_en":"Tools","categories":["DCC"]}]}
```

This example is documentation only; no fictitious extension has been added. Official DCC extensions should receive DCC plus their functional categories. A metadata/category change can be delivered by refreshing catalogs once the installed client supports those fields. Adding client behavior (for example multi-category support to an old client) requires a client update.

Sources can be validated, inspected, refreshed, enabled/disabled and deleted. Official catalog removal/disable is rejected. Refresh retains cached data on network/validation errors. CLI servers refresh hourly and offer manual refresh; uploaded files are refreshed by replacing the upload.

### One application, one current entry

DCC Web 0.1.5 merges versions using the application name, image repository (without tag/digest), and default container name. Categories never create separate applications. Stable numeric tags are compared numerically, so an old database cache or imported catalog cannot downgrade a newer bundled entry. Moving tags such as `latest` and explicit digest pins follow source precedence; their chronological order cannot be inferred from the reference. Explicit variants with distinct default container names and unrelated image repositories remain separate.

The published JSON defines each application/variant once. CI and catalog maintenance reject duplicate definitions before publication. To release an application, update its existing entry instead of appending a version. The Web entry tracks only `dcc-web-vX.Y.Z` releases, and maintenance verifies both amd64 and arm64 images before advancing its tag. Refresh therefore never offers an image that has not been published for its declared architectures.

### Older Desktop clients

The schema stays at version 1. The legacy primary category for DCC Web is Administration; additional membership is DCC and WWW. Updater keeps Updates as its primary category. Clients that read only `category` still see installable entries in those functional categories. Container Updater reads the current shared catalog independently of the Desktop store's displayed entries.

Desktop binaries released before the merge fix identify applications by name **and the complete image tag**. A binary containing Web 0.1.0 can consequently retain that bundled entry alongside the current online version. No field in schema 1 instructs that binary to delete a bundled entry. Refreshing the remote JSON cannot change this behavior; an updated client is needed to eliminate it there. DCC Web's independent container update does fix its own store without changing EXE/DEB packages. Published version tags are not overwritten to disguise older builds as current ones.

Installation validates host architecture, RAM minimum, published ports, name collisions and an allowlist of container options. A preview displays the exact Docker argument array and warnings for socket/privileges/persistent data/dependencies. Each warning must be acknowledged before the confirmation is consumed. The host never automatically executes a script from catalog metadata. A source-build entry has a separate reviewed-source action; review the repository and Dockerfile before authorizing it. Docker builds themselves execute Dockerfile code and must be trusted.

Dependencies and GPU requirements listed by a catalog are displayed for review; dependency provisioning and physical GPU availability are not automatically resolved. Port checks compare current Docker mappings, so a later external port allocation can still cause Docker to reject an installation. Uninstall removes matching containers without `-v`; data only in the removed container writable layer is not persistent storage.

Installation forms show occupied Docker ports and suggest alternatives while typing. The optional automatic selector resolves conflicts in the preview; the chosen configuration is then fixed for installation. Checks cover Docker-published TCP/UDP ports, not arbitrary non-Docker listeners on every remote OS. Docker performs the final bind validation. Missing install permission is explained and an administrator can explicitly enable that one profile capability in the UI.
