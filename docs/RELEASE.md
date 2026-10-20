# Release notes

## Source release

This source release contains the ATLAS review workbench, CHAOSLAB evaluators, synthetic examples, measured reports, tests and operator documentation.

The source release excludes credentials, local databases, raw provider artifacts, installed dependencies and private workspace material. It starts with a fresh Git history. Exact file hashes and the publication inventory are kept in the release manifest; they do not represent additional test evidence.

The latest native suite for this version passed 460 tests, with 18 optional PostgreSQL groups skipped. Database, browser, container and live-model checks have separate reports. Known benchmark failures are included. The [corrected GitHub CI run](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39461145031) passed 460 backend tests, ten private-workbench browser tests, three static-viewer tests and three synthetic-lab browser tests. Eighteen optional PostgreSQL groups were skipped; their local evidence remains separate.

The [source repository](https://github.com/harshituppala/atlas-chaoslab) is public. The uploaded file tree was checked against the reviewed release.

## Hosting

The [fictional review lab](https://atlas-review-lab.onrender.com) is live and passes targeted HTTPS, browser and controlled restart checks. The full managed review service has not been deployed. Hosting must stay free; the model-test allowance does not authorize infrastructure spending. The [hosting plan](deployment-options.md) describes the provider constraints and the difference between a temporary synthetic lab and a durable review service.

The local bearer-token launcher is for private use. A full hosted service needs real sign-in, durable source and review storage, private database roles, HTTPS and a tested recovery path. A synthetic lab may deliberately reset session history, provided the interface explains that behavior and the deployment tests confirm it.

## Release checks

Source inventory, public contents and the initial CI outcome have been checked. Remaining deployment work:

1. Check the selected host's free-plan limits and billing settings before creating a service.
2. Preserve the completed lab acceptance checks and observe cold-start and usage-limit behavior; complete durable hosting and real sign-in separately.
3. Record failures and teardown steps alongside the results.

Source publication and a reachable page do not establish production operation. The lab acceptance checks have run; the full service and broader evaluation remain unfinished.
