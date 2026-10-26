# Release notes

## Source release

This source release contains the ATLAS review workbench, CHAOSLAB evaluators, synthetic examples, measured reports, tests and operator documentation.

The source release excludes credentials, local databases, raw provider artifacts, installed dependencies and private workspace material. It starts with a fresh Git history. Exact file hashes and the publication inventory are kept in the release manifest; they do not represent additional test evidence.

The initial source publication passed 460 native tests, with eighteen optional PostgreSQL groups skipped. Later verification is recorded separately in [current status](STATUS.md). Database, browser, container and live-model checks have separate reports. Known benchmark failures are included. That [corrected GitHub CI run](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39461145031) passed 460 backend tests, ten private-workbench browser tests, three static-viewer tests and three synthetic-lab browser tests. Eighteen optional PostgreSQL groups were skipped; their local evidence remains separate.

The [source repository](https://github.com/harshituppala/atlas-chaoslab) is public. The uploaded file tree was checked against the reviewed release.

## Hosting

The [fictional review lab](https://atlas-review-lab.onrender.com) is live and passes targeted HTTPS, browser and controlled restart checks. The full managed review service has not been deployed. The [hosting plan](deployment-options.md) describes the provider constraints and the difference between a temporary synthetic lab and a durable review service.

The local bearer-token launcher is for private use. A full hosted service needs real sign-in, durable source and review storage, private database roles, HTTPS and a tested recovery path. The public lab resets session history, as explained in the interface and checked during a real service restart.

## Next release

The lab's HTTP, browser and restart checks are recorded in the [status notes](STATUS.md). The next hosting work is to observe cold starts and shared free-tier quotas, then prepare the full service with managed sign-in and durable storage. Those are separate from the temporary lab already running.

The [portfolio](https://harshit-uppala-portfolio.vercel.app) links to the lab and each tool's guide. Its project dialogs were checked on desktop and mobile after deployment.
