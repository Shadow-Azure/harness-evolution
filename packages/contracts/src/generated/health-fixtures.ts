/* This file is generated from packages/contracts/fixtures/health.json. Do not edit. */
/** @generated */

import type { HealthResponse } from "../index.js";

/** Canonical FastAPI health responses used to prove cross-stack payload compatibility. */
export const healthFixtures = {
  "healthy": {
    "db": {
      "dialect": "sqlite",
      "latencyMs": 0.1,
      "ok": true
    },
    "ok": true,
    "phase": "scaffold",
    "service": "harness-evolution",
    "version": "0.1.0"
  },
  "unavailable": {
    "db": {
      "dialect": "sqlite",
      "error": "OperationalError: database is unavailable",
      "latencyMs": 0.2,
      "ok": false
    },
    "ok": false,
    "phase": "scaffold",
    "service": "harness-evolution",
    "version": "0.1.0"
  }
} as const satisfies {
  healthy: HealthResponse;
  unavailable: HealthResponse;
};
