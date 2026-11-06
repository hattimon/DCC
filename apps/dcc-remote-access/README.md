# DCC Remote Access 0.1.0

DCC Remote Access is a managed zrok 2 sidecar for containerized DCC Web. NetFoundry provides the public HTTPS endpoint. A browser can reach it without a public IP, router port forwarding, a purchased domain or a VPN client. The tunnel starts disabled.

## Install and activate

In the DCC Desktop App Store, choose **DCC Web**. The **DCC Remote Access** entry is in the browser-based DCC Web App Store, where the panel manages its tunnel.

1. Use the published DCC Web 0.2.6 Docker image or a newer Web release with Remote Access. To upgrade, select the existing DCC Web container in DCC Container Updater, check for updates, and apply the offered Web image. Reload your existing panel address afterward. For a fresh installation, follow the [DCC Web container instructions](../dcc-web/docs/installation.md).
2. Sign in locally as a DCC administrator. In the **local Docker** profile, enable **Install applications**. In **Settings → Administration and security → Login and two-factor authentication**, enroll a TOTP app and save the recovery codes.
3. Install **DCC Remote Access** from the **DCC** category in the App Store or open **Settings → Administration and security → Panel access and HTTPS (TLS) → Remote Internet Access**. Both paths manage the same container.
4. Create an account at [myzrok.io](https://myzrok.io/). In the zrok API console, copy the account token from the getting-started wizard. Open the local panel over trusted HTTPS for enrollment and reauthentication. Use **Configure** to enter the token and choose a name or let DCC generate one. The hosted service reserves the name. If your chosen name is taken, select another name.
5. Select **Enable access**, read the consent prompt and confirm with your current password and a fresh TOTP or recovery code. Wait for **Active** and open the displayed HTTPS address. DCC verifies the TLS endpoint and a one-use-per-launch proof from this installation before enabling the panel. The hosted service may display its own first-visit interstitial. Sign in with your existing DCC credentials.
6. Select **Resume the tunnel after restarting DCC Web or the computer** in the enable/restart dialog if access should return automatically. This saves the administrator's authorization until **Disable access** or uninstall. **Resume the tunnel after DCC Web updates through Updater** is separate consent for the updater's verified image handoff; select both options to cover updates and computer restarts.

The [hosted enrollment guide](https://netfoundry.io/docs/zrok/get-started/get-token/) explains where to find the token. Local HTTPS, domain settings and DCC profiles continue to work independently of zrok.

If setup was interrupted after enrollment, open **Configure** again and confirm the suggested name. DCC uses the saved environment to complete the pending reservation in the hosted public namespace.

## Stop, remove, or rotate

- **Disable access** closes DCC's public ingress immediately, stops the sidecar and revokes automatic recovery. The reserved name can be reused. Without restart consent, a DCC Web restart requires a fresh local enable action. Existing installations do not gain restart consent automatically.
- Internet, DNS or hosted service outages leave the tunnel reconnecting, with public panel traffic blocked until HTTPS proof succeeds again. An unexpected sidecar exit is retried while the current session is authorized. With restart consent, DCC also restores its encrypted enrollment after a panel or computer restart and retries temporary startup failures with a bounded delay. Security blocks and removal of administrator MFA revoke recovery. A changed Web image needs an authorized Updater handoff or a fresh local enable action.
- Use **Disable access** for emergency shutdown and to revoke recovery. Stopping the sidecar alone may trigger recovery while authorization remains active. If the local UI is unavailable, stop DCC Web before stopping the exact managed container identified by the `io.dcc.remote-access` label. In the zrok console, revoke the environment or remove the share if its registration remains after a hard crash. Keep the reservation if you intend to reuse the address.
- **Uninstall** can retain the encrypted enrollment and reservation for reinstall. To rotate a token, disable the tunnel, uninstall with retention cleared, then install and enroll with the new token. If the old token has already been revoked, remove the environment and release the name in the zrok console, then confirm provider cleanup in the uninstall dialog.
- **Check for updates** reports the latest stable zrok 2 release. Apply only a reviewed module release with a verified multi-platform digest. Before switching versions, disable access and back up the Web data volume. Recreate the sidecar and explicitly verify the new tunnel. To roll back, stop the new sidecar, restore the prior reviewed DCC Web/module build and retain or restore its encrypted configuration. Never roll back to a blocked digest.

[Security model](SECURITY.md) · [Polski](README.pl.md)
