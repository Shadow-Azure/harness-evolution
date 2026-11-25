/* This file is generated from packages/contracts/openapi.json. Do not edit. */
/** @generated */

export interface paths {
    "/api/acquisition/pull": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Trigger Pull
         * @description Queue one administrator pull from the configured upstream source.
         */
        post: operations["trigger_pull_api_acquisition_pull_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/acquisition/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Acquisition Status
         * @description Return platform counters and scoped trace and attribution progress.
         */
        get: operations["acquisition_status_api_acquisition_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/acquisition/sync": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Trigger Sync
         * @description Queue one administrator-triggered sync or return explicit no-work.
         */
        post: operations["trigger_sync_api_acquisition_sync_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/app-config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * App Config
         * @description Report the brand resolved from the API environment at startup.
         */
        get: operations["app_config_api_app_config_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/callback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Callback
         * @description Complete an external provider callback without exposing provider details.
         */
        get: operations["callback_api_auth_callback_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/change-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Change Password
         * @description Replace the authenticated user's password and clear forced-change state.
         */
        post: operations["change_password_api_auth_change_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Login
         * @description Exchange a username and password for a short-lived access token.
         */
        post: operations["login_api_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Logout
         * @description Revoke the presented refresh token and clear its restricted cookie.
         */
        post: operations["logout_api_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Me
         * @description Return the current identity with its forced-change state.
         */
        get: operations["me_api_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Refresh
         * @description Rotate the refresh cookie and issue a fresh bearer access token.
         */
        post: operations["refresh_api_auth_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/session": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Session
         * @description Return the current user with every workspace visible to this session.
         */
        get: operations["session_api_auth_session_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/bad-cases/{badCaseId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Bad Case
         * @description Return one problem and optionally enforce deep-link ownership.
         */
        get: operations["get_bad_case_api_bad_cases__badCaseId__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/bad-cases/{badCaseId}/analysis": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Bad Case Analysis
         * @description Return the five-state attribution view, including no-row placeholder.
         */
        get: operations["get_bad_case_analysis_api_bad_cases__badCaseId__analysis_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalogs/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Model Catalog
         * @description Return normalized model usage from visible workspace sessions.
         */
        get: operations["get_model_catalog_api_catalogs_models_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/catalogs/targets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Target Catalog
         * @description Return enabled targets visible to the caller and their remote versions.
         */
        get: operations["get_target_catalog_api_catalogs_targets_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Event Stream
         * @description Consume a one-time ticket and stream replay plus live run notifications.
         */
        get: operations["event_stream_api_events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/events/ticket": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Issue Ticket
         * @description Bind authenticated run topics and a cursor to a single-use ticket.
         */
        post: operations["issue_ticket_api_events_ticket_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/cluster-previews": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Cluster Preview
         * @description Admit a cluster-only preview run in the resolved target workspace.
         */
        post: operations["create_cluster_preview_api_evolution_cluster_previews_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/probes/query": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Query Probe Hits
         * @description Return hit statistics and the first probe page for wizard step 2.
         */
        post: operations["query_probe_hits_api_evolution_probes_query_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Runs
         * @description Return backend-ordered running and history groups in visible spaces.
         */
        get: operations["list_runs_api_evolution_runs_get"];
        put?: never;
        /**
         * Create Run
         * @description Admit one full evolution run for a target in a visible space.
         */
        post: operations["create_run_api_evolution_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Run
         * @description Return one visible run shell with its backend-owned step states.
         */
        get: operations["read_run_api_evolution_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/attribution-jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Attribution Jobs
         * @description Return sanitized attribution throughput and failure observations.
         */
        get: operations["list_attribution_jobs_api_evolution_runs__run_id__attribution_jobs_get"];
        put?: never;
        /**
         * Create Attribution Job
         * @description Start or join the run's manual attribution batch.
         */
        post: operations["create_attribution_job_api_evolution_runs__run_id__attribution_jobs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/attribution-jobs/{job_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Cancel Attribution Job
         * @description Cancel queued or running attribution work without deleting its audit row.
         */
        post: operations["cancel_attribution_job_api_evolution_runs__run_id__attribution_jobs__job_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/attribution-jobs/{job_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Retry Attribution Job
         * @description Retry only cases that still lack a durable report link.
         */
        post: operations["retry_attribution_job_api_evolution_runs__run_id__attribution_jobs__job_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Run Events
         * @description Return one stable, authenticated page of durable run events.
         */
        get: operations["read_run_events_api_evolution_runs__run_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Retry Run
         * @description Admit one manual retry for a blocked run in a visible space.
         */
        post: operations["retry_run_api_evolution_runs__run_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/steps/attribution": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Attribution Step
         * @description Return the backend-owned attribution projection of one run.
         */
        get: operations["read_attribution_step_api_evolution_runs__run_id__steps_attribution_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/steps/clusters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Clusters Step
         * @description Return the backend-owned cluster projection of one run.
         */
        get: operations["read_clusters_step_api_evolution_runs__run_id__steps_clusters_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/steps/final": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Final Step
         * @description Return the backend-owned final evaluation projection of one run.
         */
        get: operations["read_final_step_api_evolution_runs__run_id__steps_final_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/steps/iteration": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Iteration Step
         * @description Return the backend-owned iteration projection of one run.
         */
        get: operations["read_iteration_step_api_evolution_runs__run_id__steps_iteration_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/steps/potential": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Potential Step
         * @description Return one page of potential bad cases for one run.
         */
        get: operations["read_potential_step_api_evolution_runs__run_id__steps_potential_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/steps/range": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Range Step
         * @description Return the backend-owned selection snapshot of one run.
         */
        get: operations["read_range_step_api_evolution_runs__run_id__steps_range_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/runs/{run_id}/steps/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Sessions Step
         * @description Return one page of associated Sessions for one run.
         */
        get: operations["read_sessions_step_api_evolution_runs__run_id__steps_sessions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/targets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Targets
         * @description Return targets visible to the caller, including disabled rows.
         */
        get: operations["list_targets_api_evolution_targets_get"];
        put?: never;
        /**
         * Create Target
         * @description Validate and create one target in the legacy default workspace.
         */
        post: operations["create_target_api_evolution_targets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/targets/{targetId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Target
         * @description Replace one target's editable fields after remote validation.
         */
        put: operations["update_target_api_evolution_targets__targetId__put"];
        post?: never;
        /**
         * Delete Target
         * @description Delete one unused target.
         */
        delete: operations["delete_target_api_evolution_targets__targetId__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evolution/targets/{targetId}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Target Versions
         * @description Return sorted tags and the target's default reference.
         */
        get: operations["list_target_versions_api_evolution_targets__targetId__versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Report API reachability, delivery phase, database and data-directory health.
         */
        get: operations["health_api_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/jobs/{jobId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Job
         * @description Return the latest durable state for one job.
         */
        get: operations["get_job_api_jobs__jobId__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/probes/{probeId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Probe
         * @description Return one validated root-cause report.
         */
        get: operations["get_probe_api_probes__probeId__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Sessions
         * @description Return the current page of root-session cards.
         */
        get: operations["list_sessions_api_sessions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions/{sessionId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Session
         * @description Return one session overview card.
         */
        get: operations["get_session_api_sessions__sessionId__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions/{sessionId}/bad-cases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Session Bad Cases
         * @description Return one Session's problems in external creation order.
         */
        get: operations["list_session_bad_cases_api_sessions__sessionId__bad_cases_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions/{sessionId}/probes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Session Probes
         * @description Return every root-cause report owned by one Session.
         */
        get: operations["list_session_probes_api_sessions__sessionId__probes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions/{sessionId}/tree": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Session Tree
         * @description Return the flat canonical Agent tree and anchored problem cards.
         */
        get: operations["get_session_tree_api_sessions__sessionId__tree_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Users
         * @description List all users in the single organization.
         */
        get: operations["list_users_api_users_get"];
        put?: never;
        /**
         * Create User
         * @description Provision a user whose first login must change its temporary password.
         */
        post: operations["create_user_api_users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Workspaces
         * @description Return every workspace visible to the current user.
         */
        get: operations["list_workspaces_api_workspaces_get"];
        put?: never;
        /**
         * Create Workspace
         * @description Create one workspace with at least one existing space administrator.
         */
        post: operations["create_workspace_api_workspaces_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Workspace
         * @description Update the workspace fields permitted for the caller's effective role.
         */
        put: operations["update_workspace_api_workspaces__wid__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/attribution-skill-packages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Attribution Skill Packages
         * @description List the built-in package and workspace uploads.
         */
        get: operations["list_attribution_skill_packages_api_workspaces__wid__attribution_skill_packages_get"];
        put?: never;
        /**
         * Upload Attribution Skill Package
         * @description Validate and store one custom Skill folder ZIP without activating it.
         */
        post: operations["upload_attribution_skill_package_api_workspaces__wid__attribution_skill_packages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/attribution-skill-packages/{packageId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Package Detail
         * @description Return the selected package prompt, file paths and target bindings.
         */
        get: operations["get_package_detail_api_workspaces__wid__attribution_skill_packages__packageId__get"];
        put?: never;
        post?: never;
        /**
         * Delete Attribution Skill Package
         * @description Remove a custom package that has no target bindings.
         */
        delete: operations["delete_attribution_skill_package_api_workspaces__wid__attribution_skill_packages__packageId__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/attribution-skill-packages/{packageId}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download Attribution Skill Package
         * @description Download a regenerated ZIP without exposing server filesystem paths.
         */
        get: operations["download_attribution_skill_package_api_workspaces__wid__attribution_skill_packages__packageId__download_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/bad-case-labels": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Bad Case Labels
         * @description Return the public badcase labels accepted by this workspace.
         */
        get: operations["get_bad_case_labels_api_workspaces__wid__bad_case_labels_get"];
        /**
         * Replace Bad Case Labels
         * @description Replace label rules and historical catalog assignments atomically.
         */
        put: operations["replace_bad_case_labels_api_workspaces__wid__bad_case_labels_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/bad-cases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Workspace Bad Cases
         * @description Return one filtered page of this workspace's reported cases.
         */
        get: operations["list_workspace_bad_cases_api_workspaces__wid__bad_cases_get"];
        put?: never;
        /**
         * Report one bad case with a workspace credential
         * @description Upsert one reported bad case as the workspace resolved from URL and credential.
         *
         *     Authentication is a workspace ingest credential
         *     (`Authorization: Bearer whk_…`), not the browser access token. The body may
         *     never carry workspace identity: the workspace comes from the URL, and the
         *     credential must belong to it. A new `badCaseId` answers `201`; re-reporting
         *     an id already owned by this workspace replaces its upstream fields and
         *     answers `200` without consuming quota.
         */
        post: operations["ingest_bad_case_api_workspaces__wid__bad_cases_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/bad-cases/{badCaseId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Workspace Bad Case
         * @description Return one problem only when it belongs to this workspace.
         */
        get: operations["get_workspace_bad_case_api_workspaces__wid__bad_cases__badCaseId__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/bad-cases/{badCaseId}/attributions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Workspace Case Attributions
         * @description Return one problem's attributions newest first, two per page by default.
         */
        get: operations["list_workspace_case_attributions_api_workspaces__wid__bad_cases__badCaseId__attributions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/bad-cases/{badCaseId}/attributions/{attributionId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Workspace Case Attribution
         * @description Return one attribution only while it is linked to the requested problem.
         */
        get: operations["get_workspace_case_attribution_api_workspaces__wid__bad_cases__badCaseId__attributions__attributionId__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/catalogs/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Model Catalog
         * @description Return model usage projected from this workspace's sessions.
         */
        get: operations["read_model_catalog_api_workspaces__wid__catalogs_models_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/catalogs/targets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Target Catalog
         * @description Return enabled targets owned by this workspace with remote versions.
         */
        get: operations["read_target_catalog_api_workspaces__wid__catalogs_targets_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/credentials": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Credentials
         * @description Return every credential row, including revoked ones, without plaintext.
         */
        get: operations["list_credentials_api_workspaces__wid__credentials_get"];
        put?: never;
        /**
         * Create Credential
         * @description Mint one credential and return its plaintext exactly once.
         */
        post: operations["create_credential_api_workspaces__wid__credentials_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/credentials/{cid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Revoke Credential
         * @description Revoke one credential; retries stay idempotent.
         */
        delete: operations["revoke_credential_api_workspaces__wid__credentials__cid__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/attribution-skill-bindings/default": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Bind Workspace Default Skill
         * @description Set the workspace fallback revision.
         */
        put: operations["bind_workspace_default_skill_api_workspaces__wid__evolution_attribution_skill_bindings_default_put"];
        post?: never;
        /**
         * Unbind Workspace Default Skill
         * @description Remove the workspace fallback and restore the platform default.
         */
        delete: operations["unbind_workspace_default_skill_api_workspaces__wid__evolution_attribution_skill_bindings_default_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/attribution-skill-bindings/default/rollback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Rollback Workspace Default Skill
         * @description Restore the prior eligible revision or the protected platform rule.
         */
        post: operations["rollback_workspace_default_skill_api_workspaces__wid__evolution_attribution_skill_bindings_default_rollback_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/attribution-skills": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Attribution Skills
         * @description List bindable package IDs in agent mode or registry revision IDs in rule mode.
         */
        get: operations["list_attribution_skills_api_workspaces__wid__evolution_attribution_skills_get"];
        put?: never;
        /**
         * Create Attribution Skill
         * @description Create a workspace Skill and publish revision one.
         */
        post: operations["create_attribution_skill_api_workspaces__wid__evolution_attribution_skills_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/attribution-skills/revisions/{revisionId}/quality-decisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Decide Attribution Skill Quality
         * @description Accept or reject one revision using an exact persisted evaluation.
         */
        post: operations["decide_attribution_skill_quality_api_workspaces__wid__evolution_attribution_skills_revisions__revisionId__quality_decisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/attribution-skills/revisions/{revisionId}/quality-events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Attribution Skill Quality Events
         * @description Return the immutable evaluation and human-decision audit trail.
         */
        get: operations["list_attribution_skill_quality_events_api_workspaces__wid__evolution_attribution_skills_revisions__revisionId__quality_events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/attribution-skills/revisions/{revisionId}/shadow-evaluations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Evaluate Attribution Skill Revision
         * @description Evaluate a revision against sanitized Golden Cases without production writes.
         */
        post: operations["evaluate_attribution_skill_revision_api_workspaces__wid__evolution_attribution_skills_revisions__revisionId__shadow_evaluations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/attribution-skills/{skillId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Set Attribution Skill State
         * @description Enable or disable a workspace Skill for future resolution.
         */
        patch: operations["set_attribution_skill_state_api_workspaces__wid__evolution_attribution_skills__skillId__patch"];
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/attribution-skills/{skillId}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Publish Attribution Skill Revision
         * @description Append a published immutable revision to a workspace Skill.
         */
        post: operations["publish_attribution_skill_revision_api_workspaces__wid__evolution_attribution_skills__skillId__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/cluster-previews": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Cluster Preview
         * @description Admit one cluster-only preview run owned by this workspace.
         */
        post: operations["create_cluster_preview_api_workspaces__wid__evolution_cluster_previews_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/preview/attribution": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Preview Attribution
         * @description Return cache reuse counts without executing attribution.
         */
        post: operations["preview_attribution_api_workspaces__wid__evolution_preview_attribution_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/preview/potential": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Preview Potential
         * @description Return one page of policy-included potential cases.
         */
        post: operations["preview_potential_api_workspaces__wid__evolution_preview_potential_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/preview/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Preview Sessions
         * @description Return one page of Sessions whose trace contains the target version.
         */
        post: operations["preview_sessions_api_workspaces__wid__evolution_preview_sessions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Runs
         * @description Return backend-ordered running and history groups for this workspace.
         */
        get: operations["list_runs_api_workspaces__wid__evolution_runs_get"];
        put?: never;
        /**
         * Create Run
         * @description Admit one full evolution run owned by this workspace.
         */
        post: operations["create_run_api_workspaces__wid__evolution_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Run
         * @description Return one run shell owned by this workspace.
         */
        get: operations["read_run_api_workspaces__wid__evolution_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/runs/{run_id}/attribution-jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Attribution Jobs
         * @description Return sanitized attribution observations for one workspace run.
         */
        get: operations["list_attribution_jobs_api_workspaces__wid__evolution_runs__run_id__attribution_jobs_get"];
        put?: never;
        /**
         * Create Attribution Job
         * @description Start or join one manual attribution batch.
         */
        post: operations["create_attribution_job_api_workspaces__wid__evolution_runs__run_id__attribution_jobs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/runs/{run_id}/attribution-jobs/{job_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Cancel Attribution Job
         * @description Cancel queued or running attribution work and retain its audit row.
         */
        post: operations["cancel_attribution_job_api_workspaces__wid__evolution_runs__run_id__attribution_jobs__job_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/runs/{run_id}/attribution-jobs/{job_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Retry Attribution Job
         * @description Retry only unfinished cases of one failed attribution batch.
         */
        post: operations["retry_attribution_job_api_workspaces__wid__evolution_runs__run_id__attribution_jobs__job_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/runs/{run_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Run Events
         * @description Return one stable event page of a run owned by this workspace.
         */
        get: operations["read_run_events_api_workspaces__wid__evolution_runs__run_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/runs/{run_id}/pause": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Pause Run
         * @description Request a cooperative pause at the next durable checkpoint.
         */
        post: operations["pause_run_api_workspaces__wid__evolution_runs__run_id__pause_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/runs/{run_id}/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resume Run
         * @description Release a user pause and admit the first unfinished operation.
         */
        post: operations["resume_run_api_workspaces__wid__evolution_runs__run_id__resume_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/runs/{run_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Retry Run
         * @description Admit one manual retry for a blocked run owned by this workspace.
         */
        post: operations["retry_run_api_workspaces__wid__evolution_runs__run_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/runs/{run_id}/steps/{key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Step
         * @description Return one backend-owned step of a run owned by this workspace.
         */
        get: operations["read_step_api_workspaces__wid__evolution_runs__run_id__steps__key__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/targets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Targets
         * @description Return every configured target in this workspace.
         */
        get: operations["list_targets_api_workspaces__wid__evolution_targets_get"];
        put?: never;
        /**
         * Create Target
         * @description Validate and create one target owned by this workspace.
         */
        post: operations["create_target_api_workspaces__wid__evolution_targets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/targets/{targetId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Target
         * @description Replace one target owned by this workspace.
         */
        put: operations["update_target_api_workspaces__wid__evolution_targets__targetId__put"];
        post?: never;
        /**
         * Delete Target
         * @description Delete one unused target owned by this workspace.
         */
        delete: operations["delete_target_api_workspaces__wid__evolution_targets__targetId__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/targets/{targetId}/attribution-skill": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Resolve Target Attribution Skill
         * @description Resolve the immutable revision currently effective for one target.
         */
        get: operations["resolve_target_attribution_skill_api_workspaces__wid__evolution_targets__targetId__attribution_skill_get"];
        /**
         * Bind Target Attribution Skill
         * @description Set a target-level Skill override.
         */
        put: operations["bind_target_attribution_skill_api_workspaces__wid__evolution_targets__targetId__attribution_skill_put"];
        post?: never;
        /**
         * Unbind Target Attribution Skill
         * @description Remove a legacy rule override; agent-mode targets always have an explicit binding.
         */
        delete: operations["unbind_target_attribution_skill_api_workspaces__wid__evolution_targets__targetId__attribution_skill_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/evolution/targets/{targetId}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Versions
         * @description Return sorted remote tags for one workspace target.
         */
        get: operations["read_versions_api_workspaces__wid__evolution_targets__targetId__versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/member-candidates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Member Candidates
         * @description Search non-member users without exposing the global user directory.
         */
        get: operations["list_member_candidates_api_workspaces__wid__member_candidates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/members": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Members
         * @description Return the member table in role and join-time order.
         */
        get: operations["list_members_api_workspaces__wid__members_get"];
        put?: never;
        /**
         * Add Member
         * @description Add one existing user to the workspace.
         */
        post: operations["add_member_api_workspaces__wid__members_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/members/self-admin": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Appoint Self As Space Admin
         * @description Write an idempotent real space-admin row for the global administrator.
         */
        post: operations["appoint_self_as_space_admin_api_workspaces__wid__members_self_admin_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/members/{userId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Member
         * @description Change one workspace member's role.
         */
        put: operations["update_member_api_workspaces__wid__members__userId__put"];
        post?: never;
        /**
         * Remove Member
         * @description Remove one workspace member while preserving a space administrator.
         */
        delete: operations["remove_member_api_workspaces__wid__members__userId__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/overview/sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Overview Sources
         * @description Return the per-object distribution, sorted by total then object name.
         */
        get: operations["get_overview_sources_api_workspaces__wid__overview_sources_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/overview/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Overview Summary
         * @description Return this workspace's overview totals, object options, and quota usage.
         */
        get: operations["get_overview_summary_api_workspaces__wid__overview_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/overview/targets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Overview Targets
         * @description Return target summary totals and one evolvable-sorted page.
         */
        get: operations["get_overview_targets_api_workspaces__wid__overview_targets_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/overview/targets/cases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Overview Target Cases
         * @description Return one filtered page of potential cases under their target versions.
         */
        get: operations["get_overview_target_cases_api_workspaces__wid__overview_targets_cases_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/overview/targets/trend": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Overview Targets Trend
         * @description Return the selected targets' three-state trend, zero-filled per bucket.
         */
        get: operations["get_overview_targets_trend_api_workspaces__wid__overview_targets_trend_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/overview/targets/{targetId}/detail": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Overview Target Detail
         * @description Return one target's independent version and source analysis.
         */
        get: operations["get_overview_target_detail_api_workspaces__wid__overview_targets__targetId__detail_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/overview/trend": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Overview Trend
         * @description Return the continuous self/discovery trend and its effective grain.
         */
        get: operations["get_overview_trend_api_workspaces__wid__overview_trend_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Workspace Sessions
         * @description Return the root sessions projected from one workspace's bad cases.
         */
        get: operations["list_workspace_sessions_api_workspaces__wid__sessions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/sessions/{sessionId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Workspace Session
         * @description Return one session card only when the workspace projected it.
         */
        get: operations["get_workspace_session_api_workspaces__wid__sessions__sessionId__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/sessions/{sessionId}/bad-cases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Workspace Session Bad Cases
         * @description Return only this workspace's problems for one projected Session.
         */
        get: operations["list_workspace_session_bad_cases_api_workspaces__wid__sessions__sessionId__bad_cases_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/workspaces/{wid}/sessions/{sessionId}/tree": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Workspace Session Tree
         * @description Return one workspace-projected tree with only this workspace's cases.
         */
        get: operations["get_workspace_session_tree_api_workspaces__wid__sessions__sessionId__tree_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AcquisitionStatusResponse
         * @description Current acquisition counts and durable latest-run metadata.
         */
        AcquisitionStatusResponse: {
            /** Activejobid */
            activeJobId: string | null;
            badCaseAnalysis: components["schemas"]["BadCaseAnalysisSummary"];
            badCaseCatalogSync: components["schemas"]["BadCaseCatalogSyncSummary"];
            badCaseSync: components["schemas"]["BadCaseSyncSummary"];
            /** Errors */
            errors: components["schemas"]["SyncStatusError"][];
            /** Imported */
            imported: number;
            /** Lastrunat */
            lastRunAt: string | null;
            /** Nextrunat */
            nextRunAt: string | null;
            /**
             * Payloadtable
             * @default trajectory_payloads
             */
            payloadTable: string;
            /** Pending */
            pending: number;
            /** Processed */
            processed: number;
            /** Skipped */
            skipped: number;
            /**
             * Status
             * @enum {string}
             */
            status: "idle" | "queued" | "running" | "completed" | "failed" | "interrupted";
        };
        /**
         * AppConfigBrand
         * @description Deployment brand name and subtitle exposed to every visitor.
         */
        AppConfigBrand: {
            /** Name */
            name: string;
            /** Subtitle */
            subtitle: string;
        };
        /**
         * AppConfigResponse
         * @description Public runtime configuration shared by the login page and the shell.
         */
        AppConfigResponse: {
            brand: components["schemas"]["AppConfigBrand"];
        };
        /**
         * AttributeStats
         * @description Probe counts by attribution type shown in the wizard distribution bar.
         */
        AttributeStats: {
            /**
             * Context
             * @default 0
             */
            context: number;
            /**
             * Error
             * @default 0
             */
            error: number;
            /**
             * Flow
             * @default 0
             */
            flow: number;
            /**
             * Model
             * @default 0
             */
            model: number;
            /**
             * Nonissue
             * @default 0
             */
            nonIssue: number;
            /**
             * Prompt
             * @default 0
             */
            prompt: number;
        };
        /**
         * AttributionAnalysis
         * @description Human-readable summary and detailed reasoning produced by the engine.
         */
        AttributionAnalysis: {
            /** Reasoning */
            reasoning: string;
            /** Summary */
            summary: string;
        };
        /**
         * AttributionDetail
         * @description One attribution with its reasoning, evidence warnings, and trigger compare.
         */
        AttributionDetail: {
            /** Attributionengine */
            attributionEngine: string;
            /** Attributionid */
            attributionId: string;
            /** Badcaseid */
            badCaseId: string;
            /** Category */
            category: ("model" | "prompt" | "error" | "flow" | "context") | null;
            /**
             * Conclusion
             * @enum {string}
             */
            conclusion: "attributed" | "non_target" | "inconclusive";
            /** Confidence */
            confidence: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            executionManifest?: components["schemas"]["AttributionExecutionManifest"] | null;
            /** Executionmanifesthash */
            executionManifestHash?: string | null;
            /** Iscached */
            isCached: boolean;
            /** Objectcommit */
            objectCommit?: string | null;
            /** Objectname */
            objectName: string;
            /** Objectref */
            objectRef?: string | null;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent" | "knowledge";
            /** Objectversion */
            objectVersion?: string | null;
            /** Policyversion */
            policyVersion: string;
            /** Reason */
            reason: string;
            /** Reasoning */
            reasoning: string;
            report?: components["schemas"]["AttributionReportV2"] | null;
            /** Reportschemaversion */
            reportSchemaVersion?: string | null;
            /** Reusedcount */
            reusedCount: number;
            /** Runid */
            runId?: string | null;
            triggerCompare: components["schemas"]["AttributionTriggerCompare"];
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Warnings */
            warnings: components["schemas"]["AttributionWarning"][];
        };
        /**
         * AttributionEvidence
         * @description One structured, non-raw evidence reference used by the analysis.
         */
        AttributionEvidence: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "bad_case" | "knowledge" | "trace" | "warning";
            /** Reference */
            reference?: string | null;
            /** Summary */
            summary: string;
        };
        /**
         * AttributionExecutionManifest
         * @description Immutable inputs that determine one attribution report and cache identity.
         */
        AttributionExecutionManifest: {
            /** Badcaseid */
            badCaseId: string;
            /** Contextsnapshothash */
            contextSnapshotHash: string;
            /** Engine */
            engine: string;
            /**
             * Manifestversion
             * @default attribution-execution/v1
             * @constant
             */
            manifestVersion: "attribution-execution/v1";
            /** Modelconfigfingerprint */
            modelConfigFingerprint: string;
            /**
             * Outputschemaversion
             * @default probe-report/v2
             * @constant
             */
            outputSchemaVersion: "probe-report/v2";
            /** Policyversion */
            policyVersion: string;
            skill: components["schemas"]["app__service__evolution__attribution_contracts__AttributionSkillRevision"];
            target: components["schemas"]["AttributionTargetRef"];
            /** Workspaceid */
            workspaceId: string;
        };
        /**
         * AttributionItem
         * @description One object/revision-scoped attribution shown in the error-detail list.
         *
         *     ``attributionId`` is the stable deep-link id and maps ``probe_reports.probe_id``;
         *     ``runId`` prefers the last run that reused the conclusion so a deep link
         *     opens the run that produced the currently displayed row. ``objectRef`` and
         *     ``objectCommit`` are display-only evidence from that run; clients fall back
         *     to ``objectVersion`` when they are absent.
         */
        AttributionItem: {
            /** Attributionid */
            attributionId: string;
            /** Badcaseid */
            badCaseId: string;
            /** Category */
            category: ("model" | "prompt" | "error" | "flow" | "context") | null;
            /**
             * Conclusion
             * @enum {string}
             */
            conclusion: "attributed" | "non_target" | "inconclusive";
            /** Confidence */
            confidence: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Iscached */
            isCached: boolean;
            /** Objectcommit */
            objectCommit?: string | null;
            /** Objectname */
            objectName: string;
            /** Objectref */
            objectRef?: string | null;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent" | "knowledge";
            /** Objectversion */
            objectVersion?: string | null;
            /** Reusedcount */
            reusedCount: number;
            /** Runid */
            runId?: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /**
         * AttributionJobList
         * @description Newest-first attribution executions for one run.
         */
        AttributionJobList: {
            /** Items */
            items: components["schemas"]["AttributionJobView"][];
        };
        /**
         * AttributionJobObservation
         * @description Sanitized throughput, quality, cost, and runtime observations.
         */
        AttributionJobObservation: {
            /**
             * Averagelatencyms
             * @default 0
             */
            averageLatencyMs: number;
            /**
             * Completed
             * @default 0
             */
            completed: number;
            /** Contexthash */
            contextHash?: string | null;
            /**
             * Created
             * @default 0
             */
            created: number;
            /**
             * Evidencecoveragerate
             * @default 0
             */
            evidenceCoverageRate: number;
            /** Executor */
            executor: string;
            /**
             * Failed
             * @default 0
             */
            failed: number;
            /**
             * Nontarget
             * @default 0
             */
            nonTarget: number;
            /**
             * P95Latencyms
             * @default 0
             */
            p95LatencyMs: number;
            /**
             * Reused
             * @default 0
             */
            reused: number;
            /** Skillrevision */
            skillRevision: string | null;
            /**
             * Tokencount
             * @default 0
             */
            tokenCount: number | null;
            /**
             * Total
             * @default 0
             */
            total: number;
            /**
             * Warningcount
             * @default 0
             */
            warningCount: number;
        };
        /**
         * AttributionJobView
         * @description One durable attribution execution without raw trace or Skill content.
         */
        AttributionJobView: {
            /** Attempt */
            attempt: number;
            /** Cancelrequested */
            cancelRequested: boolean;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Error */
            error: string | null;
            /** Finishedat */
            finishedAt: string | null;
            /** Jobid */
            jobId: string;
            /** Maxattempts */
            maxAttempts: number;
            observation: components["schemas"]["AttributionJobObservation"];
            /** Progress */
            progress: number;
            /** Runid */
            runId: string;
            /**
             * Source
             * @enum {string}
             */
            source: "prepare" | "manual" | "schedule" | "retry";
            /** Startedat */
            startedAt: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "running" | "completed" | "failed" | "interrupted" | "cancelled";
        };
        /**
         * AttributionPage
         * @description One deterministic newest-first page of a case's attributions.
         */
        AttributionPage: {
            /** Items */
            items: components["schemas"]["AttributionItem"][];
            /** Page */
            page: number;
            /** Pagesize */
            pageSize: number;
            /** Total */
            total: number;
        };
        /**
         * AttributionPoint
         * @description A bounded introduction or detection point in the selected Session.
         */
        AttributionPoint: {
            /** Label */
            label: string;
            /** Occurredat */
            occurredAt?: string | null;
        };
        /**
         * AttributionPreviewRequest
         * @description Attribution stage condition; preview never executes an engine.
         */
        AttributionPreviewRequest: {
            /**
             * Cacheenabled
             * @default true
             */
            cacheEnabled: boolean;
            /** From */
            from?: string | null;
            policy?: components["schemas"]["PotentialPolicy"] | null;
            /** Targetname */
            targetName: string;
            /**
             * Targettype
             * @enum {string}
             */
            targetType: "skill" | "agent" | "knowledge";
            /** Targetversion */
            targetVersion?: string | null;
            /** To */
            to?: string | null;
        };
        /**
         * AttributionPreviewResult
         * @description Read-only counts and whether this deployment can run workspace Skill packages.
         */
        AttributionPreviewResult: {
            /** Canrecompute */
            canRecompute: boolean;
            summary: components["schemas"]["AttributionPreviewSummary"];
            /** Targetrevision */
            targetRevision?: string | null;
            /** Usesboundskill */
            usesBoundSkill: boolean;
        };
        /**
         * AttributionPreviewSummary
         * @description Cache reuse preview and the historical non-target reference count.
         */
        AttributionPreviewSummary: {
            /** Byskill */
            bySkill?: {
                [key: string]: number;
            };
            /** Fresh */
            fresh: number | null;
            /**
             * Missing
             * @default 0
             */
            missing: number;
            /** Nontargetknown */
            nonTargetKnown: number;
            /** Potential */
            potential: number;
            /** Reused */
            reused: number | null;
        };
        /**
         * AttributionQualityDecisionWrite
         * @description Human acceptance or rejection of one exact shadow evaluation.
         */
        AttributionQualityDecisionWrite: {
            /**
             * Decision
             * @enum {string}
             */
            decision: "accept" | "reject";
            /** Evaluationeventid */
            evaluationEventId: string;
            /** Reason */
            reason: string;
        };
        /**
         * AttributionQualityEvaluation
         * @description One persisted isolated shadow report and its audit identity.
         */
        AttributionQualityEvaluation: {
            /** Actorid */
            actorId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            report: components["schemas"]["ShadowEvaluationReport"];
            /** Skillrevisionid */
            skillRevisionId: string;
        };
        /**
         * AttributionQualityEvent
         * @description Append-only evaluation, promotion, rejection, or rollback evidence.
         */
        AttributionQualityEvent: {
            /** Actorid */
            actorId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Evaluationhash */
            evaluationHash: string | null;
            /** Eventtype */
            eventType: string;
            /** Id */
            id: string;
            /** Payload */
            payload: {
                [key: string]: unknown;
            };
            /** Reason */
            reason: string;
            /** Skillrevisionid */
            skillRevisionId: string;
        };
        /**
         * AttributionQualityHistory
         * @description Ordered quality audit trail for one revision.
         */
        AttributionQualityHistory: {
            /** Items */
            items: components["schemas"]["AttributionQualityEvent"][];
        };
        /**
         * AttributionReportV2
         * @description Structured V2 payload stored beside legacy report text columns.
         */
        AttributionReportV2: {
            analysis: components["schemas"]["AttributionAnalysis"];
            /** Category */
            category?: ("model" | "prompt" | "error" | "flow" | "context") | null;
            /**
             * Conclusion
             * @enum {string}
             */
            conclusion: "attributed" | "non_target" | "inconclusive";
            detectionPoint?: components["schemas"]["AttributionPoint"] | null;
            /** Evidence */
            evidence?: components["schemas"]["AttributionEvidence"][];
            introductionPoint?: components["schemas"]["AttributionPoint"] | null;
            /**
             * Schemaversion
             * @default probe-report/v2
             * @constant
             */
            schemaVersion: "probe-report/v2";
            /** Sourcereport */
            sourceReport?: {
                [key: string]: unknown;
            } | null;
            /** Suggestionclues */
            suggestionClues?: string[];
            target: components["schemas"]["AttributionTargetRef"];
            /** Warnings */
            warnings?: string[];
        };
        /**
         * AttributionRollbackWrite
         * @description Human reason attached to a workspace-default rollback.
         */
        AttributionRollbackWrite: {
            /** Reason */
            reason: string;
        };
        /**
         * AttributionSkillBindingWrite
         * @description Select one published immutable revision for a binding.
         */
        AttributionSkillBindingWrite: {
            /** Skillrevisionid */
            skillRevisionId: string;
        };
        /**
         * AttributionSkillCreate
         * @description Create one Skill and publish its first revision.
         */
        AttributionSkillCreate: {
            /** Content */
            content: {
                [key: string]: unknown;
            };
            /**
             * Description
             * @default
             */
            description: string;
            /** Displayname */
            displayName: string;
            /**
             * Executortype
             * @default agent_stub
             * @enum {string}
             */
            executorType: "builtin_rule" | "agent_stub" | "agent";
            /**
             * Outputschemaversion
             * @default probe-report/v2
             */
            outputSchemaVersion: string;
            /** Skillkey */
            skillKey: string;
        };
        /**
         * AttributionSkillList
         * @description All platform and workspace Skill revisions visible in one workspace.
         */
        AttributionSkillList: {
            /** Items */
            items: components["schemas"]["app__service__evolution__attribution_skills__AttributionSkillRevision"][];
        };
        /**
         * AttributionSkillPackage
         * @description Package metadata rendered by workspace administration.
         */
        AttributionSkillPackage: {
            /** Archivename */
            archiveName: string;
            /** Builtin */
            builtIn: boolean;
            /** Contenthash */
            contentHash: string;
            /** Filecount */
            fileCount: number;
            /** Id */
            id: string;
            /** Sizebytes */
            sizeBytes: number;
            /** Skillname */
            skillName: string;
            /** Uploadedat */
            uploadedAt: string | null;
            /** Uploadername */
            uploaderName: string;
        };
        /**
         * AttributionSkillPackageList
         * @description Workspace resources available for binding and one-off analysis.
         */
        AttributionSkillPackageList: {
            /** Items */
            items: components["schemas"]["AttributionSkillPackage"][];
            /** Runtimeenabled */
            runtimeEnabled: boolean;
        };
        /**
         * AttributionSkillRevisionWrite
         * @description Content and compatibility metadata for one immutable revision.
         */
        AttributionSkillRevisionWrite: {
            /** Content */
            content: {
                [key: string]: unknown;
            };
            /**
             * Executortype
             * @default agent_stub
             * @enum {string}
             */
            executorType: "builtin_rule" | "agent_stub" | "agent";
            /**
             * Outputschemaversion
             * @default probe-report/v2
             */
            outputSchemaVersion: string;
        };
        /**
         * AttributionSkillStateWrite
         * @description Enable or disable a workspace-owned Skill.
         */
        AttributionSkillStateWrite: {
            /** Enabled */
            enabled: boolean;
        };
        /**
         * AttributionTargetRef
         * @description The exact evolution object revision evaluated by one report.
         */
        AttributionTargetRef: {
            /** Objectname */
            objectName: string;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent" | "knowledge";
            /** Objectversion */
            objectVersion?: string | null;
        };
        /**
         * AttributionTriggerCompare
         * @description Trigger-point comparison for one attribution detail.
         *
         *     ``order`` compares the case trigger against the object entry point; a
         *     missing or incomparable anchor stays ``unknown``. ``versionState`` is
         *     ``unknown`` when the attribution has no pinned object version, so clients
         *     must not present it as an exact revision hit.
         */
        AttributionTriggerCompare: {
            /** Casetriggerat */
            caseTriggerAt: string | null;
            /** Objecttriggerat */
            objectTriggerAt: string | null;
            /**
             * Order
             * @enum {string}
             */
            order: "before" | "after" | "same" | "unknown";
            /**
             * Versionstate
             * @enum {string}
             */
            versionState: "exact" | "unknown";
        };
        /**
         * AttributionWarning
         * @description One fixed, non-sensitive evidence gap on an attribution detail.
         */
        AttributionWarning: {
            /** Code */
            code: string;
            /** Message */
            message: string;
        };
        /**
         * BadCase
         * @description Complete public problem card used by list and detail routes.
         *
         *     ``title`` is the short display title and ``reason`` the description body;
         *     ``reason`` maps from the ``bad_cases.bad_case_description`` column.
         */
        BadCase: {
            analysis: components["schemas"]["BadCaseAnalysis"];
            anchor: components["schemas"]["BadCaseAnchor"];
            /**
             * Attributioncount
             * @description Distinct (probeType, probeObject, objectVersion) attributions reached through bad_case_analysis; the canonical definition is 06 §4.2.1.
             */
            attributionCount: number;
            badCaseAgent: components["schemas"]["BadCaseAgent"];
            /** Badcaseid */
            badCaseId: string;
            /**
             * Badcasetype
             * @enum {string}
             */
            badCaseType: "self" | "discovery";
            /**
             * Degraded
             * @default false
             */
            degraded: boolean;
            /** Diagnosticcode */
            diagnosticCode?: string | null;
            /** Hasattribution */
            hasAttribution: boolean;
            /** Metadata */
            metaData: {
                [key: string]: unknown;
            } | null;
            /** Objectname */
            objectName: string;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent";
            /** Objectversion */
            objectVersion: string | null;
            /** Reason */
            reason: string;
            /** Sessionid */
            sessionId: string;
            /** Sessiontitle */
            sessionTitle: string;
            /** Title */
            title: string;
        };
        /**
         * BadCaseAgent
         * @description The reporter that originally supplied a problem report.
         */
        BadCaseAgent: {
            /** Agentid */
            agentId: string | null;
            /** Sessionid */
            sessionId: string;
        };
        /**
         * BadCaseAnalysis
         * @description One of the three status-specific public attribution states.
         */
        BadCaseAnalysis: components["schemas"]["UnanalyzedBadCaseAnalysis"] | components["schemas"]["NonIssueBadCaseAnalysis"] | components["schemas"]["IssueBadCaseAnalysis"];
        /**
         * BadCaseAnalysisSummary
         * @description Read-only attribution progress for the top-nav popover.
         */
        BadCaseAnalysisSummary: {
            /** Analyzed */
            analyzed: number;
            /** Issue */
            issue: number;
            /** Nonissue */
            nonIssue: number;
            /** Pending */
            pending: number;
            /** Total */
            total: number;
        };
        /**
         * BadCaseAnchor
         * @description Stable host Agent, event index, and anchor kind for one problem card.
         */
        BadCaseAnchor: {
            /** Agentid */
            agentId: string;
            /**
             * Eventindex
             * @description 0-based index in anchor.agentId's events[]; INT_MAX (2147483647) is the post_process sentinel; -1 with kind=unknown means the reporting Agent could not be resolved.
             */
            eventIndex: number;
            /**
             * Kind
             * @description Anchor semantics: event, reporter node, post-process, or unknown.
             * @enum {string}
             */
            kind: "event" | "node" | "post_process" | "unknown";
        };
        /**
         * BadCaseCatalogSyncSummary
         * @description Read-only catalog-sync counters for the top-nav popover.
         */
        BadCaseCatalogSyncSummary: {
            /** Assigned */
            assigned: number;
            /** Invalidlabel */
            invalidLabel: number;
            /** Lastbadcaseid */
            lastBadCaseId: number;
            /** Lasterror */
            lastError: string | null;
            /** Lastrunat */
            lastRunAt: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "unavailable" | "idle" | "queued" | "running" | "failed";
            /** Synced */
            synced: number;
            /** Unassigned */
            unassigned: number;
            /** Unsynced */
            unsynced: number;
        };
        /**
         * BadCaseIngest
         * @description One camelCase report accepted from a workspace ingest credential.
         *
         *     Only JSON camelCase aliases are accepted: the body may never carry a
         *     workspace identity and snake_case input is rejected rather than silently
         *     accepted, so a caller cannot smuggle server-owned columns.
         */
        BadCaseIngest: {
            /** Badcaseagentid */
            badCaseAgentId?: string | null;
            /** Badcaseid */
            badCaseId: string;
            /**
             * Badcasetype
             * @enum {string}
             */
            badCaseType: "self" | "discovery";
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Metadata */
            metaData?: {
                [key: string]: unknown;
            } | null;
            /** Objectname */
            objectName: string;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent";
            /** Objectversion */
            objectVersion?: string | null;
            /** Reason */
            reason: string;
            /** Sessionid */
            sessionId: string;
            sessionSource?: components["schemas"]["BadCaseSessionSource"] | null;
            /** Source */
            source?: string | null;
            /** Title */
            title: string;
            /**
             * Triggerline
             * @description Optional 1-based log line where the report sits in the root Session, using the same coordinate as the Session tree event line; absent means the trigger point is unknown.
             */
            triggerLine?: number | null;
        };
        /**
         * BadCaseIngestResponse
         * @description Stable success payload shared by the 201 insert and 200 upsert paths.
         */
        BadCaseIngestResponse: {
            /** Badcaseid */
            badCaseId: string;
            /** Workspaceused */
            workspaceUsed: number;
        };
        /**
         * BadCaseListItem
         * @description One row of the filtered overview list.
         */
        BadCaseListItem: {
            /**
             * Attributioncount
             * @description Distinct (probeType, probeObject, objectVersion) attributions reached through bad_case_analysis; the canonical definition is 06 §4.2.1.
             */
            attributionCount: number;
            /** Badcaseid */
            badCaseId: string;
            /**
             * Badcasetype
             * @enum {string}
             */
            badCaseType: "self" | "discovery";
            /** Badcasetypelabel */
            badCaseTypeLabel: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Lasterror
             * @description Stable root-sync failure code while the trace is not ready.
             */
            lastError: string | null;
            /**
             * Nextretryat
             * @description Next scheduled automatic retry, when one is planned.
             */
            nextRetryAt: string | null;
            /** Objectname */
            objectName: string;
            /**
             * Retryable
             * @description Whether automatic sync can still make progress. Deterministic failures report false until their source configuration changes.
             */
            retryable: boolean;
            /** Sessionid */
            sessionId: string;
            /**
             * Sessionready
             * @description Whether the normalized Session projection can already be read.
             */
            sessionReady: boolean;
            /** @description Derived trace readiness: ready, pending, syncing, failed, or unavailable. The case itself exists whenever it appears in this list. */
            syncStatus: components["schemas"]["BadCaseTraceStatus"];
            /** Title */
            title: string;
            /**
             * Triggerat
             * Format: date-time
             * @description Trigger timestamp. Until object trigger coordinates land in m9-04 this temporarily equals createdAt.
             */
            triggerAt: string;
            /**
             * Triggerline
             * @description 1-based log line of the report's trigger point in the root Session (the same coordinate as the Session tree event line), or null when the report did not carry one. It is never derived from createdAt or an event index; the overview and error-detail flow share this trigger coordinate.
             */
            triggerLine: number | null;
        };
        /**
         * BadCaseListResponse
         * @description A Session's problems in external creation order.
         */
        BadCaseListResponse: {
            /** Items */
            items: components["schemas"]["BadCase"][];
        };
        /**
         * BadCaseSessionSource
         * @description One report's optional session download contract.
         *
         *     The template is a plain URL with exactly one ``{sessionId}`` placeholder.
         *     Credentials are deliberately absent: authorization is the template's own
         *     short-lived signature, and the report body can never smuggle headers.
         */
        BadCaseSessionSource: {
            /** Runtime */
            runtime?: string | null;
            /** Sessionurltemplate */
            sessionUrlTemplate: string;
        };
        /**
         * BadCaseSyncSummary
         * @description Read-only bad-case root-sync counters for the top-nav popover.
         */
        BadCaseSyncSummary: {
            /** Failed */
            failed: number;
            /** Lasterror */
            lastError: string | null;
            /** Lastrunat */
            lastRunAt: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "unavailable" | "idle" | "queued" | "running" | "failed";
            /** Synced */
            synced: number;
            /** Syncing */
            syncing: number;
            /** Total */
            total: number;
            /** Unsynced */
            unsynced: number;
        };
        /**
         * BadCaseTraceStatus
         * @description Public trace state shared by the overview list and detail error body.
         * @enum {string}
         */
        BadCaseTraceStatus: "ready" | "pending" | "syncing" | "failed" | "unavailable";
        /**
         * BindingFailure
         * @description Last failed background analysis of the current binding.
         */
        BindingFailure: {
            /** Attempts */
            attempts: number;
            /** Reason */
            reason: string;
            /** Willretry */
            willRetry: boolean;
        };
        /** Body_upload_attribution_skill_package_api_workspaces__wid__attribution_skill_packages_post */
        Body_upload_attribution_skill_package_api_workspaces__wid__attribution_skill_packages_post: {
            /**
             * File
             * @description Attribution Skill folder ZIP
             */
            file: string;
        };
        /**
         * CatalogModel
         * @description One normalized model and its usage across the trace corpus.
         */
        CatalogModel: {
            /** Agentcount */
            agentCount: number;
            /** Model */
            model: string;
            /** Sessioncount */
            sessionCount: number;
        };
        /**
         * CatalogModels
         * @description The complete model catalog.
         */
        CatalogModels: {
            /** Items */
            items: components["schemas"]["CatalogModel"][];
        };
        /**
         * CatalogTarget
         * @description One enabled evolution target and its remote versions.
         */
        CatalogTarget: {
            /** Defaultref */
            defaultRef: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Repourl */
            repoUrl: string;
            /** Subdir */
            subDir: string;
            /** Versions */
            versions: string[];
        };
        /**
         * CatalogTargets
         * @description Enabled targets grouped by the kind selectable in the wizard.
         */
        CatalogTargets: {
            /** Agent */
            agent: components["schemas"]["CatalogTarget"][];
            /** Skill */
            skill: components["schemas"]["CatalogTarget"][];
        };
        /**
         * ChangePasswordRequest
         * @description Owner-supplied current and replacement passwords.
         */
        ChangePasswordRequest: {
            /** Newpassword */
            newPassword: string;
            /** Oldpassword */
            oldPassword: string;
        };
        /**
         * CreateUserRequest
         * @description Administrator-provisioned account with a temporary password.
         */
        CreateUserRequest: {
            /** Displayname */
            displayName: string;
            /** Password */
            password: string;
            /**
             * Role
             * @default member
             * @enum {string}
             */
            role: "admin" | "member";
            /** Username */
            username: string;
        };
        /**
         * DataHealthResponse
         * @description Sanitized data-directory health included in the public health response.
         */
        DataHealthResponse: {
            /** Ok */
            ok: boolean;
        };
        /**
         * DatabaseDialect
         * @description Supported SQLAlchemy database dialects.
         * @enum {string}
         */
        DatabaseDialect: "sqlite" | "mysql";
        /**
         * DatabaseHealthResponse
         * @description Sanitized database health included in the public health response.
         */
        DatabaseHealthResponse: {
            dialect: components["schemas"]["DatabaseDialect"];
            /** Error */
            error?: string | null;
            /** Latencyms */
            latencyMs: number;
            /** Ok */
            ok: boolean;
        };
        /**
         * EffectiveAttributionSkill
         * @description Resolved Skill revision plus the precedence source that selected it.
         */
        EffectiveAttributionSkill: {
            /** Builtin */
            builtIn: boolean;
            /** Content */
            content: {
                [key: string]: unknown;
            };
            /** Contenthash */
            contentHash: string;
            /** Description */
            description: string;
            /** Displayname */
            displayName: string;
            /** Enabled */
            enabled: boolean;
            /** Executortype */
            executorType: string;
            /** Id */
            id: string;
            /** Outputschemaversion */
            outputSchemaVersion: string;
            /** Qualitystatus */
            qualityStatus: string;
            /** Revision */
            revision: number;
            /** Skillid */
            skillId: string;
            /** Skillkey */
            skillKey: string;
            /**
             * Source
             * @enum {string}
             */
            source: "target" | "workspace" | "platform";
            /** Status */
            status: string;
            /** Workspaceid */
            workspaceId: string | null;
        };
        /**
         * ErrorBody
         * @description Error payload shared by browser and API clients.
         */
        ErrorBody: {
            code: components["schemas"]["ErrorCode"];
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /** Message */
            message: string;
        };
        /**
         * ErrorCode
         * @description Stable machine-readable error codes.
         * @enum {string}
         */
        ErrorCode: "AUTH_REQUIRED" | "AUTH_INVALID" | "AUTH_EXPIRED" | "AUTH_PROVIDER_NOT_CONFIGURED" | "AUTH_STATE_INVALID" | "AUTH_PROVIDER_ERROR" | "AUTH_NO_MAPPING" | "TICKET_INVALID" | "TICKET_EXPIRED" | "FORBIDDEN" | "PASSWORD_CHANGE_REQUIRED" | "USERNAME_CONFLICT" | "SESSION_NOT_FOUND" | "BAD_CASE_NOT_FOUND" | "BAD_CASE_SESSION_PENDING" | "BAD_CASE_SESSION_UNAVAILABLE" | "BAD_CASE_SESSION_MISMATCH" | "ATTRIBUTION_NOT_FOUND" | "ATTRIBUTION_SKILL_NOT_FOUND" | "ATTRIBUTION_SKILL_EXISTS" | "ATTRIBUTION_SKILL_INVALID" | "ATTRIBUTION_SKILL_PACKAGE_NOT_FOUND" | "ATTRIBUTION_SKILL_PACKAGE_EXISTS" | "ATTRIBUTION_SKILL_PACKAGE_INVALID" | "ATTRIBUTION_SKILL_PACKAGE_TOO_LARGE" | "ATTRIBUTION_QUALITY_GATE_FAILED" | "ATTRIBUTION_ENGINE_UNAVAILABLE" | "PROBE_NOT_FOUND" | "JOB_NOT_FOUND" | "RUN_NOT_FOUND" | "STEP_NOT_READY" | "RUN_BUSY" | "RUN_CONTROL_CONFLICT" | "RUN_NOT_RETRYABLE" | "REPO_INVALID" | "PROJECT_ID_INVALID" | "ENGINE_INVALID" | "TARGET_EXISTS" | "TARGET_NOT_FOUND" | "TARGET_IN_USE" | "TARGET_NOT_CONFIGURED" | "TARGET_CONTENT_UNRESOLVED" | "NO_PROBES_MATCHED" | "POLICY_INVALID" | "NO_ASSOCIATED_SESSIONS" | "NO_POTENTIAL_MATCHED" | "INTERNAL" | "EXTERNAL_SCHEMA_DRIFT" | "EXTERNAL_READ_FORBIDDEN" | "EXTERNAL_READ_FAILED" | "METHOD_NOT_ALLOWED" | "NOT_FOUND" | "VALIDATION_INVALID" | "RATE_LIMITED" | "UPSTREAM_NOT_AVAILABLE" | "UPSTREAM_VERSION_INCOMPATIBLE" | "UPSTREAM_INVALID_RESPONSE" | "UPSTREAM_REQUEST_FAILED" | "SESSION_QUERY_UNAVAILABLE" | "SESSION_QUERY_UNAUTHORIZED" | "SESSION_QUERY_VERSION_INCOMPATIBLE" | "SESSION_QUERY_INVALID_RESPONSE" | "SESSION_QUERY_TIMEOUT" | "SESSION_QUERY_REQUEST_FAILED" | "SESSION_SOURCE_UNAUTHORIZED" | "SESSION_SOURCE_INVALID_RESPONSE" | "SESSION_SOURCE_TIMEOUT" | "SESSION_SOURCE_REQUEST_FAILED" | "SESSION_SOURCE_VERSION_INCOMPATIBLE" | "SESSION_SOURCE_SESSION_MISMATCH" | "TRAVERSAL_LIMIT_EXCEEDED" | "TRAJECTORY_EMPTY" | "BAD_CASE_SYNC_FAILED" | "BAD_CASE_SYNC_TIME_BUDGET" | "BAD_CASE_QUERY_UNAVAILABLE" | "BAD_CASE_QUERY_UNAUTHORIZED" | "BAD_CASE_QUERY_INVALID_RESPONSE" | "BAD_CASE_QUERY_TIMEOUT" | "BAD_CASE_QUERY_REQUEST_FAILED" | "BAD_CASE_CATALOG_SYNC_FAILED" | "BAD_CASE_CATALOG_SYNC_INTERRUPTED" | "WORKSPACE_NOT_FOUND" | "WORKSPACE_FORBIDDEN" | "WORKSPACE_EXISTS" | "MEMBER_EXISTS" | "MEMBER_NOT_FOUND" | "ROLE_INVALID" | "ROLE_LOCKED" | "QUOTA_INVALID" | "CREDENTIAL_NOT_FOUND" | "CREDENTIAL_INVALID" | "CREDENTIAL_LIMIT" | "QUOTA_EXCEEDED" | "BAD_CASE_ID_CONFLICT" | "WINDOW_INVALID" | "GRAIN_INVALID" | "OBJECT_FILTER_TOO_LARGE" | "KNOWLEDGE_ROOTS_INVALID";
        /**
         * ErrorResponse
         * @description Top-level failure response.
         */
        ErrorResponse: {
            error: components["schemas"]["ErrorBody"];
        };
        /**
         * EventTicketResponse
         * @description Opaque single-use grant for one SSE connection.
         */
        EventTicketResponse: {
            /** Expiresin */
            expiresIn: number;
            /** Ticket */
            ticket: string;
            /** Topics */
            topics: string[];
        };
        /**
         * EvolutionRetryAccepted
         * @description Asynchronous acceptance of one manual blocked-run retry.
         */
        EvolutionRetryAccepted: {
            /** Jobid */
            jobId: string;
            /** Reused */
            reused: boolean;
        };
        /**
         * EvolutionRunAttributeStats
         * @description Case counts by the closed attribution category.
         */
        EvolutionRunAttributeStats: {
            /**
             * Context
             * @default 0
             */
            context: number;
            /**
             * Error
             * @default 0
             */
            error: number;
            /**
             * Flow
             * @default 0
             */
            flow: number;
            /**
             * Model
             * @default 0
             */
            model: number;
            /**
             * Prompt
             * @default 0
             */
            prompt: number;
        };
        /**
         * EvolutionRunAttributionSkill
         * @description Immutable attribution Skill identity frozen when the run was launched.
         */
        EvolutionRunAttributionSkill: {
            /** Contenthash */
            contentHash: string;
            /** Engine */
            engine: string;
            /** Key */
            key: string;
            /** Revision */
            revision: number;
        };
        /**
         * EvolutionRunCard
         * @description One complete run-list card contract.
         */
        EvolutionRunCard: {
            /** Cacheenabled */
            cacheEnabled: boolean;
            /**
             * Canpause
             * @default false
             */
            canPause: boolean;
            /**
             * Canresume
             * @default false
             */
            canResume: boolean;
            /**
             * Controlstate
             * @default running
             * @enum {string}
             */
            controlState: "running" | "pause_requested" | "paused";
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Createdby */
            createdBy: string | null;
            /**
             * Degraded
             * @default false
             */
            degraded: boolean;
            error: components["schemas"]["EvolutionRunError"] | null;
            final: components["schemas"]["EvolutionRunFinal"] | null;
            /**
             * Mode
             * @enum {string}
             */
            mode: "full" | "cluster_only";
            /** Models */
            models: string[];
            /** Pauserequestedat */
            pauseRequestedAt?: string | null;
            /** Pausedat */
            pausedAt?: string | null;
            /** Pausedby */
            pausedBy?: string | null;
            policy: components["schemas"]["EvolutionRunPolicy"];
            progress: components["schemas"]["EvolutionRunProgress"];
            /** Runid */
            runId: string;
            stats: components["schemas"]["EvolutionRunStats"];
            /**
             * Status
             * @enum {string}
             */
            status: "preparing" | "running" | "blocked" | "completed" | "failed" | "interrupted";
            target: components["schemas"]["EvolutionRunTarget"];
            /** Title */
            title: string;
            window: components["schemas"]["EvolutionRunWindow"];
        };
        /**
         * EvolutionRunControl
         * @description Server-authoritative controls shared by mutations, cards and details.
         */
        EvolutionRunControl: {
            /**
             * Canpause
             * @default false
             */
            canPause: boolean;
            /**
             * Canresume
             * @default false
             */
            canResume: boolean;
            /**
             * Controlstate
             * @default running
             * @enum {string}
             */
            controlState: "running" | "pause_requested" | "paused";
            /** Pauserequestedat */
            pauseRequestedAt?: string | null;
            /** Pausedat */
            pausedAt?: string | null;
            /** Pausedby */
            pausedBy?: string | null;
            /** Runid */
            runId: string;
        };
        /**
         * EvolutionRunDetail
         * @description Complete shell consumed by the seven-step run-detail page.
         */
        EvolutionRunDetail: {
            attributionSkill: components["schemas"]["EvolutionRunAttributionSkill"] | null;
            /** Blockedstage */
            blockedStage: ("patch" | "push" | "eval" | "attribution") | null;
            /** Cacheenabled */
            cacheEnabled: boolean;
            /**
             * Canpause
             * @default false
             */
            canPause: boolean;
            /**
             * Canresume
             * @default false
             */
            canResume: boolean;
            /**
             * Controlstate
             * @default running
             * @enum {string}
             */
            controlState: "running" | "pause_requested" | "paused";
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Createdby */
            createdBy: string | null;
            /**
             * Degraded
             * @default false
             */
            degraded: boolean;
            error: components["schemas"]["EvolutionRunError"] | null;
            /**
             * Evalstatus
             * @enum {string}
             */
            evalStatus: "pending" | "evaluating" | "completed" | "failed" | "timeout";
            final: components["schemas"]["EvolutionRunFinal"] | null;
            /** Lasteventseq */
            lastEventSeq: number;
            /**
             * Mode
             * @enum {string}
             */
            mode: "full" | "cluster_only";
            /** Models */
            models: string[];
            /** Nextretryat */
            nextRetryAt: string | null;
            /** Pauserequestedat */
            pauseRequestedAt?: string | null;
            /** Pausedat */
            pausedAt?: string | null;
            /** Pausedby */
            pausedBy?: string | null;
            policy: components["schemas"]["EvolutionRunPolicy"];
            progress: components["schemas"]["EvolutionRunProgress"];
            /** Retryattempts */
            retryAttempts: number;
            /** Runid */
            runId: string;
            stats: components["schemas"]["EvolutionRunStats"];
            /**
             * Status
             * @enum {string}
             */
            status: "preparing" | "running" | "blocked" | "completed" | "failed" | "interrupted";
            /** Steps */
            steps: components["schemas"]["EvolutionRunStep"][];
            target: components["schemas"]["EvolutionRunTarget"];
            /** Title */
            title: string;
            window: components["schemas"]["EvolutionRunWindow"];
            workspace: components["schemas"]["EvolutionRunWorkspace"];
        };
        /**
         * EvolutionRunError
         * @description Sanitized terminal or blocked error summary.
         */
        EvolutionRunError: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Message */
            message: string;
            /** Stage */
            stage: string;
        };
        /**
         * EvolutionRunEvent
         * @description One complete event object shared by REST and SSE.
         */
        EvolutionRunEvent: {
            /** Clusterid */
            clusterId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            error: components["schemas"]["EvolutionRunEventError"] | null;
            /**
             * Eventtype
             * @enum {string}
             */
            eventType: "run_created" | "prepare_started" | "sessions_linked" | "potential_computed" | "attribution_created" | "attribution_reused" | "workspace_prepared" | "clusters_created" | "ai_agent_call" | "degraded" | "step_advanced" | "run_pause_requested" | "run_paused" | "run_continued" | "run_blocked" | "run_resumed" | "final_completed" | "run_failed" | "run_interrupted" | "job_recovered" | "candidate_committed" | "candidate_pushed" | "eval_submitted" | "eval_polled" | "eval_completed" | "eval_failed" | "eval_timeout" | "cluster_accepted" | "cluster_rejected" | "push_started" | "push_retry_scheduled" | "push_succeeded" | "push_failed";
            /** Jobid */
            jobId: string | null;
            /**
             * Level
             * @enum {string}
             */
            level: "info" | "warn" | "error";
            /** Message */
            message: string;
            /** Payload */
            payload: {
                [key: string]: unknown;
            } | null;
            /** Roundid */
            roundId: string | null;
            /** Seq */
            seq: number;
            /**
             * Stage
             * @enum {string}
             */
            stage: "prepare" | "cluster" | "step" | "candidate" | "push" | "eval" | "apply" | "final";
            /** Stepindex */
            stepIndex: number | null;
        };
        /**
         * EvolutionRunEventError
         * @description Sanitized error detail attached to one persisted run event.
         */
        EvolutionRunEventError: {
            /** Detail */
            detail: string | null;
            /** Message */
            message: string | null;
            /** Type */
            type: string | null;
        };
        /**
         * EvolutionRunEventPage
         * @description One stable run-event page for REST replay and UI pagination.
         */
        EvolutionRunEventPage: {
            /** Hasmore */
            hasMore: boolean;
            /** Items */
            items: components["schemas"]["EvolutionRunEvent"][];
            /** Nextseq */
            nextSeq: number;
        };
        /**
         * EvolutionRunFinal
         * @description Terminal evaluation summary shown in the history list.
         */
        EvolutionRunFinal: {
            /** Bestscore */
            bestScore: number;
            /** Bestversion */
            bestVersion: string;
            /** Branchname */
            branchName: string | null;
            /** Initscore */
            initScore: number;
            /**
             * Pushstatus
             * @enum {string}
             */
            pushStatus: "pending" | "pushing" | "succeeded" | "failed" | "skipped";
            /** Verdict */
            verdict: boolean;
        };
        /**
         * EvolutionRunList
         * @description Running and history groups already ordered by the backend.
         */
        EvolutionRunList: {
            /** History */
            history: components["schemas"]["EvolutionRunCard"][];
            /** Running */
            running: components["schemas"]["EvolutionRunCard"][];
        };
        /**
         * EvolutionRunPolicy
         * @description Display-only potential policy preset for one run card.
         */
        EvolutionRunPolicy: {
            /**
             * Preset
             * @default default
             * @enum {string}
             */
            preset: "default" | "custom";
        };
        /**
         * EvolutionRunProgress
         * @description Backend-owned cursor, percentages, rounds, and stage copy.
         */
        EvolutionRunProgress: {
            /** Accepted */
            accepted: number;
            /** Donerounds */
            doneRounds: number;
            /** Percent */
            percent: number;
            /** Stagelabel */
            stageLabel: string;
            /** Total */
            total: number;
            /** Unit */
            unit: number;
        };
        /**
         * EvolutionRunStats
         * @description Backend-normalized V2 run statistics.
         */
        EvolutionRunStats: {
            /**
             * Attributed
             * @default 0
             */
            attributed: number;
            /**
             * Badcases
             * @default 0
             */
            badCases: number;
            byCategory: components["schemas"]["EvolutionRunAttributeStats"];
            /**
             * Clusters
             * @default 0
             */
            clusters: number;
            /**
             * Potential
             * @default 0
             */
            potential: number;
            /**
             * Reused
             * @default 0
             */
            reused: number;
            /**
             * Sessions
             * @default 0
             */
            sessions: number;
            /**
             * Versionunresolvedsessions
             * @default 0
             */
            versionUnresolvedSessions: number;
        };
        /**
         * EvolutionRunStep
         * @description One backend-owned stepper node with lazy-load eligibility.
         */
        EvolutionRunStep: {
            /** Clickable */
            clickable: boolean;
            /** Detail */
            detail?: string | null;
            /** Index */
            index: number;
            /**
             * Key
             * @enum {string}
             */
            key: "range" | "sessions" | "potential" | "attribution" | "clusters" | "iteration" | "final";
            /**
             * Status
             * @enum {string}
             */
            status: "done" | "active" | "pending";
            /** Title */
            title: string;
        };
        /**
         * EvolutionRunTarget
         * @description Immutable evolution target snapshot shown on one run card.
         */
        EvolutionRunTarget: {
            /** Name */
            name: string;
            /**
             * Targetrevision
             * @description Resolved file-matching revision (digest:<sha256(body)> for skill/agent/knowledge file targets); null on historical runs.
             */
            targetRevision?: string | null;
            /**
             * Type
             * @enum {string}
             */
            type: "skill" | "agent" | "knowledge";
            /** Version */
            version: string;
        };
        /**
         * EvolutionRunWindow
         * @description Session-time window selected when the run was created.
         */
        EvolutionRunWindow: {
            /** From */
            from?: string | null;
            /** To */
            to?: string | null;
        };
        /**
         * EvolutionRunWorkspace
         * @description Repository and worktree state shown by the run detail.
         */
        EvolutionRunWorkspace: {
            /** Basecommit */
            baseCommit: string | null;
            /** Baseref */
            baseRef: string | null;
            /** Branchname */
            branchName: string | null;
            /** Pusherror */
            pushError: string | null;
            /** Pushrepourl */
            pushRepoUrl: string;
            /**
             * Pushstatus
             * @enum {string}
             */
            pushStatus: "pending" | "pushing" | "succeeded" | "failed" | "skipped";
            /** Pushedat */
            pushedAt: string | null;
            /** Remote */
            remote: string;
            /** Repopath */
            repoPath: string | null;
            /** Repourl */
            repoUrl: string;
            /** Subdir */
            subDir: string;
            /** Workspacepath */
            workspacePath: string | null;
        };
        /**
         * EvolutionStepAttribution
         * @description Step 3 response: per-case attribution conclusions.
         */
        EvolutionStepAttribution: {
            /** Clickable */
            clickable: boolean;
            /** Detail */
            detail?: string | null;
            /** Index */
            index: number;
            /**
             * Key
             * @default attribution
             * @constant
             */
            key: "attribution";
            payload: components["schemas"]["StepAttributionPayload"];
            /**
             * Status
             * @enum {string}
             */
            status: "done" | "active" | "pending";
            /** Title */
            title: string;
        };
        /**
         * EvolutionStepClusters
         * @description Step 4 response: ranked clusters with source cases.
         */
        EvolutionStepClusters: {
            /** Clickable */
            clickable: boolean;
            /** Detail */
            detail?: string | null;
            /** Index */
            index: number;
            /**
             * Key
             * @default clusters
             * @constant
             */
            key: "clusters";
            payload: components["schemas"]["StepClustersPayload"];
            /**
             * Status
             * @enum {string}
             */
            status: "done" | "active" | "pending";
            /** Title */
            title: string;
        };
        /**
         * EvolutionStepFinal
         * @description Step 6 response: terminal evaluation.
         */
        EvolutionStepFinal: {
            /** Clickable */
            clickable: boolean;
            /** Detail */
            detail?: string | null;
            /** Index */
            index: number;
            /**
             * Key
             * @default final
             * @constant
             */
            key: "final";
            payload: components["schemas"]["StepFinalPayload"];
            /**
             * Status
             * @enum {string}
             */
            status: "done" | "active" | "pending";
            /** Title */
            title: string;
        };
        /**
         * EvolutionStepIteration
         * @description Step 5 response: iteration rounds.
         */
        EvolutionStepIteration: {
            /** Clickable */
            clickable: boolean;
            /** Detail */
            detail?: string | null;
            /** Index */
            index: number;
            /**
             * Key
             * @default iteration
             * @constant
             */
            key: "iteration";
            payload: components["schemas"]["StepIterationPayload"];
            /**
             * Status
             * @enum {string}
             */
            status: "done" | "active" | "pending";
            /** Title */
            title: string;
        };
        /**
         * EvolutionStepPotential
         * @description Step 2 response: paged potential bad cases.
         */
        EvolutionStepPotential: {
            /** Clickable */
            clickable: boolean;
            /** Detail */
            detail?: string | null;
            /** Index */
            index: number;
            /**
             * Key
             * @default potential
             * @constant
             */
            key: "potential";
            payload: components["schemas"]["StepPotentialPayload"];
            /**
             * Status
             * @enum {string}
             */
            status: "done" | "active" | "pending";
            /** Title */
            title: string;
        };
        /**
         * EvolutionStepRange
         * @description Step 0 response: selection snapshot and headline counts.
         */
        EvolutionStepRange: {
            /** Clickable */
            clickable: boolean;
            /** Detail */
            detail?: string | null;
            /** Index */
            index: number;
            /**
             * Key
             * @default range
             * @constant
             */
            key: "range";
            payload: components["schemas"]["StepRangePayload"];
            /**
             * Status
             * @enum {string}
             */
            status: "done" | "active" | "pending";
            /** Title */
            title: string;
        };
        /**
         * EvolutionStepSessions
         * @description Step 1 response: paged Session association.
         */
        EvolutionStepSessions: {
            /** Clickable */
            clickable: boolean;
            /** Detail */
            detail?: string | null;
            /** Index */
            index: number;
            /**
             * Key
             * @default sessions
             * @constant
             */
            key: "sessions";
            payload: components["schemas"]["StepSessionsPayload"];
            /**
             * Status
             * @enum {string}
             */
            status: "done" | "active" | "pending";
            /** Title */
            title: string;
        };
        /**
         * EvolutionTarget
         * @description Persisted target returned to clients.
         */
        EvolutionTarget: {
            attributionFailure?: components["schemas"]["BindingFailure"] | null;
            /** Attributionpackageid */
            attributionPackageId?: string | null;
            /** Attributionskillname */
            attributionSkillName?: string | null;
            /** Defaultref */
            defaultRef: string;
            definition?: components["schemas"]["TargetDefinitionPreview"] | null;
            /**
             * Enabled
             * @default true
             */
            enabled: boolean;
            /** Id */
            id: string;
            /** Objectname */
            objectName: string;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent" | "knowledge";
            /** Repourl */
            repoUrl: string;
            /** Subdir */
            subDir: string;
            /** Testprojectid */
            testProjectId: string;
            /** Validationprojectid */
            validationProjectId: string;
        };
        /**
         * EvolutionTargetList
         * @description Complete target configuration collection.
         */
        EvolutionTargetList: {
            /** Items */
            items: components["schemas"]["EvolutionTarget"][];
        };
        /**
         * EvolutionTargetVersions
         * @description Remote tags and the persisted default reference.
         */
        EvolutionTargetVersions: {
            /** Defaultref */
            defaultRef: string;
            /** Versions */
            versions: string[];
        };
        /**
         * EvolutionTargetWrite
         * @description Mutable target configuration accepted by create and update.
         */
        EvolutionTargetWrite: {
            /** Attributionpackageid */
            attributionPackageId?: string | null;
            /** Defaultref */
            defaultRef: string;
            /**
             * Enabled
             * @default true
             */
            enabled: boolean;
            /** Objectname */
            objectName: string;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent" | "knowledge";
            /** Repourl */
            repoUrl: string;
            /** Subdir */
            subDir: string;
            /** Testprojectid */
            testProjectId: string;
            /** Validationprojectid */
            validationProjectId: string;
        };
        /**
         * GoldenExpected
         * @description Expected semantic outcome and verifiable evidence constraints.
         */
        GoldenExpected: {
            /** Category */
            category?: ("model" | "prompt" | "error" | "flow" | "context") | null;
            /**
             * Conclusion
             * @enum {string}
             */
            conclusion: "attributed" | "non_target" | "inconclusive";
            /**
             * Detectionpointrequired
             * @default false
             */
            detectionPointRequired: boolean;
            /**
             * Introductionpointrequired
             * @default false
             */
            introductionPointRequired: boolean;
            /** Requiredevidencerefs */
            requiredEvidenceRefs?: string[];
        };
        /**
         * GoldenThresholds
         * @description Closed promotion thresholds carried by one versioned Golden Set.
         */
        GoldenThresholds: {
            /** Categoryaccuracy */
            categoryAccuracy: number;
            /** Conclusionaccuracy */
            conclusionAccuracy: number;
            /** Evidencevalidityrate */
            evidenceValidityRate: number;
            /** Maximumaveragetokens */
            maximumAverageTokens: number;
            /** Maximumfailurerate */
            maximumFailureRate: number;
            /** Maximump95Latencyms */
            maximumP95LatencyMs: number;
            /** Pointhitrate */
            pointHitRate: number;
            /** Safetyrate */
            safetyRate: number;
            /** Schemacompliancerate */
            schemaComplianceRate: number;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * HealthResponse
         * @description Public health-check contract.
         */
        HealthResponse: {
            data: components["schemas"]["DataHealthResponse"];
            db: components["schemas"]["DatabaseHealthResponse"];
            /** Ok */
            ok: boolean;
            phase: components["schemas"]["ServicePhase"];
            /**
             * Service
             * @constant
             */
            service: "harness-evolution";
            /** Version */
            version: string;
        };
        /**
         * IssueAnalysisResult
         * @description Public result shape for an attribution that classifies an issue.
         */
        IssueAnalysisResult: {
            /** Summary */
            summary: string;
        };
        /**
         * IssueBadCaseAnalysis
         * @description An analyzed issue result always carries its public summary.
         */
        IssueBadCaseAnalysis: {
            /** Attributetype */
            attributeType: ("model" | "prompt" | "error" | "flow" | "context") | null;
            /**
             * Displaystate
             * @enum {string}
             */
            displayState: "analyzed_issue_model" | "analyzed_issue_prompt" | "analyzed_issue_error";
            /** Probeid */
            probeId: string | null;
            result: components["schemas"]["IssueAnalysisResult"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            status: "analyzed_issue";
        };
        /**
         * JobResponse
         * @description Durable job state returned as the REST source of truth.
         */
        JobResponse: {
            /** Attempt */
            attempt: number;
            /** Cancelrequested */
            cancelRequested: boolean;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Createdby */
            createdBy: string | null;
            /** Error */
            error: string | null;
            /** Finishedat */
            finishedAt: string | null;
            /** Jobid */
            jobId: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "sync" | "pull" | "bad_case_root_sync" | "evolution_prepare" | "evolution_advance" | "evolution_apply" | "evolution_finalize" | "evolution_retry" | "attribution_batch";
            /** Leaseexpiresat */
            leaseExpiresAt: string | null;
            /** Maxattempts */
            maxAttempts: number;
            /** Progress */
            progress: number;
            /** Refid */
            refId: string | null;
            /** Result */
            result: {
                [key: string]: unknown;
            } | null;
            /** Startedat */
            startedAt: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "running" | "completed" | "failed" | "interrupted" | "cancelled";
        };
        /**
         * LoginRequest
         * @description Credentials exchanged for a bearer token and refresh cookie.
         */
        LoginRequest: {
            /** Password */
            password: string;
            /** Username */
            username: string;
        };
        /**
         * LoginResponse
         * @description Successful authentication result.
         */
        LoginResponse: {
            /** Accesstoken */
            accessToken: string;
            /** Expiresin */
            expiresIn: number;
            user: components["schemas"]["PublicUser"];
        };
        /**
         * NonIssueAnalysisResult
         * @description Public result shape for an attribution that classifies a non-issue.
         */
        NonIssueAnalysisResult: {
            /** Reason */
            reason: string;
            /** Reasoning */
            reasoning: string[];
        };
        /**
         * NonIssueBadCaseAnalysis
         * @description An analyzed non-issue result always carries its explanation.
         */
        NonIssueBadCaseAnalysis: {
            /** Attributetype */
            attributeType: ("model" | "prompt" | "error" | "flow" | "context") | null;
            /**
             * Displaystate
             * @constant
             */
            displayState: "analyzed_nonissue";
            /** Probeid */
            probeId: string | null;
            result: components["schemas"]["NonIssueAnalysisResult"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            status: "analyzed_nonissue";
        };
        /**
         * OverviewBadCaseListResponse
         * @description One filtered page plus its authoritative total.
         */
        OverviewBadCaseListResponse: {
            /** Items */
            items: components["schemas"]["BadCaseListItem"][];
            /** Page */
            page: number;
            /** Pagesize */
            pageSize: number;
            /** Total */
            total: number;
        };
        /**
         * OverviewSummary
         * @description One workspace overview header: window, totals, and object options.
         */
        OverviewSummary: {
            /**
             * Objects
             * @description Distinct object names in the window, ignoring the object filter, sorted case-insensitively by name.
             */
            objects: string[];
            totals: components["schemas"]["OverviewTotals"];
            window: components["schemas"]["OverviewWindow"];
        };
        /**
         * OverviewTotals
         * @description Summary counters; ``quota``/``used`` ignore the window and every filter.
         */
        OverviewTotals: {
            /** Badcases */
            badCases: number;
            /** Discovery */
            discovery: number;
            /**
             * Quota
             * @description Workspace bad-case quota; independent of the window.
             */
            quota: number;
            /** Self */
            self: number;
            /**
             * Sessions
             * @description Distinct root sessions reported in the window, including roots without a normalized trace. This is not the Session page total; pending roots are counted here and pendingSessions is a separate Session page figure.
             */
            sessions: number;
            /**
             * Sources
             * @description Distinct object names in the window.
             */
            sources: number;
            /**
             * Used
             * @description Every bad case owned by the workspace; independent of the window.
             */
            used: number;
        };
        /**
         * OverviewWindow
         * @description The inclusive Asia/Shanghai window the response was computed over.
         */
        OverviewWindow: {
            /**
             * From
             * Format: date
             * @description Inclusive Asia/Shanghai start date.
             */
            from: string;
            /**
             * To
             * Format: date
             * @description Inclusive Asia/Shanghai end date.
             */
            to: string;
        };
        /**
         * PotentialPolicy
         * @description Raw policy switches accepted by the preview and launch contracts.
         */
        PotentialPolicy: {
            /** Includeafterobject */
            includeAfterObject?: boolean | null;
            /** Includeselfreport */
            includeSelfReport?: boolean | null;
            /**
             * Preset
             * @default default
             * @enum {string}
             */
            preset: "default" | "custom";
            /** Sameobjectonly */
            sameObjectOnly?: boolean | null;
        };
        /**
         * PotentialPreviewItem
         * @description One included bad case row in wizard step 3.
         */
        PotentialPreviewItem: {
            /**
             * Anchorsource
             * @enum {string}
             */
            anchorSource: "event" | "node" | "post_process" | "unknown";
            /** Badcaseid */
            badCaseId: string;
            /** Badcasetype */
            badCaseType: string;
            /**
             * Hitreason
             * @enum {string}
             */
            hitReason: "self_report" | "after_object" | "both" | "policy_excluded" | "order_unknown";
            /** Objectname */
            objectName: string;
            /**
             * Orderstate
             * @enum {string}
             */
            orderState: "comparable" | "unknown";
            /** Sessionid */
            sessionId: string;
            /**
             * Triggerat
             * Format: date-time
             */
            triggerAt: string;
        };
        /**
         * PotentialPreviewRequest
         * @description Potential stage condition: pagination plus the optional policy.
         */
        PotentialPreviewRequest: {
            /** From */
            from?: string | null;
            /**
             * Page
             * @default 1
             */
            page: number;
            /**
             * Pagesize
             * @default 5
             */
            pageSize: number;
            policy?: components["schemas"]["PotentialPolicy"] | null;
            /** Targetname */
            targetName: string;
            /**
             * Targettype
             * @enum {string}
             */
            targetType: "skill" | "agent" | "knowledge";
            /** Targetversion */
            targetVersion?: string | null;
            /** To */
            to?: string | null;
        };
        /**
         * PotentialPreviewResult
         * @description Paged potential rows; excluded rows stay in the summary only.
         */
        PotentialPreviewResult: {
            /** Items */
            items: components["schemas"]["PotentialPreviewItem"][];
            /** Page */
            page: number;
            /** Pagesize */
            pageSize: number;
            summary: components["schemas"]["PotentialPreviewSummary"];
            /** Targetrevision */
            targetRevision?: string | null;
            /** Total */
            total: number;
        };
        /**
         * PotentialPreviewSummary
         * @description Evaluated cases, included potential, and reason distribution.
         */
        PotentialPreviewSummary: {
            /** Badcases */
            badCases: number;
            byReason: components["schemas"]["PotentialReasonCounts"];
            /** Potential */
            potential: number;
        };
        /**
         * PotentialReasonCounts
         * @description Every closed hit reason, zero-filled for a stable contract.
         */
        PotentialReasonCounts: {
            /**
             * Afterobject
             * @default 0
             */
            afterObject: number;
            /**
             * Both
             * @default 0
             */
            both: number;
            /**
             * Orderunknown
             * @default 0
             */
            orderUnknown: number;
            /**
             * Policyexcluded
             * @default 0
             */
            policyExcluded: number;
            /**
             * Selfreport
             * @default 0
             */
            selfReport: number;
        };
        /**
         * ProbeHitSummary
         * @description Hit statistics shown by wizard step 2 before the probe table.
         */
        ProbeHitSummary: {
            /** Analyzed */
            analyzed: number;
            /** Badcases */
            badCases: number;
            byAttributeType: components["schemas"]["AttributeStats"];
            /** Probes */
            probes: number;
            /** Sessions */
            sessions: number;
            /** Unanalyzed */
            unanalyzed: number;
            /** Usedprobes */
            usedProbes: number;
        };
        /**
         * ProbeListResponse
         * @description A Session's root-cause reports.
         */
        ProbeListResponse: {
            /** Items */
            items: components["schemas"]["ProbeReport"][];
        };
        /**
         * ProbePreviewItem
         * @description One analyzed probe row rendered by wizard step 2.
         */
        ProbePreviewItem: {
            /**
             * Attributetype
             * @enum {string}
             */
            attributeType: "model" | "prompt" | "error" | "flow" | "context";
            /** Description */
            description: string;
            /** Model */
            model: string | null;
            /** Objectversion */
            objectVersion: string | null;
            /** Probeid */
            probeId: string;
            /** Probeobject */
            probeObject: string;
            /** Probetype */
            probeType: string;
            /** Sessionid */
            sessionId: string;
            /** Sessiontitle */
            sessionTitle: string | null;
            /** Sourcebadcaseids */
            sourceBadCaseIds: string[];
        };
        /**
         * ProbeQueryRequest
         * @description Wizard filter condition shared by preview and launch endpoints.
         */
        ProbeQueryRequest: {
            /** Attributionpackageid */
            attributionPackageId?: string | null;
            /**
             * Cacheenabled
             * @default true
             */
            cacheEnabled: boolean;
            /** Enginekey */
            engineKey?: string | null;
            /** Eval */
            eval?: {
                [key: string]: unknown;
            } | null;
            /** From */
            from?: string | null;
            /**
             * Mode
             * @default full
             * @enum {string}
             */
            mode: "full" | "cluster_only";
            /** Models */
            models?: string[];
            /**
             * Page
             * @default 1
             */
            page: number;
            /**
             * Pagesize
             * @default 8
             */
            pageSize: number;
            policy?: components["schemas"]["PotentialPolicy"] | null;
            /** Targetname */
            targetName: string;
            /**
             * Targettype
             * @enum {string}
             */
            targetType: "skill" | "agent" | "knowledge";
            /** Targetversion */
            targetVersion?: string | null;
            /** To */
            to?: string | null;
        };
        /**
         * ProbeQueryResult
         * @description Complete preview payload for wizard step 2.
         */
        ProbeQueryResult: {
            /** Items */
            items: components["schemas"]["ProbePreviewItem"][];
            /** Page */
            page: number;
            /** Pagesize */
            pageSize: number;
            summary: components["schemas"]["ProbeHitSummary"];
            /** Total */
            total: number;
        };
        /**
         * ProbeReport
         * @description One root-cause report with validated reverse source ids.
         */
        ProbeReport: {
            /** Attributetype */
            attributeType: ("model" | "prompt" | "error" | "flow" | "context") | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Frombadcases */
            fromBadCases: string[];
            /** Frombadcasescount */
            fromBadCasesCount: number;
            /** Objectversion */
            objectVersion: string | null;
            /** Probeanalysis */
            probeAnalysis: string;
            /** Probedescription */
            probeDescription: string;
            /** Probeid */
            probeId: string;
            /** Probeobject */
            probeObject: string;
            /** Probetype */
            probeType: ("skill" | "agent") | null;
            /** Sessionid */
            sessionId: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /**
         * PublicUser
         * @description User fields safe for browser and API clients.
         */
        PublicUser: {
            /** Displayname */
            displayName: string;
            /** Id */
            id: string;
            /** Mustchangepassword */
            mustChangePassword: boolean;
            /**
             * Role
             * @enum {string}
             */
            role: "admin" | "member";
            /** Username */
            username: string;
        };
        /**
         * PullJobPayload
         * @description Durable selector stored on one queued pull job.
         */
        PullJobPayload: {
            /** Sessionids */
            sessionIds?: string[] | null;
            window?: components["schemas"]["PullWindow"] | null;
        };
        /**
         * PullResponse
         * @description Queued pull job identity.
         */
        PullResponse: {
            /** Jobid */
            jobId: string;
        };
        /**
         * PullWindow
         * @description Date window accepted by the upstream enumeration endpoint.
         */
        PullWindow: {
            /** Cursor */
            cursor?: string | null;
            /**
             * From
             * Format: date
             */
            from: string;
            /**
             * Problemonly
             * @default true
             */
            problemOnly: boolean;
            /**
             * To
             * Format: date
             */
            to: string;
        };
        /**
         * RefreshResponse
         * @description Successful refresh result; callers reload `/api/auth/me` for user fields.
         */
        RefreshResponse: {
            /** Accesstoken */
            accessToken: string;
            /** Expiresin */
            expiresIn: number;
        };
        /**
         * RunAccepted
         * @description Asynchronous acceptance returned by both launch endpoints.
         */
        RunAccepted: {
            /** Jobid */
            jobId: string;
            /** Runid */
            runId: string;
            /**
             * Status
             * @constant
             */
            status: "preparing";
        };
        /**
         * ServicePhase
         * @description Delivery phase exposed by the health endpoint.
         * @enum {string}
         */
        ServicePhase: "scaffold" | "demo" | "live";
        /**
         * SessionAgent
         * @description One flat Agent node consumed directly by the execution-flow graph.
         */
        SessionAgent: {
            /**
             * Agentdefinitionhash
             * @description Stable body hash of this agent's definition when it has one.
             */
            agentDefinitionHash?: string | null;
            /** Agentid */
            agentId: string;
            /** Agenttype */
            agentType: string | null;
            /**
             * Definitionsource
             * @description Where the agent definition body was recovered from.
             */
            definitionSource?: ("prompt_snapshot" | "api_request_shape" | "builtin" | "unknown") | null;
            /** Desc */
            desc: string;
            /** Endreason */
            endReason?: ("end_turn" | "tool_use_open" | "missing_report" | "external_failed" | "external_interrupted") | null;
            /** Events */
            events: components["schemas"]["SessionEvent"][];
            /**
             * Executionoutcome
             * @enum {string}
             */
            executionOutcome: "completed" | "interrupted" | "failed" | "legacy_unknown";
            /**
             * Kind
             * @enum {string}
             */
            kind: "main" | "subagent" | "workflow";
            /** Label */
            label: string;
            /** Lines */
            lines: number;
            /** Messagescount */
            messagesCount: number;
            /** Parentagentid */
            parentAgentId: string | null;
            /** Skillname */
            skillName: string | null;
            /** Spawndepth */
            spawnDepth: number;
            /** Taskkind */
            taskKind: ("in_process_teammate" | "forked_skill") | null;
            /** Teamname */
            teamName: string | null;
            /** Tooluseid */
            toolUseId: string | null;
        };
        /**
         * SessionBadCase
         * @description One read-only problem connected to the execution tree.
         *
         *     ``title`` is the short display title and ``reason`` the description body;
         *     ``reason`` maps from the ``bad_cases.bad_case_description`` column.
         */
        SessionBadCase: {
            anchor: components["schemas"]["BadCaseAnchor"];
            badCaseAgent: components["schemas"]["BadCaseAgent"];
            /** Badcaseid */
            badCaseId: string;
            /**
             * Badcasetype
             * @enum {string}
             */
            badCaseType: "self" | "discovery";
            /** Objectname */
            objectName: string;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent";
            /** Objectversion */
            objectVersion: string | null;
            /** Reason */
            reason: string;
            /** Title */
            title: string;
        };
        /**
         * SessionEvent
         * @description One skill, Agent, workflow, or knowledge-document trigger within an Agent node.
         */
        SessionEvent: {
            /**
             * Definitionhash
             * @description Stable body hash of the triggered skill or agent definition.
             */
            definitionHash?: string | null;
            /** Desc */
            desc: string;
            /**
             * Documentid
             * @description Stable knowledge-document identity for a knowledge trigger.
             */
            documentId?: string | null;
            /**
             * Documentrevision
             * @description Raw document revision evidence: digest:<hash> / provider revision / unknown; differs from objectRevision for provider documents.
             */
            documentRevision?: string | null;
            /**
             * Filereadhash
             * @description Content hash for a complete file read that supplied the evidence.
             */
            fileReadHash?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "skill" | "agent" | "workflow" | "knowledge";
            /** Line */
            line: number;
            /** Messageoffset */
            messageOffset: number;
            /** Name */
            name: string | null;
            /**
             * Objectrevision
             * @description tag:<tag> / digest:<hash> / provider:<value> / unknown evidence for the triggered object.
             */
            objectRevision?: string | null;
            /**
             * Readcomplete
             * @description Whether the evidence source file was read in full.
             */
            readComplete?: boolean | null;
            /**
             * Relationconfidence
             * @description Strength of the parent-child evidence for an agent trigger.
             */
            relationConfidence?: ("authoritative" | "derived" | "synthetic" | "unresolved") | null;
            /**
             * Retrievalkind
             * @description file_read / mcp_search / mcp_retrieve.
             */
            retrievalKind?: string | null;
            /**
             * Retrievalscope
             * @description Matched knowledge root or provider collection scope.
             */
            retrievalScope?: string | null;
            /**
             * Sourcepath
             * @description Configured-root path of the knowledge document; never its body.
             */
            sourcePath?: string | null;
            /** Tooluseid */
            toolUseId: string | null;
        };
        /**
         * SessionListItem
         * @description One root-session card shared by list and overview routes.
         */
        SessionListItem: {
            /** Durationseconds */
            durationSeconds: number;
            /**
             * Executionoutcome
             * @enum {string}
             */
            executionOutcome: "completed" | "interrupted" | "failed" | "legacy_unknown";
            /** Id */
            id: string;
            /** Model */
            model: string | null;
            /** Repo */
            repo: string;
            /** Runtimekey */
            runtimeKey: string;
            /** Short */
            short: string;
            /** Skills */
            skills: string[];
            /**
             * Startedat
             * Format: date-time
             */
            startedAt: string;
            stats: components["schemas"]["SessionStats"];
            /**
             * Status
             * @enum {string}
             */
            status: "ok" | "partial" | "fail";
            /** Title */
            title: string;
        };
        /**
         * SessionListResponse
         * @description One current page plus counters.
         */
        SessionListResponse: {
            /** Items */
            items: components["schemas"]["SessionListItem"][];
            /**
             * Pendingsessions
             * @description Distinct roots reported inside the scope that have no normalized session yet; independent of q and status.
             */
            pendingSessions: number;
            /**
             * Total
             * @description Normalized sessions matching q and status across the whole scope; pending roots are excluded.
             */
            total: number;
        };
        /**
         * SessionPayload
         * @description Current user plus every workspace they can see for this session.
         */
        SessionPayload: {
            /** Truncated */
            truncated: boolean;
            user: components["schemas"]["PublicUser"];
            /** Workspaces */
            workspaces: components["schemas"]["SessionWorkspace"][];
        };
        /**
         * SessionPreviewItem
         * @description One associated Session row in wizard step 2.
         */
        SessionPreviewItem: {
            /** Badcasecount */
            badCaseCount: number;
            /**
             * Objecttriggerat
             * Format: date-time
             * @description Object entry instant; falls back to the Session startedAt when the entry event has no triggeredAt. Comparison still uses coordinates when either side lacks a timestamp.
             */
            objectTriggerAt: string;
            /** Sessionid */
            sessionId: string;
            /** Short */
            short: string;
            /** Title */
            title: string;
        };
        /**
         * SessionPreviewResult
         * @description Paged associated Session projection.
         */
        SessionPreviewResult: {
            /** Items */
            items: components["schemas"]["SessionPreviewItem"][];
            /** Page */
            page: number;
            /** Pagesize */
            pageSize: number;
            summary: components["schemas"]["SessionPreviewSummary"];
            /** Targetrevision */
            targetRevision?: string | null;
            /** Total */
            total: number;
        };
        /**
         * SessionPreviewSummary
         * @description Non-overlapping Session partition for wizard step 2.
         */
        SessionPreviewSummary: {
            /** Associated */
            associated: number;
            /** Pending */
            pending: number;
            /** Reported */
            reported: number;
            /** Skipped */
            skipped: number;
            /** Versionunresolved */
            versionUnresolved: number;
        };
        /**
         * SessionStats
         * @description Backend-computed whole-tree card statistics.
         */
        SessionStats: {
            /** Agents */
            agents: number;
            /** Badcases */
            badCases: number;
            /** Badcasesper100Messages */
            badCasesPer100Messages: number;
            /** Errors */
            errors: number;
            /** Failper100Messages */
            failPer100Messages: number;
            /** Messages */
            messages: number;
            /** Tokens */
            tokens: number;
            /** Tools */
            tools: number;
            /** Userturns */
            userTurns: number;
        };
        /**
         * SessionTree
         * @description Flat canonical Agent tree plus anchored read-only problem cards.
         */
        SessionTree: {
            /** Agents */
            agents: components["schemas"]["SessionAgent"][];
            /** Badcases */
            badCases: components["schemas"]["SessionBadCase"][];
            /** Runtimekey */
            runtimeKey: string;
            /** Sessionid */
            sessionId: string;
        };
        /**
         * SessionWorkspace
         * @description One workspace visible to the current user with its live aggregates.
         */
        SessionWorkspace: {
            /** Id */
            id: string;
            /** Mark */
            mark: string;
            /** Membercount */
            memberCount: number;
            /** Name */
            name: string;
            /** Quota */
            quota: number;
            /**
             * Role
             * @enum {string}
             */
            role: "global_admin" | "space_admin" | "member" | "viewer";
            /** Spaceadmincount */
            spaceAdminCount: number;
            /** Used */
            used: number;
        };
        /**
         * SessionsPreviewRequest
         * @description Session stage condition with 4 rows per page.
         */
        SessionsPreviewRequest: {
            /** From */
            from?: string | null;
            /**
             * Page
             * @default 1
             */
            page: number;
            /**
             * Pagesize
             * @default 4
             */
            pageSize: number;
            /** Targetname */
            targetName: string;
            /**
             * Targettype
             * @enum {string}
             */
            targetType: "skill" | "agent" | "knowledge";
            /** Targetversion */
            targetVersion?: string | null;
            /** To */
            to?: string | null;
        };
        /**
         * ShadowActual
         * @description Normalized engine output stored separately from Probe Reports.
         */
        ShadowActual: {
            /** Category */
            category: ("model" | "prompt" | "error" | "flow" | "context") | null;
            /**
             * Conclusion
             * @enum {string}
             */
            conclusion: "attributed" | "non_target" | "inconclusive";
            /** Confidence */
            confidence: number;
            /** Evidencereferences */
            evidenceReferences: string[];
            /** Summary */
            summary: string;
            /** Warnings */
            warnings: string[];
        };
        /**
         * ShadowCandidate
         * @description Exact engine and Skill snapshot evaluated without production writes.
         */
        ShadowCandidate: {
            /** Engine */
            engine: string;
            /**
             * Modelconfigfingerprint
             * @default none
             */
            modelConfigFingerprint: string;
            /** Skillcontent */
            skillContent: {
                [key: string]: unknown;
            };
            /** Skillcontenthash */
            skillContentHash: string;
            /** Skillexecutortype */
            skillExecutorType: string;
            /** Skillkey */
            skillKey: string;
            /** Skillrevision */
            skillRevision: number;
        };
        /**
         * ShadowCaseResult
         * @description One isolated case comparison; it is never a production attribution.
         */
        ShadowCaseResult: {
            actual: components["schemas"]["ShadowActual"] | null;
            /** Caseid */
            caseId: string;
            /** Categorymatch */
            categoryMatch: boolean;
            /** Conclusionmatch */
            conclusionMatch: boolean;
            /** Detectionpointhit */
            detectionPointHit: boolean;
            /** Error */
            error?: string | null;
            /** Evidencevalid */
            evidenceValid: boolean;
            expected: components["schemas"]["GoldenExpected"];
            /** Introductionpointhit */
            introductionPointHit: boolean;
            /** Latencyms */
            latencyMs: number;
            /** Safetypassed */
            safetyPassed: boolean;
            /** Scenario */
            scenario: string;
            /** Schemacompliant */
            schemaCompliant: boolean;
            /** Tokencount */
            tokenCount: number;
        };
        /**
         * ShadowEvaluationReport
         * @description Immutable quality artifact produced without touching production state.
         */
        ShadowEvaluationReport: {
            candidate: components["schemas"]["ShadowCandidate"];
            /** Evaluationhash */
            evaluationHash: string;
            /** Failedgates */
            failedGates: string[];
            /** Goldensethash */
            goldenSetHash: string;
            /** Goldensetid */
            goldenSetId: string;
            metrics: components["schemas"]["ShadowMetrics"];
            /** Passed */
            passed: boolean;
            /** Results */
            results: components["schemas"]["ShadowCaseResult"][];
            /**
             * Schemaversion
             * @default attribution-shadow-report/v1
             * @constant
             */
            schemaVersion: "attribution-shadow-report/v1";
            thresholds: components["schemas"]["GoldenThresholds"];
        };
        /**
         * ShadowMetrics
         * @description Aggregate quality, safety, cost, and runtime measurements.
         */
        ShadowMetrics: {
            /** Averagelatencyms */
            averageLatencyMs: number;
            /** Averagetokens */
            averageTokens: number;
            /** Categoryaccuracy */
            categoryAccuracy: number;
            /** Conclusionaccuracy */
            conclusionAccuracy: number;
            /** Detectionpointhitrate */
            detectionPointHitRate: number;
            /** Evidencevalidityrate */
            evidenceValidityRate: number;
            /** Failurerate */
            failureRate: number;
            /** Introductionpointhitrate */
            introductionPointHitRate: number;
            /** P95Latencyms */
            p95LatencyMs: number;
            /** Pointhitrate */
            pointHitRate: number;
            /** Safetyrate */
            safetyRate: number;
            /** Schemacompliancerate */
            schemaComplianceRate: number;
            /** Totalcases */
            totalCases: number;
        };
        /** SkillResourceDetail */
        SkillResourceDetail: {
            /** Files */
            files: string[];
            /** Prompt */
            prompt: string;
            /** Targets */
            targets: string[];
        };
        /**
         * SourceListResponse
         * @description Source distribution ordered by total descending, then object name.
         */
        SourceListResponse: {
            /** Items */
            items: components["schemas"]["SourceRow"][];
        };
        /**
         * SourceRow
         * @description One object's share of the window, split by bad-case type.
         */
        SourceRow: {
            /** Discovery */
            discovery: number;
            /** Object */
            object: string;
            /** Self */
            self: number;
            /** Sessions */
            sessions: number;
            /** Total */
            total: number;
        };
        /**
         * StepAttributionPayload
         * @description Attribution summary plus one row per included case.
         */
        StepAttributionPayload: {
            /** Rows */
            rows: components["schemas"]["StepAttributionRow"][];
            summary: components["schemas"]["StepAttributionSummary"];
        };
        /**
         * StepAttributionRow
         * @description One case attribution conclusion of step 4.
         *
         *     ``session_id`` is the source Session that owns the bad case. The client
         *     needs it to build the canonical error-detail deep link without a second
         *     lookup; rows without a Session cannot offer that link.
         */
        StepAttributionRow: {
            /** Attributionid */
            attributionId: string;
            /** Badcaseid */
            badCaseId: string;
            /** Category */
            category: ("model" | "prompt" | "error" | "flow" | "context") | null;
            /** Conclusion */
            conclusion?: ("attributed" | "non_target" | "inconclusive") | null;
            /** Confidence */
            confidence: number | null;
            /** Description */
            description: string;
            /** Sessionid */
            sessionId: string;
            /**
             * Source
             * @enum {string}
             */
            source: "cached" | "fresh";
        };
        /**
         * StepAttributionSummary
         * @description Four counts of the attribution step.
         */
        StepAttributionSummary: {
            /**
             * Fresh
             * @default 0
             */
            fresh: number;
            /**
             * Nontarget
             * @default 0
             */
            nonTarget: number;
            /**
             * Potential
             * @default 0
             */
            potential: number;
            /**
             * Reused
             * @default 0
             */
            reused: number;
        };
        /**
         * StepCandidate
         * @description Pushed candidate ref backing one evaluation round.
         */
        StepCandidate: {
            /** Commit */
            commit: string;
            /** Message */
            message: string;
            /** Ref */
            ref: string;
        };
        /**
         * StepCluster
         * @description One ranked cluster with its source cases and stored scores.
         */
        StepCluster: {
            /** Casecount */
            caseCount: number;
            /** Cases */
            cases: components["schemas"]["StepClusterCase"][];
            /**
             * Category
             * @enum {string}
             */
            category: "model" | "prompt" | "error" | "flow" | "context";
            /** Clusterid */
            clusterId: string;
            /** Confidence */
            confidence: number | null;
            /** Description */
            description: string;
            /** Rank */
            rank: number | null;
            /** Severity */
            severity: number | null;
            /** Title */
            title: string;
        };
        /**
         * StepClusterCase
         * @description One source bad case inside a cluster.
         */
        StepClusterCase: {
            /** Badcaseid */
            badCaseId: string;
            /** Badcasetype */
            badCaseType: string;
            /** Createdat */
            createdAt: string | null;
            /** Objectname */
            objectName: string;
            /** Title */
            title: string;
            /** Triggerat */
            triggerAt: string | null;
        };
        /**
         * StepClustersPayload
         * @description Clusters ordered by severity descending plus the AI-mode audit facts.
         *
         *     ``degraded`` lists the task keys a ``degrade`` policy replaced with
         *     deterministic fallbacks, so a degraded result is never presented as model
         *     participation. ``failure`` carries the sanitized run error when a strict
         *     policy failed the run at this step.
         */
        StepClustersPayload: {
            /** Algorithm */
            algorithm?: string | null;
            /** Clusters */
            clusters: components["schemas"]["StepCluster"][];
            /** Degraded */
            degraded?: string[];
            /** Failure */
            failure?: string | null;
            /** Failurepolicy */
            failurePolicy?: ("strict" | "degrade") | null;
        };
        /**
         * StepFinalChange
         * @description One accepted round inside the terminal modification list.
         */
        StepFinalChange: {
            /**
             * Category
             * @enum {string}
             */
            category: "model" | "prompt" | "error" | "flow" | "context";
            /** Clusterid */
            clusterId: string;
            /** Commit */
            commit: string;
            /** Reportcount */
            reportCount: number;
            /** Title */
            title: string;
        };
        /**
         * StepFinalCommit
         * @description Amended run-branch commit produced when a round was accepted.
         */
        StepFinalCommit: {
            /** Hash */
            hash: string;
            /** Message */
            message: string;
        };
        /**
         * StepFinalPayload
         * @description Terminal evaluation verdict with metrics and accepted changes.
         *
         *     The four verdict fields stay null until `evolution_finals` has a row, so an
         *     active final step cannot be mistaken for a failing verdict.
         */
        StepFinalPayload: {
            /** Bestscore */
            bestScore: number | null;
            /** Bestversion */
            bestVersion: string | null;
            /** Changes */
            changes: components["schemas"]["StepFinalChange"][];
            /**
             * Degraded
             * @default false
             */
            degraded: boolean;
            /** Initscore */
            initScore: number | null;
            /** Metrics */
            metrics: {
                [key: string]: unknown;
            }[];
            /** Verdict */
            verdict: boolean | null;
        };
        /**
         * StepIterationPayload
         * @description Rounds of step 6 in sequence order.
         */
        StepIterationPayload: {
            /** Rounds */
            rounds: components["schemas"]["StepRound"][];
        };
        /**
         * StepPotentialPayload
         * @description Paged potential rows; excluded rows stay in the summary only.
         */
        StepPotentialPayload: {
            /**
             * Page
             * @default 1
             */
            page: number;
            /**
             * Pagesize
             * @default 5
             */
            pageSize: number;
            /** Rows */
            rows: components["schemas"]["StepPotentialRow"][];
            summary: components["schemas"]["StepPotentialSummary"];
            /**
             * Total
             * @default 0
             */
            total: number;
        };
        /**
         * StepPotentialRow
         * @description One included bad case row of step 3.
         */
        StepPotentialRow: {
            /**
             * Anchorsource
             * @enum {string}
             */
            anchorSource: "event" | "node" | "post_process" | "unknown";
            /** Badcaseid */
            badCaseId: string;
            /** Badcasetype */
            badCaseType: string;
            /**
             * Hitreason
             * @enum {string}
             */
            hitReason: "self_report" | "after_object" | "both" | "policy_excluded" | "order_unknown";
            /** Objectname */
            objectName: string;
            /**
             * Orderstate
             * @enum {string}
             */
            orderState: "comparable" | "unknown";
            /** Sessionid */
            sessionId: string;
            /** Triggerat */
            triggerAt: string | null;
        };
        /**
         * StepPotentialSummary
         * @description Evaluated and included cases with the closed reason distribution.
         */
        StepPotentialSummary: {
            /**
             * Badcases
             * @default 0
             */
            badCases: number;
            byReason: components["schemas"]["PotentialReasonCounts"];
            /**
             * Potential
             * @default 0
             */
            potential: number;
        };
        /**
         * StepRangeCondition
         * @description Immutable selection snapshot shown on step 1.
         */
        StepRangeCondition: {
            /** Attributionpackageid */
            attributionPackageId?: string | null;
            /** Cacheenabled */
            cacheEnabled: boolean;
            /** From */
            from?: string | null;
            /** Policy */
            policy: {
                [key: string]: unknown;
            };
            /** Targetname */
            targetName: string;
            /**
             * Targetrevision
             * @description Resolved file-matching revision (digest:<sha256(body)>); null on historical runs that were created before content resolution.
             */
            targetRevision?: string | null;
            /**
             * Targettype
             * @enum {string}
             */
            targetType: "skill" | "agent" | "knowledge";
            /** Targetversion */
            targetVersion: string;
            /** To */
            to?: string | null;
            /** Workspaceid */
            workspaceId: string;
        };
        /**
         * StepRangePayload
         * @description Selection condition plus its headline statistics.
         */
        StepRangePayload: {
            condition: components["schemas"]["StepRangeCondition"];
            stats: components["schemas"]["StepRangeStats"];
        };
        /**
         * StepRangeStats
         * @description Headline counts of the selection step.
         */
        StepRangeStats: {
            /**
             * Badcases
             * @default 0
             */
            badCases: number;
            /**
             * Potential
             * @default 0
             */
            potential: number;
            /**
             * Sessions
             * @default 0
             */
            sessions: number;
        };
        /**
         * StepRound
         * @description One execution round rendered by the iteration step.
         */
        StepRound: {
            /** Accepted */
            accepted: boolean;
            candidate: components["schemas"]["StepCandidate"] | null;
            /** Casecount */
            caseCount: number;
            /** Cases */
            cases: components["schemas"]["StepClusterCase"][];
            /**
             * Category
             * @enum {string}
             */
            category: "model" | "prompt" | "error" | "flow" | "context";
            /** Clusterid */
            clusterId: string;
            /** Confidence */
            confidence: number | null;
            eval: components["schemas"]["StepRoundEval"];
            finalCommit?: components["schemas"]["StepFinalCommit"] | null;
            patch: components["schemas"]["StepRoundPatch"] | null;
            push: components["schemas"]["StepRoundPush"];
            /** Roundid */
            roundId: string;
            /** Severity */
            severity: number | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "patching" | "pushing" | "evaluating" | "deciding" | "accepted" | "rejected" | "skipped" | "failed";
            /** Title */
            title: string;
        };
        /**
         * StepRoundEval
         * @description External evaluation state stored on the round.
         */
        StepRoundEval: {
            /** Candidate */
            candidate: number | null;
            /** Current */
            current: number | null;
            /** Nextpollat */
            nextPollAt?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "evaluating" | "completed" | "failed" | "timeout";
        };
        /**
         * StepRoundFilePatch
         * @description One file inside a round's patch preview.
         */
        StepRoundFilePatch: {
            /** File */
            file: string;
            /** Lines */
            lines: string[];
            /**
             * Overwrite
             * @default false
             */
            overwrite: boolean;
        };
        /**
         * StepRoundPatch
         * @description Patch preview projected from the round's stored bundle.
         *
         *     The durable shape carries ``files[]`` plus ``note``/``intent``/``report``,
         *     and single-file rounds also keep the legacy ``file``/``lines`` keys. This
         *     read model is built from :func:`stored_bundle` instead of validating the
         *     raw dictionary, so a later writer field cannot break step 6 again.
         */
        StepRoundPatch: {
            /** Files */
            files: components["schemas"]["StepRoundFilePatch"][];
            /** Note */
            note?: string | null;
        };
        /**
         * StepRoundPush
         * @description Candidate push outcome stored on the round.
         */
        StepRoundPush: {
            /** Attempts */
            attempts: number;
            /** Error */
            error: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "pushing" | "succeeded" | "skipped" | "failed";
        };
        /**
         * StepSessionRow
         * @description One associated Session row of step 2.
         */
        StepSessionRow: {
            /**
             * Badcasecount
             * @default 0
             */
            badCaseCount: number;
            /** Objecttriggerat */
            objectTriggerAt: string | null;
            /**
             * Potentialcount
             * @default 0
             */
            potentialCount: number;
            /** Sessionid */
            sessionId: string;
            /** Short */
            short?: string | null;
            /** Title */
            title: string | null;
        };
        /**
         * StepSessionsPayload
         * @description Paged associated Session projection.
         */
        StepSessionsPayload: {
            /**
             * Page
             * @default 1
             */
            page: number;
            /**
             * Pagesize
             * @default 4
             */
            pageSize: number;
            /** Rows */
            rows: components["schemas"]["StepSessionRow"][];
            summary: components["schemas"]["StepSessionsSummary"];
            /**
             * Total
             * @default 0
             */
            total: number;
        };
        /**
         * StepSessionsSummary
         * @description Non-overlapping Session partition of step 2.
         */
        StepSessionsSummary: {
            /**
             * Associated
             * @default 0
             */
            associated: number;
            /**
             * Pending
             * @default 0
             */
            pending: number;
            /**
             * Reported
             * @default 0
             */
            reported: number;
            /**
             * Skipped
             * @default 0
             */
            skipped: number;
            /**
             * Versionunresolved
             * @default 0
             */
            versionUnresolved: number;
        };
        /**
         * SyncStatusError
         * @description Sanitized issue summary retained from the latest replay batch.
         */
        SyncStatusError: {
            /** Agentid */
            agentId?: string | null;
            /** Code */
            code: string;
            /** Lineno */
            lineNo?: number | null;
            /** Message */
            message: string;
            /** Sessionid */
            sessionId?: string | null;
        };
        /**
         * SyncTriggerResponse
         * @description Queued/reused job identity, or an explicit successful no-work result.
         */
        SyncTriggerResponse: {
            /** Jobid */
            jobId: string | null;
            /** Reused */
            reused: boolean;
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "reused" | "idle";
        };
        /**
         * TargetCaseItem
         * @description One potential case under one target version, with its attribution state.
         */
        TargetCaseItem: {
            /**
             * Attributionid
             * @description The probe id of the newest attribution for this target version.
             */
            attributionId?: string | null;
            /** Badcaseid */
            badCaseId: string;
            /**
             * Badcasetype
             * @enum {string}
             */
            badCaseType: "self" | "discovery";
            /**
             * Category
             * @description Attribution category; only present for the attributed state.
             */
            category?: ("model" | "prompt" | "error" | "flow" | "context") | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Objectname */
            objectName: string;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent" | "knowledge";
            /** Objectversion */
            objectVersion: string;
            /** Sessionid */
            sessionId: string;
            /**
             * Source
             * @description The object name the bad case was reported against.
             */
            source: string;
            /**
             * State
             * @enum {string}
             */
            state: "attributed" | "nonTarget" | "unanalyzed";
            /** Title */
            title: string;
        };
        /**
         * TargetCaseListResponse
         * @description One filtered page of potential cases plus its authoritative total.
         */
        TargetCaseListResponse: {
            /** Items */
            items: components["schemas"]["TargetCaseItem"][];
            /** Page */
            page: number;
            /** Pagesize */
            pageSize: number;
            /** Total */
            total: number;
        };
        /**
         * TargetDefinitionPreview
         * @description Source pinned to this target binding.
         */
        TargetDefinitionPreview: {
            /** Commit */
            commit: string;
            /** Path */
            path: string;
            /** Preview */
            preview: string;
        };
        /**
         * TargetDetailResponse
         * @description One target's version and source analysis under an independent filter.
         */
        TargetDetailResponse: {
            /** Bysource */
            bySource: components["schemas"]["TargetDetailSource"][];
            /** Byversion */
            byVersion: components["schemas"]["TargetDetailVersion"][];
            stats: components["schemas"]["TargetDetailStats"];
            target: components["schemas"]["TargetDetailTarget"];
        };
        /**
         * TargetDetailSource
         * @description One reported source and its potential cases inside the selected scope.
         */
        TargetDetailSource: {
            /** Distinctcases */
            distinctCases: number;
            /** Source */
            source: string;
            /** Total */
            total: number;
        };
        /**
         * TargetDetailStats
         * @description The detail card's four counters.
         */
        TargetDetailStats: {
            /** Distinctcases */
            distinctCases: number;
            /** Potential */
            potential: number;
            /** Sessions */
            sessions: number;
            /** Versions */
            versions: number;
        };
        /**
         * TargetDetailTarget
         * @description The configured target a detail card is about and every version it has.
         */
        TargetDetailTarget: {
            /** Defaultref */
            defaultRef: string;
            /** Objectname */
            objectName: string;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent" | "knowledge";
            /** Targetid */
            targetId: string;
            /** Versionoptions */
            versionOptions?: components["schemas"]["TargetVersionOption"][];
            /** Versions */
            versions: string[];
        };
        /**
         * TargetDetailVersion
         * @description One version's contribution inside the selected detail scope.
         */
        TargetDetailVersion: {
            /** Attributed */
            attributed: number;
            /** Commit */
            commit?: string | null;
            /** Nontarget */
            nonTarget: number;
            /** Potential */
            potential: number;
            /** Ref */
            ref?: string | null;
            /** Unanalyzed */
            unanalyzed: number;
            /** Version */
            version: string;
        };
        /**
         * TargetOverviewItem
         * @description One target's potential cases and their three-state attribution split.
         *
         *     ``potential`` counts one row per ``(badCaseId, targetVersion)`` pair, so the
         *     same bad case may contribute once for each version it is potential under;
         *     ``attributed + nonTarget + unanalyzed`` therefore always equals ``potential``.
         */
        TargetOverviewItem: {
            /** Attributed */
            attributed: number;
            /** Attributionskillname */
            attributionSkillName?: string | null;
            /**
             * Evolvable
             * @description Attributed plus unanalyzed potential rows; the list sort key.
             */
            evolvable: number;
            /** Nontarget */
            nonTarget: number;
            /** Objectname */
            objectName: string;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent" | "knowledge";
            /** Potential */
            potential: number;
            /** Sessions */
            sessions: number;
            /** Targetid */
            targetId: string;
            /** Unanalyzed */
            unanalyzed: number;
            /**
             * Versionoptions
             * @description Display evidence aligned with ``versions``; absent on older captures.
             */
            versionOptions?: components["schemas"]["TargetVersionOption"][];
            /**
             * Versions
             * @description Canonical version keys this target was observed at inside the window, plus its configured defaultRef, ordered by descending display label.
             */
            versions: string[];
        };
        /**
         * TargetOverviewListResponse
         * @description One target page plus the workspace-wide summary.
         */
        TargetOverviewListResponse: {
            /** Items */
            items: components["schemas"]["TargetOverviewItem"][];
            /** Page */
            page: number;
            /** Pagesize */
            pageSize: number;
            summary: components["schemas"]["TargetOverviewSummary"];
            /** Total */
            total: number;
        };
        /**
         * TargetOverviewSummary
         * @description Totals across every enabled target in the workspace and the window.
         */
        TargetOverviewSummary: {
            /** Attributed */
            attributed: number;
            /** Nontarget */
            nonTarget: number;
            /** Potential */
            potential: number;
            /**
             * Sessions
             * @description Sum of each target's associated Session count; a Session that contains several targets is counted once per target.
             */
            sessions: number;
            /** Targets */
            targets: number;
            /** Unanalyzed */
            unanalyzed: number;
        };
        /**
         * TargetTrendBucket
         * @description One continuous, zero-filled target trend bucket.
         */
        TargetTrendBucket: {
            /** Attributed */
            attributed: number;
            /**
             * Bucket
             * Format: date
             */
            bucket: string;
            /** Bytarget */
            byTarget: components["schemas"]["TargetTrendByTarget"][];
            /**
             * Label
             * @description MM-DD for day/week buckets, YYYY-MM for month buckets.
             */
            label: string;
            /** Nontarget */
            nonTarget: number;
            /** Unanalyzed */
            unanalyzed: number;
        };
        /**
         * TargetTrendByTarget
         * @description One target's contribution to one trend bucket.
         */
        TargetTrendByTarget: {
            /** Attributed */
            attributed: number;
            /** Nontarget */
            nonTarget: number;
            /** Objectname */
            objectName: string;
            /**
             * Objecttype
             * @enum {string}
             */
            objectType: "skill" | "agent" | "knowledge";
            /** Targetid */
            targetId: string;
            /** Unanalyzed */
            unanalyzed: number;
        };
        /**
         * TargetTrendMeta
         * @description The bucket-time policy the response actually applied.
         */
        TargetTrendMeta: {
            /**
             * Bucketpolicy
             * @description attributed and nonTarget rows use the attribution createdAt; unanalyzed rows use the bad case createdAt.
             */
            bucketPolicy: string;
        };
        /**
         * TargetTrendResponse
         * @description The continuous target trend series and its effective grain.
         */
        TargetTrendResponse: {
            /** Buckets */
            buckets: components["schemas"]["TargetTrendBucket"][];
            /**
             * Grain
             * @enum {string}
             */
            grain: "day" | "week" | "month";
            meta: components["schemas"]["TargetTrendMeta"];
            window: components["schemas"]["OverviewWindow"];
        };
        /**
         * TargetVersionOption
         * @description One selectable version: canonical identity plus its display evidence.
         *
         *     ``version`` stays the filter and match key (the body digest when known);
         *     ``ref`` and ``commit`` only feed the V2 prototype's ``ref + short commit``
         *     rendering. Historical versions without ref evidence keep ``ref`` null.
         */
        TargetVersionOption: {
            /** Commit */
            commit?: string | null;
            /** Ref */
            ref?: string | null;
            /** Version */
            version: string;
        };
        /**
         * TicketRequest
         * @description Run topics, optional workspace, and replay cursor bound to an event ticket.
         */
        TicketRequest: {
            /**
             * Lasteventid
             * @default 0
             */
            lastEventId: number;
            /** Topics */
            topics: string[];
            /** Workspaceid */
            workspaceId?: string | null;
        };
        /**
         * TrendBucket
         * @description One continuous, zero-filled trend bucket.
         */
        TrendBucket: {
            /**
             * Bucket
             * Format: date
             */
            bucket: string;
            /** Discovery */
            discovery: number;
            /**
             * Label
             * @description MM-DD for day/week buckets, YYYY-MM for month buckets.
             */
            label: string;
            /** Self */
            self: number;
            /** Total */
            total: number;
        };
        /**
         * TrendResponse
         * @description The continuous trend series plus the grain actually used.
         */
        TrendResponse: {
            /** Buckets */
            buckets: components["schemas"]["TrendBucket"][];
            /**
             * Grain
             * @description Effective grain: a day request longer than 92 days is served as week, and the response always states the grain its buckets use.
             * @enum {string}
             */
            grain: "day" | "week" | "month";
            window: components["schemas"]["OverviewWindow"];
        };
        /**
         * UnanalyzedBadCaseAnalysis
         * @description No attribution result exists for this problem.
         */
        UnanalyzedBadCaseAnalysis: {
            /** Attributetype */
            attributeType: ("model" | "prompt" | "error" | "flow" | "context") | null;
            /**
             * Displaystate
             * @constant
             */
            displayState: "unanalyzed";
            /** Probeid */
            probeId: string | null;
            /** Result */
            result: null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            status: "unanalyzed";
        };
        /**
         * UserListResponse
         * @description Small unpaginated administrator user list.
         */
        UserListResponse: {
            /** Items */
            items: components["schemas"]["PublicUser"][];
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /**
         * Workspace
         * @description Full workspace returned by the management API.
         */
        Workspace: {
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /** Knowledgeroots */
            knowledgeRoots: string[];
            /** Mark */
            mark: string;
            /** Membercount */
            memberCount: number;
            /** Name */
            name: string;
            /** Quota */
            quota: number;
            /** Spaceadmins */
            spaceAdmins: components["schemas"]["WorkspaceAdmin"][];
            /** Used */
            used: number;
        };
        /**
         * WorkspaceAdmin
         * @description Minimal identity of one workspace administrator on a workspace card.
         */
        WorkspaceAdmin: {
            /** Displayname */
            displayName: string;
            /** Id */
            id: string;
        };
        /**
         * WorkspaceBadCaseLabelConfiguration
         * @description One label rule set plus its current distinct assignment count.
         */
        WorkspaceBadCaseLabelConfiguration: {
            /** Assignedbadcasecount */
            assignedBadCaseCount: number;
            /** Items */
            items: string[];
        };
        /**
         * WorkspaceBadCaseLabelRequest
         * @description Complete replacement set for one workspace's accepted public labels.
         */
        WorkspaceBadCaseLabelRequest: {
            /** Items */
            items: string[];
        };
        /**
         * WorkspaceCreateRequest
         * @description Administrator-provisioned workspace with at least one initial space admin.
         */
        WorkspaceCreateRequest: {
            /** Knowledgeroots */
            knowledgeRoots?: string[];
            /**
             * Mark
             * @default
             */
            mark: string;
            /** Name */
            name: string;
            /** Quota */
            quota: number;
            /** Spaceadminids */
            spaceAdminIds: string[];
        };
        /**
         * WorkspaceCredential
         * @description One ingest credential without its one-time plaintext secret.
         */
        WorkspaceCredential: {
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /** Lastusedat */
            lastUsedAt: string | null;
            /** Prefix */
            prefix: string;
            /** Revokedat */
            revokedAt: string | null;
        };
        /**
         * WorkspaceCredentialCreated
         * @description One-time credential creation response; the plaintext is never persisted.
         */
        WorkspaceCredentialCreated: {
            /** Credential */
            credential: string;
            /** Credentialid */
            credentialId: string;
            /** Prefix */
            prefix: string;
        };
        /**
         * WorkspaceCredentialListResponse
         * @description Every credential row owned by one workspace, newest first.
         */
        WorkspaceCredentialListResponse: {
            /** Items */
            items: components["schemas"]["WorkspaceCredential"][];
        };
        /**
         * WorkspaceListResponse
         * @description Every workspace visible to the current user, newest first.
         */
        WorkspaceListResponse: {
            /** Items */
            items: components["schemas"]["Workspace"][];
        };
        /**
         * WorkspaceMember
         * @description One membership row with the joined user's public identity.
         */
        WorkspaceMember: {
            /** Displayname */
            displayName: string;
            /**
             * Joinedat
             * Format: date-time
             */
            joinedAt: string;
            /**
             * Role
             * @enum {string}
             */
            role: "viewer" | "member" | "space_admin";
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Userid */
            userId: string;
            /** Username */
            username: string;
            /** Workspaceid */
            workspaceId: string;
        };
        /**
         * WorkspaceMemberCandidate
         * @description One non-member user returned by the server-side candidate search.
         */
        WorkspaceMemberCandidate: {
            /** Active */
            active: boolean;
            /** Displayname */
            displayName: string;
            /** Id */
            id: string;
            /** Username */
            username: string;
        };
        /**
         * WorkspaceMemberCandidateListResponse
         * @description Bounded candidate page that never exposes the global user directory.
         */
        WorkspaceMemberCandidateListResponse: {
            /** Items */
            items: components["schemas"]["WorkspaceMemberCandidate"][];
        };
        /**
         * WorkspaceMemberCreateRequest
         * @description Add one existing user to a workspace at an allowed role.
         */
        WorkspaceMemberCreateRequest: {
            /**
             * Role
             * @enum {string}
             */
            role: "viewer" | "member" | "space_admin";
            /** Userid */
            userId: string;
        };
        /**
         * WorkspaceMemberListResponse
         * @description Members of one workspace ordered by role and join time.
         */
        WorkspaceMemberListResponse: {
            /** Items */
            items: components["schemas"]["WorkspaceMember"][];
        };
        /**
         * WorkspaceMemberUpdateRequest
         * @description Change one existing membership's role.
         */
        WorkspaceMemberUpdateRequest: {
            /**
             * Role
             * @enum {string}
             */
            role: "viewer" | "member" | "space_admin";
        };
        /**
         * WorkspaceUpdateRequest
         * @description Partial workspace update; field-level permission is enforced by the service.
         */
        WorkspaceUpdateRequest: {
            /** Knowledgeroots */
            knowledgeRoots?: string[] | null;
            /** Mark */
            mark?: string | null;
            /** Name */
            name?: string | null;
            /** Quota */
            quota?: number | null;
        };
        /**
         * AttributionSkillRevision
         * @description Resolved Skill identity that can invalidate cached attribution output.
         */
        app__service__evolution__attribution_contracts__AttributionSkillRevision: {
            /** Contenthash */
            contentHash: string;
            /** Key */
            key: string;
            /** Revision */
            revision: string;
        };
        /**
         * AttributionSkillRevision
         * @description Public immutable Skill revision.
         */
        app__service__evolution__attribution_skills__AttributionSkillRevision: {
            /** Builtin */
            builtIn: boolean;
            /** Content */
            content: {
                [key: string]: unknown;
            };
            /** Contenthash */
            contentHash: string;
            /** Description */
            description: string;
            /** Displayname */
            displayName: string;
            /** Enabled */
            enabled: boolean;
            /** Executortype */
            executorType: string;
            /** Id */
            id: string;
            /** Outputschemaversion */
            outputSchemaVersion: string;
            /** Qualitystatus */
            qualityStatus: string;
            /** Revision */
            revision: number;
            /** Skillid */
            skillId: string;
            /** Skillkey */
            skillKey: string;
            /** Status */
            status: string;
            /** Workspaceid */
            workspaceId: string | null;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    trigger_pull_api_acquisition_pull_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PullJobPayload"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PullResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Admin role is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Upstream is not configured */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Selector validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    acquisition_status_api_acquisition_status_get: {
        parameters: {
            query?: {
                workspaceId?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AcquisitionStatusResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    trigger_sync_api_acquisition_sync_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description No pending payloads; no job was created */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SyncTriggerResponse"];
                };
            };
            /** @description A sync job was queued or an active job was reused */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SyncTriggerResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Admin role is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    app_config_api_app_config_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AppConfigResponse"];
                };
            };
        };
    };
    callback_api_auth_callback_get: {
        parameters: {
            query?: {
                code?: string | null;
                state?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Redirect to the web application with a refresh cookie */
            302: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Authentication state is invalid */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The provider rejected the grant */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description No local user is mapped */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description No external identity provider is configured */
            501: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The identity provider exchange failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    change_password_api_auth_change_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangePasswordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    login_api_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginResponse"];
                };
            };
            /** @description Invalid username or password */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Account is inactive */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Too many login attempts */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    logout_api_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    me_api_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicUser"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    refresh_api_auth_refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RefreshResponse"];
                };
            };
            /** @description Refresh token is invalid or expired */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Account is inactive */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    session_api_auth_session_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionPayload"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_bad_case_api_bad_cases__badCaseId__get: {
        parameters: {
            query?: {
                sessionId?: string | null;
            };
            header?: never;
            path: {
                badCaseId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BadCase"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Problem does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Problem belongs to another Session or its Session is still syncing */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Problem Session is not available yet */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_bad_case_analysis_api_bad_cases__badCaseId__analysis_get: {
        parameters: {
            query?: {
                sessionId?: string | null;
            };
            header?: never;
            path: {
                badCaseId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BadCaseAnalysis"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Problem does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Problem belongs to another Session or its Session is still syncing */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Problem Session is not available yet */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_model_catalog_api_catalogs_models_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogModels"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_target_catalog_api_catalogs_targets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogTargets"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Configured remote is unavailable */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    event_stream_api_events_get: {
        parameters: {
            query?: {
                ticket?: string | null;
            };
            header?: {
                "Last-Event-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Server-Sent Event frames for authorized run topics */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": {
                        /** Data */
                        data: {
                            [key: string]: unknown;
                        };
                        /**
                         * Event
                         * @enum {string}
                         */
                        event: "ping" | "run.event" | "run.progress" | "run.blocked" | "run.resumed" | "run.completed" | "run.failed" | "run.interrupted" | "reset";
                        /** Id */
                        id?: string | null;
                    };
                };
            };
            /** @description Event ticket is invalid or expired */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Replay cursor is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    issue_ticket_api_events_ticket_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TicketRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EventTicketResponse"];
                };
            };
            /** @description Authentication or ticket input is invalid */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_cluster_preview_api_evolution_cluster_previews_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProbeQueryRequest"];
            };
        };
        responses: {
            /** @description Cluster-only run accepted */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunAccepted"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target unconfigured or no probe hits */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Launch condition is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    query_probe_hits_api_evolution_probes_query_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProbeQueryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProbeQueryResult"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target unconfigured or no probe hits */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Launch condition is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_runs_api_evolution_runs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionRunList"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_run_api_evolution_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProbeQueryRequest"];
            };
        };
        responses: {
            /** @description Full run accepted */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunAccepted"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target unconfigured or no probe hits */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Launch condition is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    read_run_api_evolution_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionRunDetail"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_attribution_jobs_api_evolution_runs__run_id__attribution_jobs_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionJobList"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or the step has not been reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_attribution_job_api_evolution_runs__run_id__attribution_jobs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionJobView"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or the step has not been reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_attribution_job_api_evolution_runs__run_id__attribution_jobs__job_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionJobView"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or the step has not been reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    retry_attribution_job_api_evolution_runs__run_id__attribution_jobs__job_id__retry_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionJobView"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or the step has not been reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_run_events_api_evolution_runs__run_id__events_get: {
        parameters: {
            query?: {
                afterSeq?: number;
                limit?: number;
                level?: ("info" | "warn" | "error") | null;
            };
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionRunEventPage"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    retry_run_api_evolution_runs__run_id__retry_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Blocked-run retry accepted */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionRetryAccepted"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is not blocked or another stage job is active */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_attribution_step_api_evolution_runs__run_id__steps_attribution_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionStepAttribution"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or the step has not been reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_clusters_step_api_evolution_runs__run_id__steps_clusters_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionStepClusters"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or the step has not been reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_final_step_api_evolution_runs__run_id__steps_final_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionStepFinal"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or the step has not been reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_iteration_step_api_evolution_runs__run_id__steps_iteration_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionStepIteration"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or the step has not been reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_potential_step_api_evolution_runs__run_id__steps_potential_get: {
        parameters: {
            query?: {
                page?: number;
                pageSize?: number;
            };
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionStepPotential"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or the step has not been reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_range_step_api_evolution_runs__run_id__steps_range_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionStepRange"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or the step has not been reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_sessions_step_api_evolution_runs__run_id__steps_sessions_get: {
        parameters: {
            query?: {
                page?: number;
                pageSize?: number;
            };
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionStepSessions"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or the step has not been reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_targets_api_evolution_targets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionTargetList"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_target_api_evolution_targets_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvolutionTargetWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionTarget"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Administrator role is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Object pair already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target, remote, or test project id is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_target_api_evolution_targets__targetId__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                targetId: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvolutionTargetWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionTarget"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Administrator role is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Object pair already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target, remote, or test project id is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_target_api_evolution_targets__targetId__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                targetId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Administrator role is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target has an active run */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target id is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_target_versions_api_evolution_targets__targetId__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                targetId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionTargetVersions"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Remote is unavailable */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    health_api_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    get_job_api_jobs__jobId__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                jobId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Job does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_probe_api_probes__probeId__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                probeId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProbeReport"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Probe does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_sessions_api_sessions_get: {
        parameters: {
            query?: {
                q?: string;
                status?: "all" | "ok" | "partial" | "fail" | "problem";
                sort?: "latest" | "userTurns" | "messages" | "agents";
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_session_api_sessions__sessionId__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sessionId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionListItem"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Session does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_session_bad_cases_api_sessions__sessionId__bad_cases_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sessionId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BadCaseListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Session does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_session_probes_api_sessions__sessionId__probes_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sessionId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProbeListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Session does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_session_tree_api_sessions__sessionId__tree_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sessionId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionTree"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Session does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_users_api_users_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Administrator role is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_user_api_users_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateUserRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicUser"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Administrator role is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Username already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed or the admin role is not assignable */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_workspaces_api_workspaces_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_workspace_api_workspaces_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkspaceCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Workspace"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Administrator role is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace name already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Quota or initial admin list is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_workspace_api_workspaces__wid__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkspaceUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Workspace"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Role cannot change this field */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace name already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Quota is below current usage */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_attribution_skill_packages_api_workspaces__wid__attribution_skill_packages_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionSkillPackageList"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Package or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill name already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description ZIP package exceeds a safety limit */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description ZIP or SKILL.md is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    upload_attribution_skill_package_api_workspaces__wid__attribution_skill_packages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_attribution_skill_package_api_workspaces__wid__attribution_skill_packages_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionSkillPackage"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Package or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill name already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description ZIP package exceeds a safety limit */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description ZIP or SKILL.md is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_package_detail_api_workspaces__wid__attribution_skill_packages__packageId__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                packageId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SkillResourceDetail"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Package or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill name already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description ZIP package exceeds a safety limit */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description ZIP or SKILL.md is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_attribution_skill_package_api_workspaces__wid__attribution_skill_packages__packageId__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                packageId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Package or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill name already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description ZIP package exceeds a safety limit */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description ZIP or SKILL.md is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    download_attribution_skill_package_api_workspaces__wid__attribution_skill_packages__packageId__download_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                packageId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Attribution Skill folder ZIP */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/zip": string;
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Package or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill name already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description ZIP package exceeds a safety limit */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description ZIP or SKILL.md is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_bad_case_labels_api_workspaces__wid__bad_case_labels_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceBadCaseLabelConfiguration"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    replace_bad_case_labels_api_workspaces__wid__bad_case_labels_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkspaceBadCaseLabelRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceBadCaseLabelConfiguration"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Label set is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_workspace_bad_cases_api_workspaces__wid__bad_cases_get: {
        parameters: {
            query?: {
                /** @description Inclusive Asia/Shanghai start date (YYYY-MM-DD). */
                from?: string | null;
                /** @description Inclusive Asia/Shanghai end date (YYYY-MM-DD). */
                to?: string | null;
                /** @description Quick range in days; only 7, 30, and 90 are accepted when it derives a boundary, and it is ignored when both from and to are supplied. Defaults to 90 when neither from nor to is supplied. */
                range?: 7 | 30 | 90;
                /** @description Object names to include. Repeat the parameter or pass a comma-separated value; empty means every object, and at most 50 distinct names are allowed. */
                objects?: string[] | null;
                /** @description Restrict the list to one bad-case type. */
                badCaseType?: "all" | "self" | "discovery";
                /** @description 1-based page number. */
                page?: number;
                /** @description Page size; defaults to 8. */
                pageSize?: number;
                /** @description Return every reported case regardless of date; the list's empty date filter sends this, and any from/to/range is then ignored. */
                allTime?: boolean;
            };
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OverviewBadCaseListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    ingest_bad_case_api_workspaces__wid__bad_cases_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BadCaseIngest"];
            };
        };
        responses: {
            /** @description The same workspace already owned badCaseId; upstream fields were replaced */
            200: {
                headers: {
                    /** @description Live count of bad cases owned by the workspace after this report, as a decimal integer in a string because HTTP header values are strings. */
                    "X-HE-Workspace-Used"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BadCaseIngestResponse"];
                };
            };
            /** @description A new bad case was created inside the workspace quota */
            201: {
                headers: {
                    /** @description Live count of bad cases owned by the workspace after this report, as a decimal integer in a string because HTTP header values are strings. */
                    "X-HE-Workspace-Used"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BadCaseIngestResponse"];
                };
            };
            /** @description The workspace credential is missing or invalid */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The credential belongs to a different workspace */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The quota is exhausted or badCaseId belongs to another workspace */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reported payload violates the contract */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_workspace_bad_case_api_workspaces__wid__bad_cases__badCaseId__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                badCaseId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BadCase"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace or problem does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Problem Session is still syncing */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Problem Session is not available yet */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_workspace_case_attributions_api_workspaces__wid__bad_cases__badCaseId__attributions_get: {
        parameters: {
            query?: {
                page?: number;
                pageSize?: number;
            };
            header?: never;
            path: {
                wid: string;
                badCaseId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionPage"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace or problem does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_workspace_case_attribution_api_workspaces__wid__bad_cases__badCaseId__attributions__attributionId__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                badCaseId: string;
                attributionId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionDetail"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace, problem, or attribution does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    read_model_catalog_api_workspaces__wid__catalogs_models_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogModels"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_target_catalog_api_workspaces__wid__catalogs_targets_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogTargets"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Configured remote is unavailable */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_credentials_api_workspaces__wid__credentials_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceCredentialListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_credential_api_workspaces__wid__credentials_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceCredentialCreated"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Three active credentials already exist */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revoke_credential_api_workspaces__wid__credentials__cid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                cid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Credential does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Credential id is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    bind_workspace_default_skill_api_workspaces__wid__evolution_attribution_skill_bindings_default_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AttributionSkillBindingWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EffectiveAttributionSkill"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    unbind_workspace_default_skill_api_workspaces__wid__evolution_attribution_skill_bindings_default_delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    rollback_workspace_default_skill_api_workspaces__wid__evolution_attribution_skill_bindings_default_rollback_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AttributionRollbackWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EffectiveAttributionSkill"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_attribution_skills_api_workspaces__wid__evolution_attribution_skills_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionSkillList"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_attribution_skill_api_workspaces__wid__evolution_attribution_skills_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AttributionSkillCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["app__service__evolution__attribution_skills__AttributionSkillRevision"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    decide_attribution_skill_quality_api_workspaces__wid__evolution_attribution_skills_revisions__revisionId__quality_decisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                revisionId: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AttributionQualityDecisionWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["app__service__evolution__attribution_skills__AttributionSkillRevision"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_attribution_skill_quality_events_api_workspaces__wid__evolution_attribution_skills_revisions__revisionId__quality_events_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                revisionId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionQualityHistory"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    evaluate_attribution_skill_revision_api_workspaces__wid__evolution_attribution_skills_revisions__revisionId__shadow_evaluations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                revisionId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionQualityEvaluation"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    set_attribution_skill_state_api_workspaces__wid__evolution_attribution_skills__skillId__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                skillId: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AttributionSkillStateWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    publish_attribution_skill_revision_api_workspaces__wid__evolution_attribution_skills__skillId__revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                skillId: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AttributionSkillRevisionWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["app__service__evolution__attribution_skills__AttributionSkillRevision"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_cluster_preview_api_workspaces__wid__evolution_cluster_previews_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProbeQueryRequest"];
            };
        };
        responses: {
            /** @description Cluster-only run accepted */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunAccepted"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target unconfigured or no probe hits */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Launch condition is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    preview_attribution_api_workspaces__wid__evolution_preview_attribution_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AttributionPreviewRequest"];
            };
        };
        responses: {
            /** @description Read-only cache reuse preview */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionPreviewResult"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace is unknown or invisible to the caller */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target is not configured, or no Session/potential matched */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Window, policy, version, or engine is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    preview_potential_api_workspaces__wid__evolution_preview_potential_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PotentialPreviewRequest"];
            };
        };
        responses: {
            /** @description Potential case page */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PotentialPreviewResult"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace is unknown or invisible to the caller */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target is not configured, or no Session/potential matched */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Window, policy, version, or engine is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    preview_sessions_api_workspaces__wid__evolution_preview_sessions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SessionsPreviewRequest"];
            };
        };
        responses: {
            /** @description Associated Session page */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionPreviewResult"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace is unknown or invisible to the caller */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target is not configured, or no Session/potential matched */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Window, policy, version, or engine is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_runs_api_workspaces__wid__evolution_runs_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionRunList"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_run_api_workspaces__wid__evolution_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProbeQueryRequest"];
            };
        };
        responses: {
            /** @description Full run accepted */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunAccepted"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target unconfigured or no probe hits */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Launch condition is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    read_run_api_workspaces__wid__evolution_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionRunDetail"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or out of workspace */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_attribution_jobs_api_workspaces__wid__evolution_runs__run_id__attribution_jobs_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionJobList"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown, out of workspace, or step not reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_attribution_job_api_workspaces__wid__evolution_runs__run_id__attribution_jobs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionJobView"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown, out of workspace, or step not reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_attribution_job_api_workspaces__wid__evolution_runs__run_id__attribution_jobs__job_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                run_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionJobView"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown, out of workspace, or step not reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    retry_attribution_job_api_workspaces__wid__evolution_runs__run_id__attribution_jobs__job_id__retry_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                run_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionJobView"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown, out of workspace, or step not reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_run_events_api_workspaces__wid__evolution_runs__run_id__events_get: {
        parameters: {
            query?: {
                afterSeq?: number;
                limit?: number;
                level?: ("info" | "warn" | "error") | null;
            };
            header?: never;
            path: {
                wid: string;
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionRunEventPage"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or out of workspace */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    pause_run_api_workspaces__wid__evolution_runs__run_id__pause_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionRunControl"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resume_run_api_workspaces__wid__evolution_runs__run_id__resume_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionRunControl"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    retry_run_api_workspaces__wid__evolution_runs__run_id__retry_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Blocked-run retry accepted */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionRetryAccepted"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown or out of workspace */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is not blocked or another stage job is active */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_step_api_workspaces__wid__evolution_runs__run_id__steps__key__get: {
        parameters: {
            query?: {
                page?: number;
                pageSize?: number;
            };
            header?: never;
            path: {
                wid: string;
                run_id: string;
                key: "range" | "sessions" | "potential" | "attribution" | "clusters" | "iteration" | "final";
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionStepRange"] | components["schemas"]["EvolutionStepSessions"] | components["schemas"]["EvolutionStepPotential"] | components["schemas"]["EvolutionStepAttribution"] | components["schemas"]["EvolutionStepClusters"] | components["schemas"]["EvolutionStepIteration"] | components["schemas"]["EvolutionStepFinal"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Password change is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Run is unknown, out of workspace, or step not reached */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_targets_api_workspaces__wid__evolution_targets_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionTargetList"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_target_api_workspaces__wid__evolution_targets_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvolutionTargetWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionTarget"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Space administrator is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Object pair already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target configuration is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_target_api_workspaces__wid__evolution_targets__targetId__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                targetId: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvolutionTargetWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionTarget"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Space administrator is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Object pair already exists */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target configuration is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_target_api_workspaces__wid__evolution_targets__targetId__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                targetId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Space administrator is required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target has an active run */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resolve_target_attribution_skill_api_workspaces__wid__evolution_targets__targetId__attribution_skill_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                targetId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EffectiveAttributionSkill"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    bind_target_attribution_skill_api_workspaces__wid__evolution_targets__targetId__attribution_skill_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                targetId: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AttributionSkillBindingWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EffectiveAttributionSkill"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    unbind_target_attribution_skill_api_workspaces__wid__evolution_targets__targetId__attribution_skill_delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                targetId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill, target, or workspace is missing */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill identity or revision conflicts */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Skill contract is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    read_versions_api_workspaces__wid__evolution_targets__targetId__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                targetId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvolutionTargetVersions"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Target does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Configured remote is unavailable */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_member_candidates_api_workspaces__wid__member_candidates_get: {
        parameters: {
            query?: {
                q?: string;
                limit?: number;
            };
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceMemberCandidateListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Search limit is out of range */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_members_api_workspaces__wid__members_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceMemberListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_member_api_workspaces__wid__members_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkspaceMemberCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceMember"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Space admins cannot grant space_admin */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description User is already a member */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description User or role is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    appoint_self_as_space_admin_api_workspaces__wid__members_self_admin_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceMember"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Only the global administrator may appoint itself */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_member_api_workspaces__wid__members__userId__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                userId: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkspaceMemberUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceMember"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Space admins cannot grant space_admin */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace or member does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Space-admin row or last admin is locked */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Role is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    remove_member_api_workspaces__wid__members__userId__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                userId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Space admins cannot remove space admins */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace or member does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The last space admin cannot be removed */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Member id is invalid */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_overview_sources_api_workspaces__wid__overview_sources_get: {
        parameters: {
            query?: {
                /** @description Inclusive Asia/Shanghai start date (YYYY-MM-DD). */
                from?: string | null;
                /** @description Inclusive Asia/Shanghai end date (YYYY-MM-DD). */
                to?: string | null;
                /** @description Quick range in days; only 7, 30, and 90 are accepted when it derives a boundary, and it is ignored when both from and to are supplied. Defaults to 90 when neither from nor to is supplied. */
                range?: 7 | 30 | 90;
                /** @description Object names to include. Repeat the parameter or pass a comma-separated value; empty means every object, and at most 50 distinct names are allowed. */
                objects?: string[] | null;
            };
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_overview_summary_api_workspaces__wid__overview_summary_get: {
        parameters: {
            query?: {
                /** @description Inclusive Asia/Shanghai start date (YYYY-MM-DD). */
                from?: string | null;
                /** @description Inclusive Asia/Shanghai end date (YYYY-MM-DD). */
                to?: string | null;
                /** @description Quick range in days; only 7, 30, and 90 are accepted when it derives a boundary, and it is ignored when both from and to are supplied. Defaults to 90 when neither from nor to is supplied. */
                range?: 7 | 30 | 90;
                /** @description Object names to include. Repeat the parameter or pass a comma-separated value; empty means every object, and at most 50 distinct names are allowed. */
                objects?: string[] | null;
            };
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OverviewSummary"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_overview_targets_api_workspaces__wid__overview_targets_get: {
        parameters: {
            query?: {
                /** @description Inclusive Asia/Shanghai start date (YYYY-MM-DD). */
                from?: string | null;
                /** @description Inclusive Asia/Shanghai end date (YYYY-MM-DD). */
                to?: string | null;
                /** @description Quick range in days; only 7, 30, and 90 are accepted when it derives a boundary, and it is ignored when both from and to are supplied. Defaults to 90 when neither from nor to is supplied. */
                range?: 7 | 30 | 90;
                /** @description 1-based page number. */
                page?: number;
                /** @description Page size; defaults to 5. */
                pageSize?: number;
            };
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TargetOverviewListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_overview_target_cases_api_workspaces__wid__overview_targets_cases_get: {
        parameters: {
            query?: {
                /** @description Inclusive Asia/Shanghai start date (YYYY-MM-DD). */
                from?: string | null;
                /** @description Inclusive Asia/Shanghai end date (YYYY-MM-DD). */
                to?: string | null;
                /** @description Quick range in days; only 7, 30, and 90 are accepted when it derives a boundary, and it is ignored when both from and to are supplied. Defaults to 90 when neither from nor to is supplied. */
                range?: 7 | 30 | 90;
                /** @description Evolution target ids to include. Repeat the parameter or pass a comma-separated value; empty means every enabled target. */
                targets?: string[] | null;
                /** @description Object names to include. Repeat the parameter or pass a comma-separated value; empty means every object, and at most 50 distinct names are allowed. */
                objects?: string[] | null;
                /** @description Attribution states to include: attributed, nonTarget, or unanalyzed. Repeat the parameter or pass a comma-separated value; empty means all. */
                states?: "attributed" | "nonTarget" | "unanalyzed";
                /** @description 1-based page number. */
                page?: number;
                /** @description Page size; defaults to 8. */
                pageSize?: number;
            };
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TargetCaseListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_overview_targets_trend_api_workspaces__wid__overview_targets_trend_get: {
        parameters: {
            query?: {
                /** @description Inclusive Asia/Shanghai start date (YYYY-MM-DD). */
                from?: string | null;
                /** @description Inclusive Asia/Shanghai end date (YYYY-MM-DD). */
                to?: string | null;
                /** @description Quick range in days; only 7, 30, and 90 are accepted when it derives a boundary, and it is ignored when both from and to are supplied. Defaults to 90 when neither from nor to is supplied. */
                range?: 7 | 30 | 90;
                /** @description Evolution target ids to include. Repeat the parameter or pass a comma-separated value; empty means every enabled target. */
                targets?: string[] | null;
                /** @description Attribution states to include: attributed, nonTarget, or unanalyzed. Repeat the parameter or pass a comma-separated value; empty means all. */
                states?: "attributed" | "nonTarget" | "unanalyzed";
                /** @description Requested trend grain: day, week, or month. A day request longer than 92 inclusive days is served as week and the response states the effective grain. */
                grain?: "day" | "week" | "month";
            };
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TargetTrendResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_overview_target_detail_api_workspaces__wid__overview_targets__targetId__detail_get: {
        parameters: {
            query?: {
                /** @description Inclusive Asia/Shanghai start date (YYYY-MM-DD). */
                from?: string | null;
                /** @description Inclusive Asia/Shanghai end date (YYYY-MM-DD). */
                to?: string | null;
                /** @description Quick range in days; only 7, 30, and 90 are accepted when it derives a boundary, and it is ignored when both from and to are supplied. Defaults to 90 when neither from nor to is supplied. */
                range?: 7 | 30 | 90;
                /** @description Target versions for one detail card. Repeat the parameter or pass a comma-separated value; empty selects the highest versionLimit versions. */
                versions?: string[] | null;
                /** @description Version count when versions is empty: 5, 10, 20, or 0 for all. */
                versionLimit?: 0 | 5 | 10 | 20;
            };
            header?: never;
            path: {
                wid: string;
                targetId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TargetDetailResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace or target does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_overview_trend_api_workspaces__wid__overview_trend_get: {
        parameters: {
            query?: {
                /** @description Inclusive Asia/Shanghai start date (YYYY-MM-DD). */
                from?: string | null;
                /** @description Inclusive Asia/Shanghai end date (YYYY-MM-DD). */
                to?: string | null;
                /** @description Quick range in days; only 7, 30, and 90 are accepted when it derives a boundary, and it is ignored when both from and to are supplied. Defaults to 90 when neither from nor to is supplied. */
                range?: 7 | 30 | 90;
                /** @description Requested trend grain: day, week, or month. A day request longer than 92 inclusive days is served as week and the response states the effective grain. */
                grain?: "day" | "week" | "month";
                /** @description Object names to include. Repeat the parameter or pass a comma-separated value; empty means every object, and at most 50 distinct names are allowed. */
                objects?: string[] | null;
            };
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TrendResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_workspace_sessions_api_workspaces__wid__sessions_get: {
        parameters: {
            query?: {
                /** @description Complete root Session ID. Surrounding whitespace is trimmed and the match is exact but case-insensitive; ID substrings and titles return an empty list. */
                q?: string;
                status?: "all" | "ok" | "partial" | "fail" | "problem";
                sort?: "latest" | "userTurns" | "messages" | "agents";
                limit?: number;
            };
            header?: never;
            path: {
                wid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_workspace_session_api_workspaces__wid__sessions__sessionId__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                sessionId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionListItem"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace or Session does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_workspace_session_bad_cases_api_workspaces__wid__sessions__sessionId__bad_cases_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                sessionId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BadCaseListResponse"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace or Session does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_workspace_session_tree_api_workspaces__wid__sessions__sessionId__tree_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wid: string;
                sessionId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionTree"];
                };
            };
            /** @description Authentication is required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace role is insufficient */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Workspace or Session does not exist */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
}
