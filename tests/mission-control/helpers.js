'use strict';
/** Provide disposable test workspaces and the bundled Mission Control runtime. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const EXTENSION = path.resolve(__dirname, '..', '..', 'extension');
const { runtime } = require('../../extension/ui/lifecycle-cli');
const TEMP = fs.realpathSync.native(os.tmpdir());
const PREFIX = 'hve-mission-control-';

/** Create a disposable workspace in the system temp folder.
 * @returns {string}
 */
function workspace() {
  return fs.mkdtempSync(path.join(TEMP, PREFIX));
}

/** Remove only a workspace created by this helper.
 * @param {string} folder
 * @returns {void}
 */
function removeWorkspace(folder) {
  if (path.dirname(folder) !== TEMP || !path.basename(folder).startsWith(PREFIX)) throw new Error(`Unsafe test cleanup path: ${folder}`);
  fs.rmSync(folder, { recursive: true, force: true });
}

/** Return the extension's bundled lifecycle runtime run by `python`.
 * @returns {import('../../extension/ui/lifecycle-cli').Runtime}
 */
function bundled() {
  return runtime(EXTENSION, ['python']);
}

/** Write JSON within a test workspace.
 * @param {string} root
 * @param {string} relative
 * @param {unknown} value
 * @returns {void}
 */
function json(root, relative, value) {
  const file = path.join(root, relative);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 2));
}

module.exports = { EXTENSION, workspace, removeWorkspace, bundled, json };
