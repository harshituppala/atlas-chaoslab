# Release notes

## Source release

This source release contains the ATLAS review workbench, CHAOSLAB evaluators, synthetic examples, measured reports, tests and operator documentation.

The source release excludes credentials, local databases, raw provider artifacts, installed dependencies and private workspace material. It starts with a fresh Git history. Exact file hashes and the publication inventory are kept in the release manifest; they do not represent additional test evidence.

The latest native suite for this version passed 453 tests, with 18 optional PostgreSQL groups skipped. Database, browser, container and live-model checks have separate reports. Known benchmark failures are included. The [first GitHub CI run](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39451999129) passed its backend and browser jobs: 393 backend tests, ten workbench browser tests and three static-viewer tests. Eighteen optional PostgreSQL groups were skipped; their local evidence remains separate.

The [source repository](https://github.com/harshituppala/atlas-chaoslab) is public. The uploaded file tree was checked against the reviewed release. The initial upload was rejected for missing workflow permission; it succeeded after the owner approved GitHub’s authorization screen.

## Hosting

There is no hosted ATLAS URL yet. Hosting must stay free; the model-test allowance does not authorize infrastructure spending. The [hosting plan](deployment-options.md) describes the provider constraints and the difference between a temporary synthetic lab and a durable review service.

The local bearer-token launcher is for private use. A full hosted service needs real sign-in, durable source and review storage, private database roles, HTTPS and a tested recovery path. A synthetic lab may deliberately reset session history, provided the interface explains that behavior and the deployment tests confirm it.

## Release checks

Source inventory, public contents and the initial CI outcome have been checked. Remaining deployment work:

1. Check the selected host's free-plan limits and billing settings before creating a service.
2. Exercise the deployed workflow, isolation, review conflicts and restart behavior at the actual URL.
3. Record failures and teardown steps alongside the results.

Source publication and a reachable page do not establish production operation. Deployment remains unfinished until the hosted checks have run.
