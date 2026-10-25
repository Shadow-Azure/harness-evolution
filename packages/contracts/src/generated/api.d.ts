/* This file is generated from packages/contracts/openapi.json. Do not edit. */
/** @generated */

export interface paths {
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
        ErrorCode: "AUTH_REQUIRED" | "AUTH_INVALID" | "AUTH_EXPIRED" | "TICKET_INVALID" | "TICKET_EXPIRED" | "FORBIDDEN" | "PASSWORD_CHANGE_REQUIRED" | "USERNAME_CONFLICT" | "SESSION_NOT_FOUND" | "JOB_NOT_FOUND" | "RUN_BUSY" | "INTERNAL" | "METHOD_NOT_ALLOWED" | "NOT_FOUND" | "VALIDATION_INVALID" | "RATE_LIMITED";
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
