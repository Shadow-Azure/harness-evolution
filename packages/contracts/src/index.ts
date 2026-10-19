/**
 * Shared contracts between the API and the web app.
 *
 * Domain types are intentionally kept out of the scaffold. They will be added
 * together with the corresponding API vertical slice.
 */

export type ServicePhase = "scaffold";

export interface HealthResponse {
  ok: boolean;
  service: "harness-evolution";
  phase: ServicePhase;
}
