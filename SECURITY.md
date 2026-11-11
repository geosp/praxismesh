# Security policy

## Supported versions

PraxisMesh has not been released yet. Until the first tagged release, only the `main` branch is supported. The release and support policy will be described in [docs/release.md](docs/release.md).

## Reporting a vulnerability

**Please do not report security problems in public issues, pull requests or discussions.**

Report privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**, or go directly to <https://github.com/geosp/praxismesh/security/advisories/new>. Only the maintainers can see the report.

Please include:

- what is affected (file, component or configuration) and the commit or version;
- how to reproduce it, ideally with a minimal example;
- the impact you expect (for example credential exposure, privilege escalation, sandbox escape);
- any suggested fix or mitigation.

## What to expect

The project currently has a single maintainer, so responses are best effort. The aim is to acknowledge a report within a week and to agree on a disclosure timeline with the reporter. Fixes are developed in a private advisory and published with credit to the reporter unless they prefer otherwise.

## Scope notes

PraxisMesh treats prompt content, repository files, tool output and webhook bodies as untrusted input; agent privileges come only from validated system configuration (plan §2 and §9.5). Reports showing that untrusted input can grant tools, skills, secrets or repository access are especially welcome. A threat model will be published under `docs/security/` as the platform is built.
