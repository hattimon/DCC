# Releasing Kiri Manager

The independent tag is `kiri-manager-v0.1.0`. The target repository is `ghcr.io/hattimon/dcc-kiri-manager`. Maintain independent versioning and source paths under `apps/kiri-manager/`.

1. Review and approve the application-only change. Land it with the dedicated workflows. The Store entry is prepared as a separate local change, so the published catalog can follow the verified OCI image.
2. Dispatch the Kiri Manager workflow with `live=true` and `publish=false` from the reviewed default branch. Verify both native Linux architectures on disposable GitHub runners. Inspect Kiri identity, the real inventory, logs, a statistics sample and configuration persistence from Docker and directly from Kiri.
3. Resolve failures, update the compatibility matrix and record environment versions. After approval, create the independent tag at the reviewed source commit and manually dispatch publication at that exact tag. Configure required reviewers for `kiri-manager-release`. The PUBLISH job depends on VERIFY, BUILD, the Docker smoke jobs and real Kiri integration.
4. Verify the registry's `0.1.0`, `latest` and `sha-<commit>` indexes against the OCI archive and both platform digests. The workflow compares them after upload. If a version or commit tag already exists, its digests must match.
5. Set up and approve the initial GitHub Pages deployment only after checking the repository still has no unrelated Pages publisher. Set **Settings → Pages → Source → GitHub Actions** and review the `github-pages` environment. Dispatch the separate Pages workflow with `publish=true`. Its build confirms the Pages URL and refuses to overwrite an unrelated recognizable root. The deployment owns the project Pages artifact, including a root link to `kiri-manager/`.
6. On the deployed project site, verify HTTPS, both locales, navigation at mobile width, images, all share metadata and browser console. The target URL is [hattimon.github.io/DCC/kiri-manager](https://hattimon.github.io/DCC/kiri-manager/). GitHub reported `has_pages=false` and returned 404 for the repository Pages resource on 2026-11-25. The target path is reserved by the build; the URL is public only after deployment. [GitHub Pages workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
7. Publish the GitHub release using [English/Polish release notes](../RELEASE_NOTES_0.1.0.md). An approved publish uses `gh release … --notes-file` with UTF-8 input and a Unicode read-back. Verify the tag and selected OCI digests on GitHub.
8. Merge the dedicated Store entry after the versioned image and project URL are verified. Use `python tools/catalog_review.py --output <new-file>` to preview the exact one-entry change against an updated catalog if needed. Check installation with the loopback port and dedicated volume. Existing entries should compare byte for byte.

## Build the site locally

```sh
python tools/prepare_pages.py browser-artifacts/pages-preview
python -m http.server --bind 127.0.0.1 --directory browser-artifacts/pages-preview 8000
```

Preview `http://127.0.0.1:8000/kiri-manager/`. Both locale documents have independent metadata. The approved workflow passes the confirmed base URL to insert canonical links, alternate languages and absolute social card URLs into the artifact.

## Future versions

- **0.2.0**. Start/stop/restart behind explicit access controls and extended monitoring after real-engine compatibility evidence.
- **0.3.0**. Expand Compose observation and verify safe Windows/WSL2 and macOS transport options.
- **Migration proposal**. Stage an independently approved workflow with an inventory-only plan, collision checks, digest and data-integrity proofs, isolated target copies and explicit cutover. Prefer native backup/restore for stateful services. Test recovery from mid-copy failure and rollback that affects only resources created by the migration. Kiri upstream already offers import on selected platforms. [Upstream import behavior](https://docs.runkiri.com/docker/migrate/).
- **1.0.0**. Supported platform matrix and documented update paths backed by repeated integration tests.
