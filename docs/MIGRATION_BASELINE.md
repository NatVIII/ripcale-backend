# ripcale — Migration Baseline (import graph)

> Frozen snapshot generated 2026-11-09 by `scripts/import_graph.py`. Regenerate and diff against this in F76 to confirm no stale imports remain.

- **Test count at baseline:** 542
- **Importer files with `app.*` imports:** 132
- **Distinct targets:** 77

## Hub modules (imported by N files)

| imports | module |
|---:|---|
| 58 | `app.models` |
| 55 | `app.schema` |
| 52 | `app.config` |
| 25 | `app.security` |
| 25 | `app.services.actions` |
| 21 | `app.db` |
| 17 | `app.identity` |
| 15 | `app.intake` |
| 14 | `app.registry` |
| 14 | `app.web` |
| 14 | `app.admin` |
| 13 | `app.logging` |
| 12 | `app.services.clock` |
| 12 | `app.timeutil` |
| 12 | `app.services.events` |
| 12 | `app.ingest` |
| 9 | `app.gatherers.errors` |
| 9 | `app.services.images` |
| 8 | `app.services.categories` |
| 7 | `app.services.auth` |
| 7 | `app.gatherers.elfsight.gatherer` |
| 7 | `app.sieve` |
| 7 | `app.services.status` |
| 7 | `app.services.approvals` |
| 6 | `app.decisionmaker` |
| 6 | `app.services.archive` |
| 5 | `app.routers.debug` |
| 5 | `app.services.stats` |
| 5 | `app.gatherers.base` |
| 5 | `app.services.recurrence` |
| 5 | `app.services.deepseek` |
| 5 | `app.public` |
| 4 | `app.routers.pipeline` |
| 4 | `app.services.ssrf` |
| 4 | `app.services.pending` |
| 4 | `app.categorize` |
| 4 | `app.routers.events` |
| 4 | `app.serializers` |
| 4 | `app.services.expiry` |
| 3 | `app.services.scheduler` |
| 3 | `app.services.overseer_worker` |
| 3 | `app.services.llm_worker` |
| 3 | `app.categorize.categorize` |
| 3 | `app.decisionmaker.decisionmaker` |
| 3 | `app.services.lock` |
| 3 | `app.routers.feeds` |
| 3 | `app.services.ics` |
| 3 | `app.services.backup` |
| 2 | `app.routers.images` |
| 2 | `app.routers.retag` |
| 2 | `app.services.backup_worker` |
| 2 | `app.gatherers.hikerapi.gatherer` |
| 2 | `app.gatherers.ics.gatherer` |
| 2 | `app.services.placeholders` |
| 2 | `app.gatherers` |
| 2 | `app.services.retag` |
| 2 | `app.services.coherence` |
| 2 | `app.services.wipe` |
| 2 | `app.services.conflicts` |
| 2 | `app.services.testrunner` |
| 2 | `app.services.vtimezone` |
| 2 | `app.services.llm` |
| 2 | `app.services.overseer` |
| 2 | `app.sieve.sieve` |
| 1 | `app.routers.wipe` |
| 1 | `app.routers.ingest` |
| 1 | `app.routers.auth` |
| 1 | `app.routers.overseer` |
| 1 | `app.routers.api` |
| 1 | `app.routers.images_admin` |
| 1 | `app.routers.conflicts` |
| 1 | `app.routers.tests` |
| 1 | `app.routers.approvals` |
| 1 | `app.routers.backup` |
| 1 | `app.routers.archive` |
| 1 | `app.routers.event` |
| 1 | `app.audit` |

## Mutual imports (2-cycle check)

None (no direct mutual imports).

## Full edge list (importer → target)

```
app.admin -> app.config
app.admin -> app.db
app.admin -> app.logging
app.admin -> app.models
app.admin -> app.registry
app.admin -> app.routers.api
app.admin -> app.routers.approvals
app.admin -> app.routers.archive
app.admin -> app.routers.auth
app.admin -> app.routers.backup
app.admin -> app.routers.conflicts
app.admin -> app.routers.debug
app.admin -> app.routers.event
app.admin -> app.routers.images
app.admin -> app.routers.images_admin
app.admin -> app.routers.ingest
app.admin -> app.routers.overseer
app.admin -> app.routers.pipeline
app.admin -> app.routers.retag
app.admin -> app.routers.tests
app.admin -> app.routers.wipe
app.admin -> app.security
app.admin -> app.services.auth
app.admin -> app.services.backup_worker
app.admin -> app.services.llm_worker
app.admin -> app.services.overseer_worker
app.admin -> app.services.scheduler
app.archive -> app.db
app.archive -> app.logging
app.archive -> app.services.actions
app.auth -> app.db
app.auth -> app.logging
app.auth -> app.models
app.auth -> app.services.auth
app.backup -> app.logging
app.backup -> app.services.actions
app.categorize -> app.categorize.categorize
app.categorize.categorize -> app.intake
app.categorize.categorize -> app.schema
app.categorize.categorize -> app.services.categories
app.db -> app.config
app.db -> app.models
app.debug -> app.db
app.debug -> app.logging
app.debug -> app.services.stats
app.decisionmaker -> app.decisionmaker.decisionmaker
app.decisionmaker.decisionmaker -> app.models
app.decisionmaker.decisionmaker -> app.registry
app.decisionmaker.decisionmaker -> app.schema
app.decisionmaker.decisionmaker -> app.services.clock
app.gatherers.base -> app.gatherers.errors
app.gatherers.base -> app.services.ssrf
app.gatherers.elfsight.__main__ -> app.gatherers.elfsight.gatherer
app.gatherers.elfsight.__main__ -> app.registry
app.gatherers.elfsight.__main__ -> app.schema
app.gatherers.elfsight.gatherer -> app.gatherers.base
app.gatherers.elfsight.gatherer -> app.schema
app.gatherers.elfsight.gatherer -> app.timeutil
app.gatherers.hikerapi.__main__ -> app.gatherers.errors
app.gatherers.hikerapi.__main__ -> app.gatherers.hikerapi.gatherer
app.gatherers.hikerapi.__main__ -> app.registry
app.gatherers.hikerapi.__main__ -> app.schema
app.gatherers.hikerapi.gatherer -> app.config
app.gatherers.hikerapi.gatherer -> app.gatherers.errors
app.gatherers.hikerapi.gatherer -> app.schema
app.gatherers.hikerapi.gatherer -> app.services.ssrf
app.gatherers.ics.__main__ -> app.gatherers.ics.gatherer
app.gatherers.ics.__main__ -> app.registry
app.gatherers.ics.__main__ -> app.schema
app.gatherers.ics.gatherer -> app.gatherers.base
app.gatherers.ics.gatherer -> app.schema
app.gatherers.ics.gatherer -> app.services.recurrence
app.gatherers.ics.gatherer -> app.timeutil
app.identity -> app.schema
app.images -> app.db
app.images -> app.logging
app.images -> app.services.actions
app.ingest -> app.categorize
app.ingest -> app.config
app.ingest -> app.db
app.ingest -> app.decisionmaker
app.ingest -> app.gatherers.errors
app.ingest -> app.identity
app.ingest -> app.logging
app.ingest -> app.models
app.ingest -> app.registry
app.ingest -> app.schema
app.ingest -> app.services.archive
app.ingest -> app.services.clock
app.ingest -> app.services.images
app.ingest -> app.services.lock
app.ingest -> app.services.pending
app.ingest -> app.services.placeholders
app.ingest -> app.services.status
app.ingest -> app.sieve
app.intake -> app.config
app.intake -> app.schema
app.logging -> app.config
app.public -> app.config
app.public -> app.db
app.public -> app.logging
app.public -> app.models
app.public -> app.routers.events
app.public -> app.routers.feeds
app.public -> app.routers.images
app.registry -> app.intake
app.registry -> app.schema
app.routers.api -> app.logging
app.routers.api -> app.security
app.routers.api -> app.services.actions
app.routers.api -> app.services.archive
app.routers.approvals -> app.security
app.routers.approvals -> app.services.actions
app.routers.approvals -> app.web
app.routers.archive -> app.security
app.routers.archive -> app.services.actions
app.routers.archive -> app.services.archive
app.routers.archive -> app.web
app.routers.auth -> app.security
app.routers.auth -> app.services.actions
app.routers.auth -> app.services.auth
app.routers.auth -> app.web
app.routers.backup -> app.security
app.routers.backup -> app.services.actions
app.routers.backup -> app.web
app.routers.conflicts -> app.security
app.routers.conflicts -> app.services.actions
app.routers.conflicts -> app.web
app.routers.debug -> app.logging
app.routers.debug -> app.security
app.routers.debug -> app.services.actions
app.routers.debug -> app.services.clock
app.routers.debug -> app.services.events
app.routers.debug -> app.services.status
app.routers.debug -> app.timeutil
app.routers.debug -> app.web
app.routers.event -> app.security
app.routers.event -> app.services.actions
app.routers.event -> app.web
app.routers.events -> app.db
app.routers.events -> app.serializers
app.routers.events -> app.services.clock
app.routers.events -> app.services.events
app.routers.events -> app.timeutil
app.routers.feeds -> app.db
app.routers.feeds -> app.services.events
app.routers.feeds -> app.services.ics
app.routers.images -> app.services.images
app.routers.images_admin -> app.security
app.routers.images_admin -> app.services.actions
app.routers.images_admin -> app.web
app.routers.ingest -> app.registry
app.routers.ingest -> app.security
app.routers.ingest -> app.services.actions
app.routers.ingest -> app.web
app.routers.overseer -> app.security
app.routers.overseer -> app.services.actions
app.routers.overseer -> app.web
app.routers.pipeline -> app.gatherers
app.routers.pipeline -> app.registry
app.routers.pipeline -> app.schema
app.routers.pipeline -> app.security
app.routers.pipeline -> app.services.actions
app.routers.pipeline -> app.web
app.routers.retag -> app.security
app.routers.retag -> app.services.actions
app.routers.retag -> app.web
app.routers.tests -> app.security
app.routers.tests -> app.services.actions
app.routers.tests -> app.web
app.routers.wipe -> app.security
app.routers.wipe -> app.services.actions
app.routers.wipe -> app.web
app.security -> app.config
app.security -> app.services.auth
app.serializers -> app.models
app.serializers -> app.schema
app.serializers -> app.services.categories
app.services.actions -> app.categorize
app.services.actions -> app.db
app.services.actions -> app.ingest
app.services.actions -> app.intake
app.services.actions -> app.logging
app.services.actions -> app.registry
app.services.actions -> app.schema
app.services.actions -> app.serializers
app.services.actions -> app.services.approvals
app.services.actions -> app.services.archive
app.services.actions -> app.services.backup
app.services.actions -> app.services.backup_worker
app.services.actions -> app.services.categories
app.services.actions -> app.services.coherence
app.services.actions -> app.services.conflicts
app.services.actions -> app.services.events
app.services.actions -> app.services.images
app.services.actions -> app.services.llm_worker
app.services.actions -> app.services.overseer_worker
app.services.actions -> app.services.pending
app.services.actions -> app.services.retag
app.services.actions -> app.services.scheduler
app.services.actions -> app.services.stats
app.services.actions -> app.services.status
app.services.actions -> app.services.testrunner
app.services.actions -> app.services.wipe
app.services.actions -> app.timeutil
app.services.approvals -> app.db
app.services.approvals -> app.models
app.services.archive -> app.config
app.services.archive -> app.models
app.services.archive -> app.registry
app.services.archive -> app.schema
app.services.archive -> app.services.clock
app.services.archive -> app.services.events
app.services.archive -> app.services.expiry
app.services.archive -> app.services.images
app.services.auth -> app.config
app.services.auth -> app.db
app.services.auth -> app.models
app.services.auth -> app.services.actions
app.services.backup -> app.config
app.services.backup -> app.db
app.services.backup -> app.models
app.services.backup -> app.services.lock
app.services.backup_worker -> app.config
app.services.backup_worker -> app.models
app.services.backup_worker -> app.services.backup
app.services.categories -> app.intake
app.services.clock -> app.config
app.services.clock -> app.models
app.services.clock -> app.timeutil
app.services.coherence -> app.categorize.categorize
app.services.coherence -> app.config
app.services.coherence -> app.intake
app.services.coherence -> app.registry
app.services.coherence -> app.services.categories
app.services.conflicts -> app.db
app.services.conflicts -> app.identity
app.services.conflicts -> app.models
app.services.conflicts -> app.schema
app.services.conflicts -> app.services.deepseek
app.services.conflicts -> app.services.events
app.services.deepseek -> app.config
app.services.events -> app.identity
app.services.events -> app.models
app.services.events -> app.schema
app.services.events -> app.services.categories
app.services.expiry -> app.services.recurrence
app.services.ics -> app.config
app.services.ics -> app.models
app.services.ics -> app.schema
app.services.ics -> app.services.categories
app.services.ics -> app.services.vtimezone
app.services.images -> app.config
app.services.images -> app.models
app.services.images -> app.schema
app.services.images -> app.services.ssrf
app.services.llm -> app.config
app.services.llm -> app.db
app.services.llm -> app.identity
app.services.llm -> app.intake
app.services.llm -> app.models
app.services.llm -> app.schema
app.services.llm -> app.services.approvals
app.services.llm -> app.services.categories
app.services.llm -> app.services.clock
app.services.llm -> app.services.deepseek
app.services.llm -> app.services.recurrence
app.services.llm -> app.timeutil
app.services.llm_worker -> app.config
app.services.llm_worker -> app.db
app.services.llm_worker -> app.models
app.services.llm_worker -> app.services.llm
app.services.llm_worker -> app.services.pending
app.services.lock -> app.config
app.services.overseer -> app.models
app.services.overseer -> app.schema
app.services.overseer -> app.services.approvals
app.services.overseer -> app.services.clock
app.services.overseer -> app.services.deepseek
app.services.overseer -> app.services.events
app.services.overseer_worker -> app.config
app.services.overseer_worker -> app.db
app.services.overseer_worker -> app.models
app.services.overseer_worker -> app.services.events
app.services.overseer_worker -> app.services.overseer
app.services.pending -> app.models
app.services.pending -> app.schema
app.services.pending -> app.services.clock
app.services.pending -> app.services.images
app.services.placeholders -> app.identity
app.services.placeholders -> app.intake
app.services.placeholders -> app.models
app.services.placeholders -> app.schema
app.services.placeholders -> app.services.approvals
app.services.placeholders -> app.services.clock
app.services.placeholders -> app.services.recurrence
app.services.placeholders -> app.timeutil
app.services.recurrence -> app.timeutil
app.services.retag -> app.models
app.services.scheduler -> app.config
app.services.scheduler -> app.ingest
app.services.scheduler -> app.models
app.services.ssrf -> app.config
app.services.stats -> app.config
app.services.stats -> app.models
app.services.stats -> app.registry
app.services.stats -> app.schema
app.services.stats -> app.services.clock
app.services.stats -> app.services.expiry
app.services.stats -> app.services.images
app.services.stats -> app.timeutil
app.services.status -> app.config
app.services.status -> app.models
app.services.wipe -> app.config
app.services.wipe -> app.db
app.services.wipe -> app.services.status
app.sieve -> app.sieve.sieve
app.sieve.sieve -> app.config
app.sieve.sieve -> app.identity
app.sieve.sieve -> app.models
app.sieve.sieve -> app.schema
app.sieve.sieve -> app.services.clock
app.sieve.sieve -> app.services.expiry
app.timeutil -> app.config
tests.conftest -> app.config
tests.conftest -> app.services.auth
tests.test_actions -> app.config
tests.test_actions -> app.intake
tests.test_actions -> app.models
tests.test_actions -> app.schema
tests.test_actions -> app.services.actions
tests.test_api -> app.admin
tests.test_api -> app.config
tests.test_api -> app.db
tests.test_api -> app.gatherers.elfsight.gatherer
tests.test_api -> app.ingest
tests.test_api -> app.intake
tests.test_api -> app.models
tests.test_api -> app.services.actions
tests.test_api -> app.services.auth
tests.test_approvals -> app.admin
tests.test_approvals -> app.models
tests.test_approvals -> app.security
tests.test_approvals -> app.services.approvals
tests.test_archive -> app.config
tests.test_archive -> app.models
tests.test_archive -> app.schema
tests.test_archive -> app.services.archive
tests.test_archive -> app.services.events
tests.test_archive -> app.services.images
tests.test_archive -> app.services.stats
tests.test_audit -> app.audit
tests.test_auth -> app.admin
tests.test_auth -> app.config
tests.test_auth -> app.models
tests.test_auth -> app.security
tests.test_auth -> app.services.actions
tests.test_auth -> app.services.auth
tests.test_backup -> app.config
tests.test_backup -> app.services.backup
tests.test_categories -> app.admin
tests.test_categories -> app.config
tests.test_categories -> app.intake
tests.test_categories -> app.models
tests.test_categories -> app.routers.debug
tests.test_categories -> app.serializers
tests.test_categories -> app.services.categories
tests.test_categories -> app.services.events
tests.test_categories -> app.services.ics
tests.test_categorize -> app.categorize
tests.test_categorize -> app.config
tests.test_categorize -> app.decisionmaker
tests.test_categorize -> app.identity
tests.test_categorize -> app.ingest
tests.test_categorize -> app.intake
tests.test_categorize -> app.models
tests.test_categorize -> app.schema
tests.test_clock -> app.config
tests.test_clock -> app.services.clock
tests.test_coherence -> app.admin
tests.test_coherence -> app.config
tests.test_coherence -> app.routers.debug
tests.test_coherence -> app.services.coherence
tests.test_config -> app.config
tests.test_conflicts -> app.identity
tests.test_conflicts -> app.models
tests.test_conflicts -> app.schema
tests.test_conflicts -> app.services.conflicts
tests.test_conflicts -> app.sieve
tests.test_contract_categorize -> app.categorize.categorize
tests.test_contract_categorize -> app.schema
tests.test_contract_decisionmaker -> app.decisionmaker
tests.test_contract_decisionmaker -> app.decisionmaker.decisionmaker
tests.test_contract_decisionmaker -> app.identity
tests.test_contract_decisionmaker -> app.models
tests.test_contract_decisionmaker -> app.schema
tests.test_contract_gatherer -> app.gatherers
tests.test_contract_gatherer -> app.schema
tests.test_contract_sieve -> app.identity
tests.test_contract_sieve -> app.models
tests.test_contract_sieve -> app.schema
tests.test_contract_sieve -> app.sieve
tests.test_contract_sieve -> app.sieve.sieve
tests.test_db -> app.config
tests.test_db -> app.db
tests.test_db -> app.models
tests.test_debug -> app.admin
tests.test_debug -> app.gatherers.elfsight.gatherer
tests.test_debug -> app.models
tests.test_debug -> app.routers.debug
tests.test_debug -> app.routers.pipeline
tests.test_debug -> app.schema
tests.test_debug -> app.security
tests.test_debug -> app.services.stats
tests.test_decisionmaker -> app.decisionmaker
tests.test_decisionmaker -> app.decisionmaker.decisionmaker
tests.test_decisionmaker -> app.identity
tests.test_decisionmaker -> app.models
tests.test_decisionmaker -> app.schema
tests.test_deepseek -> app.services.deepseek
tests.test_default_location -> app.identity
tests.test_default_location -> app.ingest
tests.test_default_location -> app.models
tests.test_default_location -> app.schema
tests.test_default_location -> app.sieve
tests.test_elfsight -> app.gatherers.base
tests.test_elfsight -> app.gatherers.elfsight.gatherer
tests.test_elfsight -> app.gatherers.errors
tests.test_elfsight -> app.schema
tests.test_error_handling -> app.gatherers.errors
tests.test_error_handling -> app.ingest
tests.test_error_handling -> app.models
tests.test_error_handling -> app.routers.pipeline
tests.test_error_handling -> app.schema
tests.test_error_handling -> app.services.status
tests.test_events -> app.identity
tests.test_events -> app.models
tests.test_events -> app.public
tests.test_events -> app.routers.events
tests.test_events -> app.schema
tests.test_events -> app.serializers
tests.test_events -> app.services.events
tests.test_events -> app.timeutil
tests.test_gatherer_base -> app.gatherers.base
tests.test_gatherer_base -> app.gatherers.errors
tests.test_gatherer_hikerapi -> app.gatherers.errors
tests.test_gatherer_hikerapi -> app.gatherers.hikerapi.gatherer
tests.test_gatherer_hikerapi -> app.schema
tests.test_gatherer_ics -> app.gatherers.base
tests.test_gatherer_ics -> app.gatherers.errors
tests.test_gatherer_ics -> app.gatherers.ics.gatherer
tests.test_gatherer_ics -> app.schema
tests.test_ics -> app.config
tests.test_ics -> app.models
tests.test_ics -> app.public
tests.test_ics -> app.routers.feeds
tests.test_ics -> app.services.ics
tests.test_identity -> app.identity
tests.test_identity -> app.schema
tests.test_images -> app.models
tests.test_images -> app.public
tests.test_images -> app.schema
tests.test_images -> app.services.images
tests.test_ingest -> app.config
tests.test_ingest -> app.gatherers.elfsight.gatherer
tests.test_ingest -> app.identity
tests.test_ingest -> app.ingest
tests.test_ingest -> app.intake
tests.test_ingest -> app.models
tests.test_ingest -> app.registry
tests.test_ingest -> app.schema
tests.test_ingest -> app.services.archive
tests.test_ingest -> app.services.events
tests.test_ingest_route -> app.admin
tests.test_ingest_route -> app.ingest
tests.test_ingest_route -> app.models
tests.test_ingest_route -> app.schema
tests.test_ingest_route -> app.security
tests.test_intake -> app.config
tests.test_intake -> app.intake
tests.test_intake -> app.schema
tests.test_llm -> app.config
tests.test_llm -> app.intake
tests.test_llm -> app.models
tests.test_llm -> app.schema
tests.test_llm -> app.services.deepseek
tests.test_llm -> app.services.llm
tests.test_llm_worker -> app.services.llm_worker
tests.test_lock -> app.config
tests.test_lock -> app.services.lock
tests.test_logging -> app.admin
tests.test_logging -> app.logging
tests.test_overseer -> app.admin
tests.test_overseer -> app.models
tests.test_overseer -> app.security
tests.test_overseer -> app.services.actions
tests.test_overseer -> app.services.approvals
tests.test_overseer -> app.services.overseer
tests.test_overseer -> app.services.overseer_worker
tests.test_pending -> app.config
tests.test_pending -> app.models
tests.test_pending -> app.schema
tests.test_pending -> app.services.pending
tests.test_pipeline -> app.categorize
tests.test_pipeline -> app.config
tests.test_pipeline -> app.decisionmaker
tests.test_pipeline -> app.gatherers.elfsight.gatherer
tests.test_pipeline -> app.ingest
tests.test_pipeline -> app.models
tests.test_pipeline -> app.public
tests.test_pipeline -> app.registry
tests.test_pipeline -> app.routers.events
tests.test_pipeline -> app.routers.feeds
tests.test_pipeline -> app.schema
tests.test_pipeline -> app.sieve
tests.test_pipeline_playground -> app.admin
tests.test_pipeline_playground -> app.gatherers.elfsight.gatherer
tests.test_pipeline_playground -> app.models
tests.test_pipeline_playground -> app.routers.pipeline
tests.test_pipeline_playground -> app.security
tests.test_placeholders -> app.config
tests.test_placeholders -> app.intake
tests.test_placeholders -> app.models
tests.test_placeholders -> app.schema
tests.test_placeholders -> app.services.approvals
tests.test_placeholders -> app.services.placeholders
tests.test_recurrence -> app.services.expiry
tests.test_recurrence -> app.services.recurrence
tests.test_retag -> app.admin
tests.test_retag -> app.models
tests.test_retag -> app.routers.retag
tests.test_retag -> app.security
tests.test_retag -> app.services.retag
tests.test_scheduler -> app.config
tests.test_scheduler -> app.services.scheduler
tests.test_scrub -> app.logging
tests.test_sieve -> app.config
tests.test_sieve -> app.identity
tests.test_sieve -> app.models
tests.test_sieve -> app.schema
tests.test_sieve -> app.sieve
tests.test_ssrf -> app.services.images
tests.test_ssrf -> app.services.ssrf
tests.test_stale -> app.admin
tests.test_stale -> app.config
tests.test_stale -> app.decisionmaker
tests.test_stale -> app.identity
tests.test_stale -> app.ingest
tests.test_stale -> app.models
tests.test_stale -> app.routers.debug
tests.test_stale -> app.schema
tests.test_stale -> app.services.stats
tests.test_stale -> app.sieve
tests.test_status -> app.ingest
tests.test_status -> app.schema
tests.test_status -> app.services.status
tests.test_testrunner -> app.admin
tests.test_testrunner -> app.security
tests.test_testrunner -> app.services.actions
tests.test_testrunner -> app.services.testrunner
tests.test_timeutil -> app.config
tests.test_timeutil -> app.timeutil
tests.test_vtimezone -> app.services.vtimezone
tests.test_wipe -> app.admin
tests.test_wipe -> app.db
tests.test_wipe -> app.ingest
tests.test_wipe -> app.models
tests.test_wipe -> app.public
tests.test_wipe -> app.routers.events
tests.test_wipe -> app.schema
tests.test_wipe -> app.security
tests.test_wipe -> app.services.actions
tests.test_wipe -> app.services.status
tests.test_wipe -> app.services.wipe
```
