# PIQUANO Branch- & Release-Konvention

Gilt für **alle PIQUANO-Repos**: `piquano-core`, `piquano-app`, `piquano-crm`,
`piquano-ats`, `piquano-ticket`, `piquano-lms`.

## Grundregel

| Branch  | Bedeutung                              | Auto-Deploy nach          |
| ------- | -------------------------------------- | ------------------------- |
| `main`  | Staging — was hier landet, läuft live  | `*-staging.piquano.com`   |
| `prod`  | Production — bewusst promoteter Stand  | `*.piquano.com`           |
| `hot/*` | Hotfix-Branches (von `prod` abzweigen) | nichts, manuelles Merge   |

**Niemand committet direkt auf `prod`.** Promotion ist ein expliziter Push.

## Workflow

### Normale Entwicklung

```bash
# Feature-Branch (optional, kann auch direkt auf main)
git switch -c feature/foo
# … arbeiten …
git push -u origin feature/foo
# PR → main, mergen
```

Sobald ein Commit auf `main` landet, läuft er auf `*-staging.piquano.com`
nach dem nächsten `deploy.sh` (manuell oder per Cron).

### Promotion main → prod

```bash
git fetch origin
git push origin origin/main:prod        # Fast-Forward Push
```

Auf der Prod-Maschine dann:

```bash
cd /opt/<app>
./deploy.sh                              # pullt 'prod', migrate, restart
```

Promotion ist immer Fast-Forward. Wenn nicht: erst klären, was auf `prod`
diverged ist (Hotfix?), dann merge zurück nach `main`, dann promoten.

### Hotfix in Production

```bash
# Direkt auf der Prod-Quelle, nicht auf der Maschine
git fetch origin
git switch -c hot/auth-bug origin/prod
# Fix, commit
git push -u origin hot/auth-bug
# Review, dann:
git push origin hot/auth-bug:prod        # auf Prod deployen
git push origin hot/auth-bug:main        # zurück nach main mergen
```

Niemals einen Hotfix nur auf `prod` lassen — `main` würde davon nichts
wissen und die nächste Promotion wäre kein Fast-Forward mehr.

## Sonderfall: `piquano-core` (Library)

`piquano-core` ist eine Library, kein Service. Statt prod/staging gibt es
**Tags** als „Release":

* `main` — wird von **Staging-Apps** als `@main` gepullt (immer aktuellster Stand)
* Tags `v*.*.*` — werden von **Prod-Apps** in `requirements.txt` gepinnt
* `prod`-Branch existiert hier **nicht**

Promotion in der Library-Welt ist ein Tag-Bump:

```bash
git tag -a v0.2.0 -m "v0.2.0 — added X"
git push origin v0.2.0
```

Anschließend in den Prod-Branches der konsumierenden Apps die Pin in
`requirements.txt` updaten und durch den normalen `main → prod`-Workflow
promoten.

### SemVer-Regeln für piquano-core

| Bump  | Wann                                                  |
| ----- | ----------------------------------------------------- |
| Major | Breaking Change (Signatur, entfernte Funktion, …)     |
| Minor | Neue Funktion, abwärtskompatibel                      |
| Patch | Bugfix, interne Refaktorierung                        |

Major-Bumps erfordern explizites Update in jeder konsumierenden App, kein
Auto-Upgrade.

## CI-Anforderungen

Jeder Push auf `main` und jeder PR triggert die CI (siehe `.github/workflows/ci.yml`):

* **Lint** (`ruff check`)
* **Format-Check** (`ruff format --check`)
* **Compile-Check** (`python -m py_compile` für alle `.py`)
* **Tests** (`pytest`, sobald welche existieren)

Apps zusätzlich:
* **Django-System-Checks** (`manage.py check --deploy`)
* **Migrations vollständig** (`manage.py makemigrations --check --dry-run`)

CI muss grün sein, bevor `main → prod` gepusht wird. Es gibt keine
automatische Branch-Protection-Regel — die Regel lebt im Kopf.

## Was NICHT erlaubt ist

* **`git push --force`** (überall blockiert durch den lokalen Prod-Guard-Hook)
* **Direktes Editieren auf der Prod-Maschine** (Regel #1: Entwicklung nur auf Staging)
* **Promotion ohne grüne CI** auf `main`
* **Hotfix nur in `prod`** ohne Backport nach `main`
