# DCC Remote Access 0.1.0

DCC Remote Access is a managed zrok 2 sidecar for containerized DCC Web. NetFoundry provides the public HTTPS endpoint. A browser can reach it without a public IP, router port forwarding, a purchased domain or a VPN client. The tunnel starts disabled.

## Install and activate

1. Use the published DCC Web 0.2.3 Docker image or a newer Web release with Remote Access. To upgrade, select the existing DCC Web container in DCC Container Updater, check for updates, and apply the offered Web image. Reload your existing panel address afterward. For a fresh installation, follow the [DCC Web container instructions](../dcc-web/docs/installation.md).
2. Sign in locally as a DCC administrator. In the **local Docker** profile, enable **Install applications**. In **Settings → Administration and security → Login and two-factor authentication**, enroll a TOTP app and save the recovery codes.
3. Install **DCC Remote Access** from the **DCC** category in the App Store or open **Settings → Administration and security → Panel access and HTTPS (TLS) → Remote Internet Access**. Both paths manage the same container.
4. Create an account at [myzrok.io](https://myzrok.io/). In the zrok API console, copy the account token from the getting-started wizard. Open the local panel over trusted HTTPS for enrollment and reauthentication. Use **Configure** to enter the token and choose a name or let DCC generate one. The hosted service reserves the name. If your chosen name is taken, select another name.
5. Select **Enable access**, read the consent prompt and confirm with your current password and a fresh TOTP or recovery code. Wait for **Active** and open the displayed HTTPS address. DCC verifies the TLS endpoint and a one-use-per-launch proof from this installation before enabling the panel. The hosted service may display its own first-visit interstitial. Sign in with your existing DCC credentials.

The [hosted enrollment guide](https://netfoundry.io/docs/zrok/get-started/get-token/) explains where to find the token. Local HTTPS, domain settings and DCC profiles continue to work independently of zrok.

## Stop, remove, or rotate

- **Disable access** closes DCC's public ingress immediately and stops the sidecar. The reserved name can be reused. A DCC Web restart closes the ingress and requires a fresh local enable action.
- For emergency shutdown when the local UI is unavailable, identify the exact managed container by the `io.dcc.remote-access` label and run `docker stop <managed-container>` on the same host. In the zrok console, revoke the environment or remove the share if its registration remains after a hard crash. Keep the reservation if you intend to reuse the address.
- **Uninstall** can retain the encrypted enrollment and reservation for reinstall. To rotate a token, disable the tunnel, uninstall with retention cleared, then install and enroll with the new token. If the old token has already been revoked, remove the environment and release the name in the zrok console, then confirm provider cleanup in the uninstall dialog.
- **Check for updates** reports the latest stable zrok 2 release. Apply only a reviewed module release with a verified multi-platform digest. Before switching versions, disable access and back up the Web data volume. Recreate the sidecar and explicitly verify the new tunnel. To roll back, stop the new sidecar, restore the prior reviewed DCC Web/module build and retain or restore its encrypted configuration. Never roll back to a blocked digest.

[Security model](SECURITY.md) · [Polski](README.pl.md)
