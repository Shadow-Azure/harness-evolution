/** Scroll offsets for the two independently scrolling Session panels. */
export interface SessionScrollPosition {
  list: number;
  overview: number;
}

/**
 * In-memory per-Session scroll memory.
 *
 * Reload intentionally resets positions; browser history and card selection
 * within one SPA session restore them.
 */
export class SessionScrollMemory {
  private readonly positions = new Map<string, SessionScrollPosition>();

  /**
   * Save offsets for a Session.
   * @param sessionId Session identifier.
   * @param position Current list and overview offsets.
   * @returns Nothing.
   */
  save(sessionId: string, position: SessionScrollPosition): void {
    if (!sessionId) return;
    this.positions.set(sessionId, {
      list: Math.max(0, Math.round(position.list)),
      overview: Math.max(0, Math.round(position.overview)),
    });
  }

  /**
   * Read offsets for a Session.
   * @param sessionId Session identifier.
   * @returns Stored offsets or zeroes when none exist.
   */
  get(sessionId: string): SessionScrollPosition {
    return this.positions.get(sessionId) ?? { list: 0, overview: 0 };
  }

  /**
   * Check whether a Session has stored scroll offsets.
   * @param sessionId Session identifier.
   * @returns true when a position was saved.
   */
  has(sessionId: string): boolean {
    return this.positions.has(sessionId);
  }

  /**
   * Forget stale state for a removed Session.
   * @param sessionId Session identifier.
   * @returns Nothing.
   */
  forget(sessionId: string): void {
    this.positions.delete(sessionId);
  }
}
