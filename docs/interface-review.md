# Review interface

ATLAS uses a quiet document layout: warm paper, dark text, a serif face for requirements and source excerpts, and compact navigation. Counts share one strip rather than four separate cards. Status colors identify evidence, conflicts and gaps; they do not decorate the page. The selected requirement keeps a visible edge and readable text.

CHAOSLAB uses the same application shell with a restrained blue section rule and aligned numeric summaries. Failed cases and incomplete runs remain visible. Its tables and scope notes carry the detail; the interface adds no new performance claims. The recorded viewer now describes the saved reviews directly instead of opening with a slogan. The fictional public lab keeps its separate session and input restrictions.

The refinement also removes decorative navigation symbols, the redundant pipeline-step chips and the engineering-status footer. The exact execution mode remains beside the source record, where it helps a reviewer understand the result. Navigation exposes its current page to assistive technology, and the sign-in page uses a properly centered layout. System fonts avoid another external request or font dependency.

[Desktop review](../reports/interface-review-desktop.png) · [Phone review](../reports/interface-review-mobile.png) · [Evaluation details](../reports/interface-evaluation.png) · [Public lab preview](../reports/interface-public-lab.png)

Twenty local Chromium cases passed across the private workbench, disconnected layout, recorded viewer and synthetic lab. Connected review and benchmark layouts were checked at phone and tablet widths; source dialogs retained Escape handling and focus return. Existing upload, review, access and unknown-metric checks passed. The separate joined HTTPS login check also passed twelve groups using a synthetic identity provider. The native Python suite passed 833 tests, with eighteen optional database groups skipped. These are layout and functional checks, not a complete accessibility audit or evidence from user research. The [record](../reports/interface-review.json) identifies their source and screenshots.

Test screenshots now go to ignored `var/ui-review/screenshots` by default. This preserves earlier authored report images; selected, inspected images are copied to new report filenames for publication. Existing owner-edited screenshots and private documents were checked unchanged. Hosting is a separate step: these screenshots describe the local builds, not a newly verified public deployment.
