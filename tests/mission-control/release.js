'use strict';
/** Package the single Frontier HVE extension, inspect the VSIX, and check ordinary startup activation in an isolated real VS Code. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRequire } = require('node:module');
const { spawnSync } = require('node:child_process');
const EXTENSION = path.resolve(__dirname, '..', '..', 'extension');
const REPO = path.dirname(EXTENSION);
const { runTests, resolveCliPathFromVSCodeExecutablePath } = createRequire(path.join(EXTENSION, 'package.json'))('@vscode/test-electron');
const ORIGINAL = ['frontierHve.setup', 'frontierHve.installHarnesses', 'frontierHve.researchTelemetry', 'frontierHve.researchTelemetryOff',
  'frontierHve.installPlugin', 'frontierHve.managePlugins'];
const UI_FILES = ['mission-control.js', 'workspace-state.js', 'activity.js', 'workflow.js', 'lifecycle-cli.js', 'file-access.js', 'validate.js',
  'media/app.css', 'media/app.js', 'media/vnode.js', 'media/markdown.js', 'media/views.js', 'media/pages.js', 'media/hve.svg'];
const EXCLUDED = /(^|\/)node_modules\/|^package-lock\.json$|^tsconfig\.json$|^ui\/types\.d\.ts$|\.vsix$|^build\.py$|__pycache__\//;

/** Run a command and return its standard output, failing with its output when it exits non-zero.
 * @param {string} command
 * @param {string[]} args
 * @param {import('node:child_process').SpawnSyncOptions} [options]
 * @returns {string}
 */
function run(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, ...options });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} ${args.join(' ')} exited ${result.status}:\n${result.stdout}${result.stderr}`);
  return String(result.stdout);
}

/** Return every file below a folder as forward-slash paths relative to the extension.
 * @param {string} folder
 * @returns {string[]}
 */
function files(folder) {
  return fs.readdirSync(folder, { recursive: true, withFileTypes: true }).filter(entry => entry.isFile())
    .map(entry => path.relative(EXTENSION, path.join(entry.parentPath, entry.name)).split(path.sep).join('/'));
}

/** Build and package the extension, then check the VSIX keeps the original extension and adds Mission Control.
 * @param {string} out
 * @returns {{vsix: string, version: string, commands: string[]}}
 */
function packageAndInspect(out) {
  run('python', ['-B', path.join(EXTENSION, 'build.py')], { env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });
  const version = JSON.parse(fs.readFileSync(path.join(EXTENSION, 'package.json'), 'utf8')).version;
  const vsix = path.join(out, `frontier-hve-${version}.vsix`);
  run(process.execPath, [path.join(EXTENSION, 'node_modules', '@vscode', 'vsce', 'vsce'), 'package', '--skip-license',
    '--allow-missing-repository', '--out', vsix], { cwd: EXTENSION });
  const reader = 'import json, sys, zipfile\nz = zipfile.ZipFile(sys.argv[1])\nprint(json.dumps({"names": z.namelist(), '
    + '"manifest": json.loads(z.read("extension/package.json")), "lifecycle": z.read("extension/runtime/tools/loop/lifecycle.py").decode(), '
    + '"uplift": z.read("extension/skills/wow-uplift/SKILL.md").decode()}))';
  const packaged = JSON.parse(run('python', ['-c', reader, vsix]));
  const names = new Set(packaged.names.filter(name => name.startsWith('extension/')).map(name => name.slice('extension/'.length)));
  const missing = [...UI_FILES.map(file => `ui/${file}`), 'extension.js', 'render.js', 'packs.js',
    ...files(path.join(EXTENSION, 'runtime')), ...files(path.join(EXTENSION, 'agents')), ...files(path.join(EXTENSION, 'skills'))]
    .filter(file => !names.has(file));
  if (missing.length) throw new Error(`The VSIX is missing ${missing.length} extension files, for example ${missing.slice(0, 5).join(', ')}`);
  const leaked = [...names].filter(name => EXCLUDED.test(name));
  if (leaked.length) throw new Error(`The VSIX contains development files: ${leaked.slice(0, 5).join(', ')}`);
  if ([...names].filter(name => /^agents\/[^/]+\.agent\.md$/.test(name)).length !== 41) throw new Error('The VSIX must keep all 41 HVE agents.');
  if (packaged.lifecycle !== fs.readFileSync(path.join(REPO, 'tools', 'loop', 'lifecycle.py'), 'utf8') || !packaged.lifecycle.includes('tick-for')) {
    throw new Error('The packaged lifecycle runtime must match tools/loop/lifecycle.py, including the guarded review API.');
  }
  if (packaged.uplift !== fs.readFileSync(path.join(REPO, 'plugins', 'harness-assist', 'skills', 'wow-uplift', 'SKILL.md'), 'utf8')) {
    throw new Error('The packaged wow-uplift skill must be the current plugins/harness-assist/skills/wow-uplift/SKILL.md.');
  }
  const manifest = packaged.manifest;
  if (manifest.extensionDependencies !== undefined) throw new Error('The packaged extension must not depend on another extension.');
  const commands = manifest.contributes.commands.map(/** @param {{command: string}} item */ item => item.command);
  const absent = ORIGINAL.filter(id => !commands.includes(id));
  if (absent.length) throw new Error(`The packaged manifest lost original commands: ${absent.join(', ')}`);
  if (manifest.contributes.views.frontierHve[0].id !== 'frontierHve.missionControl') throw new Error('The packaged manifest has no Mission Control view.');
  return { vsix, version, commands };
}

/** Install the VSIX into an isolated profile and check startup activation with Copilot Chat disabled.
 * @param {string} root
 * @param {{vsix: string, version: string, commands: string[]}} release
 * @returns {Promise<Record<string, unknown>>}
 */
async function hostCheck(root, release) {
  const executable = process.env.HVE_VSCODE;
  if (!executable) throw new Error('Set HVE_VSCODE to a VS Code executable for the isolated host check; your own profile and extensions are not used.');
  const extensions = path.join(root, 'extensions');
  const profile = path.join(root, 'user-data');
  const project = path.join(root, 'pawstagram');
  fs.mkdirSync(path.join(profile, 'User'), { recursive: true });
  fs.mkdirSync(project);
  fs.writeFileSync(path.join(profile, 'User', 'settings.json'), JSON.stringify({
    'extensions.autoUpdate': false, 'extensions.autoCheckUpdates': false, 'extensions.ignoreRecommendations': true, 'update.mode': 'none',
    'telemetry.telemetryLevel': 'off', 'workbench.startupEditor': 'none', 'window.restoreWindows': 'none',
  }));
  const cli = resolveCliPathFromVSCodeExecutablePath(executable);
  const isolated = [`--extensions-dir=${extensions}`, `--user-data-dir=${profile}`];
  const shell = process.platform === 'win32';
  const quote = /** @param {string} value */ value => shell ? `"${value}"` : value;
  run(quote(cli), [...isolated, '--install-extension', release.vsix].map(quote), { shell });
  const installed = run(quote(cli), [...isolated, '--list-extensions', '--show-versions'].map(quote), { shell });
  if (!installed.includes(`muralim-ai2.frontier-hve@${release.version}`)) throw new Error(`The VSIX did not install:\n${installed}`);
  const runtime = path.join(extensions, `muralim-ai2.frontier-hve-${release.version}`, 'runtime', 'tools', 'loop', 'lifecycle.py');
  fs.writeFileSync(path.join(root, 'request.txt'), 'Build Pawstagram, a photo sharing app for pets.');
  run('python', ['-B', runtime, 'contract', 'direct', 'pawstagram', 'HVE creator', path.join(root, 'request.txt')],
    { cwd: project, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', HVE_PLUGIN_HOME: path.join(root, 'packs') } });
  const report = path.join(root, 'host-report.json');
  const code = await runTests({
    vscodeExecutablePath: executable,
    extensionDevelopmentPath: path.join(__dirname, 'host', 'runner'),
    extensionTestsPath: path.join(__dirname, 'host', 'index.js'),
    extensionTestsEnv: { HVE_HOST_REPORT: report, HVE_HOST_EXTENSIONS: extensions, HVE_HOST_COMMANDS: JSON.stringify(release.commands),
      HVE_HOST_UPLIFT: path.join(REPO, 'plugins', 'harness-assist', 'skills', 'wow-uplift', 'SKILL.md'),
      HVE_PLUGIN_HOME: path.join(root, 'packs'), PYTHONDONTWRITEBYTECODE: '1', VSCODE_PORTABLE: root },
    launchArgs: [project, '--user-data-dir', profile, '--extensions-dir', extensions, '--disable-extension', 'GitHub.copilot-chat',
      '--skip-welcome', '--skip-release-notes', '--skip-add-to-recently-opened', '--disable-workspace-trust', '--disable-telemetry'],
  });
  if (code !== 0) throw new Error(`The isolated VS Code host exited ${code}.`);
  return JSON.parse(fs.readFileSync(report, 'utf8'));
}

/** Run the release checks; the isolated run folder is kept for inspection because VS Code helpers release their files after exit.
 * @returns {Promise<void>}
 */
async function main() {
  const root = fs.mkdtempSync(path.join(fs.realpathSync.native(os.tmpdir()), 'hve-release-'));
  console.log(`Release check folder (kept for inspection; delete when done): ${root}`);
  const release = packageAndInspect(root);
  const report = await hostCheck(root, release);
  if (report.status !== 'passed') throw new Error('The isolated host did not record passing checks.');
  console.log(JSON.stringify({ vsix: path.basename(release.vsix), ...report }, null, 2));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
