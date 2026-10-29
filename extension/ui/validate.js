'use strict';
/** Validate data crossing the harness and webview boundaries. */

/** Return a non-array object.
 * @param {unknown} value
 * @param {string} context
 * @returns {Record<string, unknown>}
 */
function record(value, context) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${context}: expected an object.`);
  return /** @type {Record<string, unknown>} */ (value);
}

/** Return a string, optionally allowing empty text.
 * @param {unknown} value
 * @param {string} context
 * @param {boolean} [allowEmpty]
 * @returns {string}
 */
function text(value, context, allowEmpty = false) {
  if (typeof value !== 'string' || (!allowEmpty && !value.trim())) throw new Error(`${context}: expected ${allowEmpty ? 'text' : 'non-empty text'}.`);
  return value;
}

/** Return an array.
 * @param {unknown} value
 * @param {string} context
 * @returns {unknown[]}
 */
function list(value, context) {
  if (!Array.isArray(value)) throw new Error(`${context}: expected an array.`);
  return value;
}

/** Return a boolean.
 * @param {unknown} value
 * @param {string} context
 * @returns {boolean}
 */
function flag(value, context) {
  if (typeof value !== 'boolean') throw new Error(`${context}: expected a boolean.`);
  return value;
}

/** Return an integer.
 * @param {unknown} value
 * @param {string} context
 * @returns {number}
 */
function integer(value, context) {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)) throw new Error(`${context}: expected an integer.`);
  return value;
}

/** Return an error's diagnostic text.
 * @param {unknown} error
 * @returns {string}
 */
function errorText(error) {
  return error instanceof Error ? error.message : String(error);
}

/** Return a strictly shaped webview action.
 * @param {unknown} value
 * @returns {Record<string, string>}
 */
function message(value) {
  const data = record(value, 'Webview message');
  const action = text(data.action, 'Webview action');
  /** @type {Record<string, string[]>} */
  const fields = {
    ready: [], refresh: [], selectWorkspace: [], newAsk: [], newChat: [], editPlan: [], loadPacks: [], revealAsk: [], attachReferences: [],
    openDashboard: ['page'], openFile: ['path'], command: ['name'], telemetry: ['value'], review: ['item', 'revision', 'value'],
    selectAsk: ['ask'], activateAsk: ['ask'], selectChat: ['chat'], linkChat: ['chat'],
  };
  if (!Object.hasOwn(fields, action)) throw new Error(`Unknown UI action: ${action}`);
  const expected = ['action', ...fields[action]];
  if (Object.keys(data).length !== expected.length || Object.keys(data).some(key => !expected.includes(key))) {
    throw new Error(`Unexpected fields for UI action: ${action}`);
  }
  return Object.fromEntries(expected.map(key => [key, text(data[key], `UI ${key}`)]));
}

module.exports = { record, text, list, flag, integer, errorText, message };
