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
         * @description Return durable acquisition progress for all authenticated users.
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
         * @description Return normalized model usage from the Agent table.
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
         * @description Return enabled evolution targets and their remote versions.
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
         * @description Admit a cluster-only preview run without workspace or evaluation.
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
         * @description Return backend-ordered running and history groups.
         */
        get: operations["list_runs_api_evolution_runs_get"];
        put?: never;
        /**
         * Create Run
         * @description Admit one full evolution run after synchronous validation.
         */
        post: operations["create_run_api_evolution_runs_post"];
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
         * @description Return every configured target, including disabled rows.
         */
        get: operations["list_targets_api_evolution_targets_get"];
        put?: never;
        /**
         * Create Target
         * @description Validate and create one administrator-managed target.
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
         * @description Report API reachability, delivery phase, and database health.
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
         * AttributeStats
         * @description Probe counts by attribution type shown in the wizard distribution bar.
         */
        AttributeStats: {
            /**
             * Error
             * @default 0
             */
            error: number;
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
         * BadCase
         * @description Complete public problem card used by list and detail routes.
         */
        BadCase: {
            analysis: components["schemas"]["BadCaseAnalysis"];
            anchor: components["schemas"]["BadCaseAnchor"];
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
         * BadCaseAnchor
         * @description Stable host Agent and event index for one problem card.
         */
        BadCaseAnchor: {
            /** Agentid */
            agentId: string;
            /** Eventindex */
            eventIndex: number;
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
        ErrorCode: "AUTH_REQUIRED" | "AUTH_INVALID" | "AUTH_EXPIRED" | "TICKET_INVALID" | "TICKET_EXPIRED" | "FORBIDDEN" | "PASSWORD_CHANGE_REQUIRED" | "USERNAME_CONFLICT" | "SESSION_NOT_FOUND" | "BAD_CASE_NOT_FOUND" | "BAD_CASE_SESSION_MISMATCH" | "PROBE_NOT_FOUND" | "JOB_NOT_FOUND" | "RUN_BUSY" | "REPO_INVALID" | "TARGET_EXISTS" | "TARGET_NOT_FOUND" | "TARGET_IN_USE" | "TARGET_NOT_CONFIGURED" | "NO_PROBES_MATCHED" | "INTERNAL" | "METHOD_NOT_ALLOWED" | "NOT_FOUND" | "VALIDATION_INVALID" | "RATE_LIMITED" | "UPSTREAM_NOT_AVAILABLE" | "UPSTREAM_VERSION_INCOMPATIBLE" | "UPSTREAM_INVALID_RESPONSE" | "UPSTREAM_REQUEST_FAILED";
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
         * EvolutionRunAttributeStats
         * @description Probe counts by externally supplied attribution type.
         */
        EvolutionRunAttributeStats: {
            /**
             * Error
             * @default 0
             */
            error: number;
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
         * EvolutionRunCard
         * @description One complete run-list card contract.
         */
        EvolutionRunCard: {
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Createdby */
            createdBy: string | null;
            error: components["schemas"]["EvolutionRunError"] | null;
            final: components["schemas"]["EvolutionRunFinal"] | null;
            /**
             * Mode
             * @enum {string}
             */
            mode: "full" | "cluster_only";
            /** Models */
            models: string[];
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
            /** Pushstatus */
            pushStatus: string;
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
         * @description Backend-normalized run statistics.
         */
        EvolutionRunStats: {
            byAttributeType: components["schemas"]["EvolutionRunAttributeStats"];
            /**
             * Clusters
             * @default 0
             */
            clusters: number;
            /**
             * Probes
             * @default 0
             */
            probes: number;
            /**
             * Sessions
             * @default 0
             */
            sessions: number;
            /**
             * Usedprobes
             * @default 0
             */
            usedProbes: number;
        };
        /**
         * EvolutionRunTarget
         * @description Immutable evolution target snapshot shown on one run card.
         */
        EvolutionRunTarget: {
            /** Name */
            name: string;
            /**
             * Type
             * @enum {string}
             */
            type: "skill" | "agent";
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
         * EvolutionTarget
         * @description Persisted target returned to clients.
         */
        EvolutionTarget: {
            /** Defaultref */
            defaultRef: string;
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
            objectType: "skill" | "agent";
            /** Repourl */
            repoUrl: string;
            /** Subdir */
            subDir: string;
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
            objectType: "skill" | "agent";
            /** Repourl */
            repoUrl: string;
            /** Subdir */
            subDir: string;
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
            attributeType: ("model" | "prompt" | "error") | null;
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
            kind: "sync" | "pull" | "evolution_prepare" | "evolution_advance" | "evolution_apply" | "evolution_finalize" | "evolution_retry";
            /** Progress */
            progress: number;
            /** Refid */
            refId: string | null;
            /** Startedat */
            startedAt: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "running" | "completed" | "failed" | "interrupted";
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
            attributeType: ("model" | "prompt" | "error") | null;
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
            attributeType: "model" | "prompt" | "error";
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
            /** Targetname */
            targetName: string;
            /**
             * Targettype
             * @enum {string}
             */
            targetType: "skill" | "agent";
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
            attributeType: ("model" | "prompt" | "error") | null;
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
            /** Agentid */
            agentId: string;
            /** Agenttype */
            agentType: string | null;
            /** Desc */
            desc: string;
            /** Events */
            events: components["schemas"]["SessionEvent"][];
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
        };
        /**
         * SessionEvent
         * @description One skill, Agent, or workflow trigger within an Agent node.
         */
        SessionEvent: {
            /** Desc */
            desc: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "skill" | "agent" | "workflow";
            /** Line */
            line: number;
            /** Messageoffset */
            messageOffset: number;
            /** Name */
            name: string | null;
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
            /** Id */
            id: string;
            /** Model */
            model: string | null;
            /** Repo */
            repo: string;
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
         * @description Current-page session cards.
         */
        SessionListResponse: {
            /** Items */
            items: components["schemas"]["SessionListItem"][];
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
            /** Sessionid */
            sessionId: string;
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
         * TicketRequest
         * @description Run topics and optional replay cursor bound to an event ticket.
         */
        TicketRequest: {
            /**
             * Lasteventid
             * @default 0
             */
            lastEventId: number;
            /** Topics */
            topics: string[];
        };
        /**
         * UnanalyzedBadCaseAnalysis
         * @description No attribution result exists for this problem.
         */
        UnanalyzedBadCaseAnalysis: {
            /** Attributetype */
            attributeType: ("model" | "prompt" | "error") | null;
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
            /** @description Problem belongs to another Session */
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
            /** @description Problem belongs to another Session */
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
            /** @description Target or remote is invalid */
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
            /** @description Target or remote is invalid */
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
