/* This file is generated from packages/contracts/openapi.json. Do not edit. */
/** @generated */

export interface paths {
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
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
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
            /** Code */
            code: string;
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /** Message */
            message: string;
        };
        /**
         * ErrorResponse
         * @description Top-level failure response.
         */
        ErrorResponse: {
            error: components["schemas"]["ErrorBody"];
        };
        /**
         * HealthResponse
         * @description Public health-check contract.
         */
        HealthResponse: {
            db: components["schemas"]["DatabaseHealthResponse"];
            /**
             * Ok
             * @default true
             */
            ok: boolean;
            phase: components["schemas"]["ServicePhase"];
            /**
             * Service
             * @default harness-evolution
             * @constant
             */
            service: "harness-evolution";
            /** Version */
            version: string;
        };
        /**
         * ServicePhase
         * @description Delivery phase exposed by the health endpoint.
         * @enum {string}
         */
        ServicePhase: "scaffold" | "demo" | "live";
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
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
}
