# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it via [GitHub Security Advisories](https://github.com/weirdtangent/blink2mqtt/security/advisories/new).

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (optional)

## Container Image Verification

Docker images are signed using [Cosign](https://github.com/sigstore/cosign) with keyless signing via GitHub Actions OIDC.

### Verifying Image Signatures

```bash
cosign verify graystorm/blink2mqtt:latest \
  --certificate-identity-regexp="https://github.com/weirdtangent/blink2mqtt/.*" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"
```

## Security Scanning

- Container images are scanned with [Trivy](https://github.com/aquasecurity/trivy) on every build
- Scan results are uploaded to the GitHub Security tab
- SBOM (Software Bill of Materials) is generated for each image
- Build provenance is attested for supply chain security
