# Releasing Kiri Manager

The independent tag is `kiri-manager-v0.1.2`. The target repository is `ghcr.io/hattimon/dcc-kiri-manager`. Maintain independent versioning and source paths under `apps/kiri-manager/`.

1. Review the application-only pull request. The Store entry is prepared as a separate local change, so the published catalog can follow the verified OCI image.
2. Check the Kiri Manager workflow on the same-repository pull request. The integration jobs use disposable GitHub-hosted Linux runners for both architectures. They check Kiri identity, the real inventory, logs, stats and persistence from Docker and directly from Kiri. After the application lands, the same checks can also be dispatched from the default branch with `live=true` and `publish=false`.
3. Resolve failures, update the compatibility matrix and record environment versions. After approval, create the independent tag at the reviewed source commit and manually dispatch publication at that exact tag. Configure required reviewers for `kiri-manager-release`. The PUBLISH job depends on VERIFY, BUILD, the Docker smoke jobs and real Kiri integration.
4. Verify the registry's version, `latest` and `sha-<commit>` indexes against the OCI archive and both platform digests. The workflow compares them after upload. A published version or commit tag requires a matching digest.
5. Dispatch the Pages workflow with `publish=true` after approval. It confirms the Pages URL and the existing ownership marker before updating the project site. The deployment includes a root link to `kiri-manager/`.
6. On the deployed project site, verify HTTPS, both locales, navigation at mobile width, images, share metadata and browser console. [Project site](https://hattimon.github.io/DCC/kiri-manager/).
7. Publish the GitHub release using the English and Polish release notes. Use `gh release … --latest=false --notes-file` with UTF-8 input. Verify the tag and OCI digests on GitHub. [Release notes](../RELEASE_NOTES_0.1.2.md).
8. Merge the dedicated Store change after the versioned image and project page are verified. Use `python tools/catalog_review.py --output <new-file>` to preview the change. Check the loopback port, dedicated volume and category **DCC**. Entries for other apps should compare byte for byte.

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
