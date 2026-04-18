# piquano-core

Shared building blocks for Piquano Django apps (CRM, ATS, App, LMS, Support).

Provides the patterns that every internal app needs: Authelia SSO middleware,
CRM/ATS API clients, MS365 mail integration, audit/DSGVO helpers, Admin-Center,
AI rate-limiting, design-system CSS, and shared database support.

## License

Proprietary. See [LICENSE](LICENSE).

## Install

```txt
# Production: pin a tag
piquano-core @ git+ssh://git@github.com/piquano/piquano-core.git@v1.1.2

# Staging: track main
piquano-core @ git+ssh://git@github.com/piquano/piquano-core.git@main
```

## Modules

| Module | Purpose |
|---|---|
| `piquano_core.sso` | Authelia SSO middleware for Django |
| `piquano_core.crm_client` | Python client for the internal CRM API |
| `piquano_core.ats_client` | Python client for the internal ATS API |
| `piquano_core.ms365` | MS365 Graph API mail sync (OAuth, crypto, adapter) |
| `piquano_core.email` | Mailjet Send v3.1 wrapper with retry and logging |
| `piquano_core.audit` | AuditLog model + DSGVO export/lock/anonymize helpers |
| `piquano_core.admin_center` | Feature toggles, permissions, dashboard |
| `piquano_core.shared` | Shared database models (notes, emails, activities) |
| `piquano_core.ai` | Rate-limit decorator for Anthropic API endpoints |
| `piquano_core.utils` | `get_client_ip`, `model_field_names` |

## Versioning

Semantic Versioning. Current: **v1.1.2**.

CRM uses piquano-core as editable local install, ATS/LMS/Support install
via pip from GitHub tag.
