'use strict';
/** Perform explicit ask and human-review actions through the existing harness. */
const fs = require('node:fs');
const path = require('node:path');
const { lifecycle } = require('./lifecycle-cli');
const { snapshot, askId } = require('./workspace-state');
const { Reader } = require('./file-access');
const { record, text } = require('./validate');

/** @typedef {{ask: string, revision: string, workspaceRevision: string, item: string, value: 'accepted' | 'changes'}} ReviewTicket */

/** Reject an outdated UI snapshot before a live action.
 * @param {string} workspace
 * @param {string} revision
 * @returns {import('./types').Snapshot}
 */
function current(workspace, revision) {
  const state = snapshot(workspace);
  if (state.revision !== revision) throw new Error('Workspace state changed. Refresh and review the current ask before trying again.');
  return state;
}

/** Coordinate user-confirmed mutations without running agents or feature checks. */
class Workflow {
  /** @param {import('./lifecycle-cli').Runtime} connection @param {string} storage */
  constructor(connection, storage) {
    this.connection = connection;
    this.storage = storage;
    this.busy = false;
  }

  /** Create a private request input and remove it after the CLI finishes.
   * @param {string} request
   * @param {(file: string) => Promise<unknown>} action
   * @returns {Promise<unknown>}
   */
  async requestFile(request, action) {
    text(request, 'Ask request');
    if (request.length > 20000) throw new Error('Ask request must be at most 20,000 characters.');
    fs.mkdirSync(this.storage, { recursive: true });
    const folder = fs.mkdtempSync(path.join(this.storage, 'request-'));
    const file = path.join(folder, 'request.txt');
    try {
      fs.writeFileSync(file, request, 'utf8');
      return await action(file);
    } finally {
      if (fs.existsSync(file)) fs.unlinkSync(file);
      fs.rmdirSync(folder);
    }
  }

  /** Describe where a request lands, using the harness's own recommendation, without creating anything.
   * @param {string} workspace
   * @param {string} request
   * @returns {Promise<{revision: string, activeAsk: string | null, verdict: string, why: string}>}
   */
  async describeAsk(workspace, request) {
    const state = snapshot(workspace);
    const result = record(await this.requestFile(request, file => lifecycle(this.connection, workspace, ['where', file])), 'Ask scope');
    current(workspace, state.revision);
    return { revision: state.revision, activeAsk: state.ask?.id || null, verdict: text(result.verdict, 'Scope verdict'), why: text(result.why, 'Scope reason') };
  }

  /** Serialize UI-owned mutations and release the lock on failure.
   * @param {() => Promise<import('./types').Snapshot>} action
   * @returns {Promise<import('./types').Snapshot>}
   */
  async mutate(action) {
    if (this.busy) throw new Error('Another UI operation is still running.');
    this.busy = true;
    try { return await action(); } finally { this.busy = false; }
  }

  /** Create and verify a real ask after the user confirms its target workspace.
   * @param {string} workspace
   * @param {string} revision
   * @param {string} slug
   * @param {string} request
   * @returns {Promise<import('./types').Snapshot>}
   */
  async createAsk(workspace, revision, slug, request) {
    return this.mutate(async () => {
      if (!/^[a-z0-9][a-z0-9-]{0,40}$/.test(slug)) throw new Error('Ask name must contain 1-41 lowercase letters, digits or hyphens.');
      current(workspace, revision);
      const result = record(await this.requestFile(request, file =>
        lifecycle(this.connection, workspace, ['contract', 'direct', slug, 'HVE creator', file])), 'Created ask');
      const created = askId(result.ask);
      const state = snapshot(workspace);
      if (state.ask?.id !== created) throw new Error(`Ask ${created} was created, but the active ask changed before verification. Inspect the project before continuing.`);
      return state;
    });
  }

  /** Make an existing ask the active one through the harness and verify the pointer.
   * @param {string} workspace
   * @param {string} ask
   * @returns {Promise<import('./types').Snapshot>}
   */
  async openAsk(workspace, ask) {
    return this.mutate(async () => {
      const result = record(await lifecycle(this.connection, workspace, ['open', askId(ask)]), 'Opened ask');
      const state = snapshot(workspace);
      if (result.active !== ask || state.ask?.id !== ask) throw new Error(`The harness did not make ${ask} the active ask.`);
      return state;
    });
  }

  /** Obtain a guarded core ticket for the exact review displayed to the user.
   * @param {string} workspace
   * @param {string} revision
   * @param {string} item
   * @param {'accepted' | 'changes'} value
   * @returns {Promise<ReviewTicket>}
   */
  async prepareReview(workspace, revision, item, value) {
    const state = current(workspace, revision);
    if (!state.ask) throw new Error('No active ask to review.');
    if (state.pendingPlanTicks) throw new Error('Plan checkboxes changed. Reconcile them through the harness before another review.');
    const review = state.reviews.find(row => row.item === item);
    if (!review) throw new Error('The review item is not in the active ask.');
    if (!['accepted', 'changes'].includes(value)) throw new Error('Unknown human review decision.');
    if (value === 'accepted' && (!review.ready || state.planState !== 'synced')) {
      throw new Error('Acceptance requires completed work, its required evidence, and a synchronized plan.');
    }
    const ticket = record(await lifecycle(this.connection, workspace, ['review-status', state.ask.id]), 'Review ticket');
    current(workspace, revision);
    if (ticket.ask !== state.ask.id) throw new Error('Harness returned a ticket for a different ask.');
    const coreRevision = text(ticket.revision, 'Review revision');
    if (!/^[a-f0-9]{64}$/.test(coreRevision)) throw new Error('Harness returned an invalid review revision.');
    return { ask: state.ask.id, revision: coreRevision, workspaceRevision: revision, item, value };
  }

  /** Persist a confirmed review through the guarded core API and verify its saved record.
   * @param {string} workspace
   * @param {ReviewTicket} ticket
   * @param {string} note
   * @returns {Promise<import('./types').Snapshot>}
   */
  async recordReview(workspace, ticket, note) {
    return this.mutate(async () => {
      text(note, 'Human review note');
      current(workspace, ticket.workspaceRevision);
      const result = record(await lifecycle(this.connection, workspace,
        ['tick-for', ticket.ask, ticket.revision, ticket.item, ticket.value, note]), 'Recorded review');
      if (result.ask !== ticket.ask || result.item !== ticket.item || result.value !== ticket.value) throw new Error('Harness returned a different review result.');
      const reader = new Reader(workspace);
      const saved = record(reader.json(path.join('.hve', 'asks', ticket.ask, 'contract.json')), 'Saved contract');
      const entry = record(record(saved.checklist, 'Saved checklist')[ticket.item], 'Saved review');
      if (entry.value !== ticket.value || entry.note !== note) throw new Error('Review response did not match the saved human decision.');
      return snapshot(workspace);
    });
  }
}

module.exports = { Workflow, current };
