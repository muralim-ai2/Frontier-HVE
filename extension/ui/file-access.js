'use strict';
/** Read bounded local harness files without following workspace links. */
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { errorText } = require('./validate');
const MAX_BYTES = 8 * 1024 * 1024;

/** Resolve a workspace-relative path and reject traversal and links.
 * @param {string} root
 * @param {string} relative
 * @returns {string}
 */
function containedPath(root, relative) {
  if (!relative || path.isAbsolute(relative) || relative.includes('\0')) throw new Error('Expected a workspace-relative file path.');
  const absolute = path.resolve(root, relative);
  const suffix = path.relative(root, absolute);
  if (!suffix || suffix === '..' || suffix.startsWith(`..${path.sep}`) || path.isAbsolute(suffix)) throw new Error('Path leaves the selected workspace.');
  let current = root;
  for (const component of suffix.split(path.sep)) {
    current = path.join(current, component);
    if (fs.existsSync(current) && fs.lstatSync(current).isSymbolicLink()) throw new Error(`Linked harness paths are not supported: ${relative}`);
  }
  return absolute;
}

/** Read a bounded UTF-8 file.
 * @param {string} file
 * @returns {string}
 */
function boundedText(file) {
  const stat = fs.statSync(file);
  if (!stat.isFile() || stat.size > MAX_BYTES) throw new Error(`Expected a regular file no larger than 8 MB: ${file}`);
  return fs.readFileSync(file, 'utf8');
}

/** Return a SHA-256 digest.
 * @param {string} content
 * @returns {string}
 */
function digest(content) {
  return createHash('sha256').update(content).digest('hex');
}

/** Collect a read-only snapshot fingerprint including absent optional files. */
class Reader {
  /** @param {string} workspace */
  constructor(workspace) {
    this.root = fs.realpathSync(workspace);
    /** @type {string[]} */
    this.fingerprints = [];
  }

  /** Read text and include its bytes in the snapshot fingerprint.
   * @param {string} relative
   * @param {boolean} [optional]
   * @returns {string | undefined}
   */
  text(relative, optional = false) {
    const file = containedPath(this.root, relative);
    if (!fs.existsSync(file) && optional) {
      this.fingerprints.push(`${relative}:absent`);
      return undefined;
    }
    const value = boundedText(file);
    this.fingerprints.push(`${relative}:${digest(value)}`);
    return value;
  }

  /** Read JSON or identify an absent optional file.
   * @param {string} relative
   * @param {boolean} [optional]
   * @returns {unknown}
   */
  json(relative, optional = false) {
    const value = this.text(relative, optional);
    if (value === undefined) return undefined;
    try {
      return /** @type {unknown} */ (JSON.parse(value));
    } catch (error) {
      throw new Error(`Invalid JSON in ${relative}: ${errorText(error)}`, { cause: error });
    }
  }

  /** List evidence files and fingerprint their content.
   * @param {string} relative
   * @returns {string[]}
   */
  files(relative) {
    const folder = containedPath(this.root, relative);
    if (!fs.existsSync(folder)) {
      this.fingerprints.push(`${relative}:absent`);
      return [];
    }
    /** @type {string[]} */
    const found = [];
    /** @param {string} directory @param {number} depth @returns {void} */
    const walk = (directory, depth) => {
      if (depth > 8) throw new Error('Evidence nesting exceeds the supported depth of 8.');
      for (const name of fs.readdirSync(containedPath(this.root, directory)).sort()) {
        const child = path.join(directory, name);
        const file = containedPath(this.root, child);
        const stat = fs.statSync(file);
        if (stat.isDirectory()) walk(child, depth + 1);
        else if (stat.isFile()) {
          if (stat.size > MAX_BYTES) throw new Error(`Evidence exceeds the 8 MB per-file preview limit: ${child}`);
          found.push(child);
          if (found.length > 500) throw new Error('This ask exceeds the 500-file evidence preview limit.');
          this.fingerprints.push(`${child}:${stat.size}:${stat.mtimeMs}:${stat.ctimeMs}`);
        } else throw new Error(`Unsupported evidence file type: ${child}`);
      }
    };
    walk(relative, 0);
    return found;
  }

  /** Return the revision of the files read for this snapshot.
   * @returns {string}
   */
  revision() { return digest(this.fingerprints.join('\n')); }
}

module.exports = { containedPath, boundedText, digest, Reader };
