# piquano-core

Shared building blocks for PIQUANO Django apps (CRM, ATS, Ticket, LMS).

Provides the patterns that every internal app needs so they don't have to be
re-invented per project: Authelia SSO middleware, CRM API client, Mailjet
wrapper, audit/DSGVO helpers, design-system CSS, and deployment templates.

## Install

In a downstream app's `requirements.txt`:

```
# Production: pin a tag
piquano-core @ git+ssh://git@github.com/piquano/piquano-core.git@v0.1.0

# Staging: track main
piquano-core @ git+ssh://git@github.com/piquano/piquano-core.git@main
```

## Modules

| Module                            | Purpose                                                |
| --------------------------------- | ------------------------------------------------------ |
| `piquano_core.sso.middleware`     | `AutheliaRemoteUserMiddleware` for Django              |
| `piquano_core.crm_client`         | Python client for the internal CRM API                 |
| `piquano_core.email.mailjet`      | Mailjet Send v3.1 wrapper with retry & logging        |
| `piquano_core.audit.models`       | `AuditLog` model + DSGVO export/lock/anonymize helpers |
| `piquano_core.utils`              | `get_client_ip`, `model_field_names`                   |

## Deployment templates

In `deploy/`:

- `deploy.sh.template` — pull → migrate → collectstatic → restart → status check
- `systemd.service.template` — Gunicorn unit
- `nginx.conf.template` — site config with Authelia forward auth
- `backup.sh.template` — daily PG dump to `/var/backups/<app>/`

Replace placeholders (`__APP__`, `__PORT__`, `__DOMAIN__`) and copy into the
target system.

## Versioning

Semantic Versioning. Breaking changes require a major bump and explicit
upgrade in each consuming app.
