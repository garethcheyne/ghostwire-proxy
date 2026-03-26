---
title: SSL Certificates
excerpt: Manage Let's Encrypt and custom SSL certificates for your proxy hosts
---

Ghostwire Proxy supports both automated Let's Encrypt certificate provisioning and manual certificate uploads.

![Certificates](../_img/certificates.png)

## Let's Encrypt Certificates

### Requesting a Certificate

:::steps
### Click "Add Certificate" and select Let's Encrypt

Choose the Let's Encrypt provider to get free, automatically-renewed certificates.

### Enter domain names

Add one or more domain names to include in the certificate. Wildcard domains (e.g., `*.example.com`) require DNS challenge validation.

### Provide your email

Enter an email address for renewal notifications and Let's Encrypt account registration.

### Choose validation method

- **HTTP Challenge** — Requires port 80 to be reachable from the internet. Ghostwire Proxy handles the challenge automatically.
- **DNS Challenge** — Uses the Cloudflare API to create validation records. Required for wildcard certificates. Requires a [DNS provider](./dns.md) to be configured.

### Issue the certificate

Click **Request** to start the provisioning process. The certificate will be available within seconds for HTTP challenges, or a few minutes for DNS challenges.
:::

### Auto-Renewal

Let's Encrypt certificates expire every 90 days. Ghostwire Proxy automatically tracks expiration dates and renews certificates before they expire when auto-renew is enabled.

| Status | Meaning |
|--------|---------|
| :badge[Valid]{success} | Certificate is active and not expiring soon |
| :badge[Expiring Soon]{warning} | Certificate expires within 30 days |
| :badge[Expired]{error} | Certificate has expired and needs immediate renewal |

## Custom Certificates

### Uploading a Certificate

To use a certificate from another provider:

1. Click **Add Certificate** and select **Custom**
2. Paste or upload the **certificate** in PEM format
3. Paste or upload the **private key** in PEM format
4. Optionally add the **certificate chain** (intermediate certificates)

> [!IMPORTANT]
> Private keys are encrypted at rest using the `ENCRYPTION_KEY` configured in your environment variables.

## Certificate Management

| Action | Description |
|--------|-------------|
| **Renew** | Manually trigger certificate renewal |
| **Download** | Download the certificate and key files |
| **Refresh Status** | Re-check certificate validity and expiration |
| **Delete** | Remove the certificate (unassign from proxy hosts first) |

## Assigning Certificates

After creating or uploading a certificate, assign it to a proxy host via the proxy host's SSL settings. Multiple proxy hosts can share the same certificate if they use the same domain names.
