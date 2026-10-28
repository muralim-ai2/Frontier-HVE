'use strict';
/** Read the current harness project, evidence and sign-offs without reconciling or writing state. */
const path = require('node:path');
const { Reader, digest } = require('./file-access');
const { record, text, list, flag, integer } = require('./validate');
const { headline } = require('./activity');
const ASK = /^\d{8}-\d{4}-[a-z0-9][a-z0-9-]{0,40}$/;
const FEATURE = /^[a-z0-9][a-z0-9_-]{0,40}$/;
const SKILLS_BLOCK = /<!-- hve:skills -->\n?([\s\S]*?)<!-- \/hve:skills -->\n?/;
const CHECKLIST_BLOCK = /<!-- hve:checklist -->[\s\S]*?<!-- \/hve:checklist -->\n?/;

/** Validate a harness ask identifier.
 * @param {unknown} value
 * @returns {string}
 */
function askId(value) {
  const id = text(value, 'Ask identifier');
  if (!ASK.test(id)) throw new Error(`Invalid ask identifier: ${id}`);
  return id;
}

/** Return a validated feature name.
 * @param {unknown} value
 * @returns {string}
 */
function featureName(value) {
  const name = text(value, 'Feature name');
  if (!FEATURE.test(name)) throw new Error(`Invalid feature name: ${name}`);
  return name;
}

/** Read one feature's recorded pass or failed attempt.
 * @param {Reader} reader
 * @param {string} owner
 * @param {string} name
 * @param {string} command
 * @param {boolean} passes
 * @returns {import('./types').Check | null}
 */
function evidence(reader, owner, name, command, passes) {
  const folder = path.join('.hve', 'asks', owner, 'loop');
  const prPath = path.join(folder, 'prs', `${name}.json`);
  const pr = reader.json(prPath, true);
  if (passes && pr !== undefined) {
    const result = record(pr, prPath);
    if (result.feature !== name) throw new Error(`${prPath}: feature identity does not match.`);
    const verification = record(result.verify, `${prPath}: verify`);
    const recordedCommand = text(verification.command, 'Recorded check command');
    if (recordedCommand !== command) throw new Error(`${prPath}: recorded command differs from the feature check.`);
    return { exitCode: integer(verification.exit_code, 'Recorded exit code'), command, output: text(verification.output_tail, 'Check output', true), source: prPath };
  }
  const attemptsPath = path.join(folder, 'attempts', `${name}.jsonl`);
  const attempts = reader.text(attemptsPath, true);
  if (attempts === undefined || !attempts.trim()) return null;
  const rows = attempts.trim().split(/\r?\n/).map(line => record(JSON.parse(line), attemptsPath));
  const last = rows.filter(row => row.exit_code !== undefined).at(-1);
  if (!last) return null;
  return { exitCode: integer(last.exit_code, 'Attempt exit code'), command, output: text(last.output_tail, 'Attempt output', true), source: attemptsPath };
}

/** Read a stored human decision without treating missing decisions as acceptance.
 * @param {Record<string, unknown>} checklist
 * @param {string} item
 * @returns {{decision: string, note: string}}
 */
function decision(checklist, item) {
  if (!Object.hasOwn(checklist, item)) return { decision: 'open', note: '' };
  const entry = record(checklist[item], `Decision ${item}`);
  const value = text(entry.value, `Decision ${item} value`);
  if (!['accepted', 'changes', 'skipped'].includes(value)) throw new Error(`Invalid review decision for ${item}: ${value}`);
  return { decision: value, note: text(entry.note, `Decision ${item} note`, true) };
}

/** Compute the plan digest using the existing lifecycle's generated-block exclusions.
 * @param {string} plan
 * @returns {string | null}
 */
function planDigest(plan) {
  const body = plan.replace(/\r\n/g, '\n').replace(/<!-- hve:skills -->[\s\S]*?<!-- \/hve:skills -->\n?/g, '')
    .replace(/<!-- hve:checklist -->[\s\S]*?<!-- \/hve:checklist -->\n?/g, '').trim();
  return body ? digest(body) : null;
}

/** Read a complete immutable view of the workspace, showing the selected ask or, without a selection, the active ask.
 * @param {string} workspace
 * @param {string | null} [selected]
 * @returns {import('./types').Snapshot}
 */
function snapshot(workspace, selected = null) {
  const reader = new Reader(workspace);
  /** @type {import('./types').Snapshot} */
  const state = { workspace: reader.root, revision: '', project: null, ask: null, features: [], reviews: [], files: [],
    planState: 'missing', plan: null, pendingPlanTicks: false, decisions: [], skills: [], skillLoad: null, pluginSkills: [], options: [], stages: [] };
  const projectPath = path.join('.hve', 'project', 'project.json');
  const projectValue = reader.json(projectPath, true);
  /** @type {string[]} */
  let projectAsks = [];
  if (projectValue !== undefined) {
    const project = record(projectValue, projectPath);
    state.project = { name: text(project.name, 'Project name'), goal: text(project.goal, 'Project goal') };
    projectAsks = list(project.asks, 'Project asks').map(askId);
  }
  const activeValue = reader.json(path.join('.hve', 'asks', 'active.json'), true);
  const activeId = activeValue === undefined ? null : askId(record(activeValue, 'Active ask pointer').active);
  const shown = selected === null ? activeId : askId(selected);
  /** @type {Record<string, unknown> | null} */
  let contract = null;
  let askFolder = '';
  if (shown !== null) {
    if (!state.project || !projectAsks.includes(shown)) throw new Error(`Ask ${shown} is missing from the project record.`);
    askFolder = path.join('.hve', 'asks', shown);
    contract = record(reader.json(path.join(askFolder, 'contract.json')), 'Ask contract');
    if (contract.ask !== shown) throw new Error('Ask folder and contract identities differ.');
    state.ask = { id: shown, title: headline(text(contract.request, 'Ask request')), request: text(contract.request, 'Ask request'),
      agent: text(contract.agent, 'Ask agent'), lifecycle: text(contract.lifecycle, 'Ask lifecycle'), created: text(contract.created, 'Ask creation time'),
      current: contract.current === null ? null : text(contract.current, 'Current stage'), active: shown === activeId };
    const planFile = path.join(askFolder, 'plan.md');
    const plan = reader.text(planFile, true);
    if (plan !== undefined) {
      state.files.push(planFile);
      const current = planDigest(plan);
      const contractPlan = record(contract.plan, 'Contract plan');
      const recorded = contractPlan.sha256;
      if (recorded !== null) text(recorded, 'Recorded plan digest');
      state.planState = current === null ? 'missing' : current === recorded ? 'synced' : 'unsynced';
      const revisions = list(contractPlan.revisions, 'Plan revisions').map(row => record(row, 'Plan revision'));
      state.plan = { path: planFile.split(path.sep).join('/'), body: plan.replace(/\r\n/g, '\n').replace(SKILLS_BLOCK, '').replace(CHECKLIST_BLOCK, '').trim(),
        skills: (SKILLS_BLOCK.exec(plan.replace(/\r\n/g, '\n'))?.[1] || '').trim(),
        status: current === null ? 'empty' : recorded === null ? 'draft' : current === recorded ? 'agreed' : 'edited',
        revisions: revisions.length, agreedAt: revisions.length ? text(revisions[revisions.length - 1].ts, 'Plan revision time') : null };
      const rendered = record(contract.checklist_rendered, 'Rendered checklist');
      const block = /<!-- hve:checklist -->[\s\S]*?<!-- \/hve:checklist -->/.exec(plan);
      for (const match of (block ? block[0] : '').matchAll(/^- \[([ xX])\] ((?:opt|stage|task|gate):[\w.-]+)/gm)) {
        const prior = Object.hasOwn(rendered, match[2]) ? flag(rendered[match[2]], 'Rendered checkbox') : false;
        if ((match[1] !== ' ') !== prior) state.pendingPlanTicks = true;
      }
    }
    const requestFile = path.join(askFolder, 'request.md');
    reader.text(requestFile);
    state.files.push(requestFile);
    state.files.push(...reader.files(path.join(askFolder, 'loop', 'evidence')));
  }
  const featureValue = reader.json(path.join('.hve', 'project', 'feature_list.json'), true);
  const lockValue = reader.json(path.join('.hve', 'project', 'state.json'), true);
  const lock = lockValue === undefined ? null : record(record(lockValue, 'Loop state').lock, 'Feature lock');
  if (featureValue !== undefined) {
    state.features = list(featureValue, 'Project features').map(value => {
      const row = record(value, 'Feature');
      const name = featureName(row.name);
      const command = text(row.verify, `${name}: verify`);
      const passes = flag(row.passes, `${name}: passes`);
      const entry = lock ? record(lock[name], `${name}: feature lock`) : null;
      if (entry && entry.verify !== command) throw new Error(`${name}: check differs from its locked command.`);
      const owner = entry && entry.ask !== null ? askId(entry.ask) : null;
      if (owner && !projectAsks.includes(owner)) throw new Error(`${name}: owning ask is missing from the project.`);
      return { name, description: text(row.description, `${name}: description`), command, passes, ask: owner,
        check: owner ? evidence(reader, owner, name, command, passes) : null };
    });
    if (new Set(state.features.map(feature => feature.name)).size !== state.features.length) throw new Error('Duplicate feature names.');
    state.files.push(...state.features.flatMap(feature => feature.check ? [feature.check.source] : []));
  }
  if (contract) {
    const skills = record(contract.skills, 'Ask skills');
    state.skills = list(skills.selected, 'Selected skills').map(value => {
      const skill = record(value, 'Selected skill');
      return { name: text(skill.name, 'Skill name'), status: text(skill.status, 'Skill status'), reason: text(skill.reason, 'Skill selection reason'),
        why: typeof skill.why === 'string' ? skill.why : '', tokens: integer(skill.skill_tokens, 'Skill tokens') };
    });
    const budget = record(skills.budget, 'Skill budget');
    state.skillLoad = { tokens: integer(skills.tokens, 'Skill load tokens'), maxTokens: integer(budget.max_tokens, 'Token guideline'),
      maxSkills: integer(budget.max_skills, 'Skill limit'), overBudget: flag(skills.over_budget, 'Over budget'),
      choice: skills.choice ? text(record(skills.choice, 'Skill choice').choice, 'Skill choice') : null };
    const environment = record(contract.environment, 'Ask environment');
    state.pluginSkills = environment.plugin_skills === undefined ? [] : list(environment.plugin_skills, 'Plugin skills').map(value => text(value, 'Plugin skill'));
    const checklist = record(contract.checklist, 'Ask checklist');
    state.options = Object.keys(record(contract.checklist_rendered, 'Rendered checklist')).filter(item => item.startsWith('opt:') && item !== 'opt:telemetry')
      .map(item => ({ item, value: Object.hasOwn(checklist, item) ? text(record(checklist[item], item).value, `${item} value`) : 'not answered' }));
    state.stages = list(contract.stages, 'Ask stages').map(value => {
      const stage = record(value, 'Stage');
      const agent = text(stage.agent, 'Stage agent');
      return { name: text(stage.name, 'Stage name'), goal: text(stage.goal, 'Stage goal'), status: text(stage.status, 'Stage status'),
        persona: agent === 'self' ? text(contract.agent, 'Ask agent') : agent };
    });
    state.reviews = list(contract.stages, 'Ask stages').map(value => {
      const stage = record(value, 'Stage');
      const name = text(stage.name, 'Stage name');
      const status = text(stage.status, 'Stage status');
      if (!/^[\w.-]+$/.test(name) || !['planned', 'active', 'done', 'skipped'].includes(status)) throw new Error('Invalid stage identity or status.');
      const item = `stage:${name}`;
      return { item, title: text(stage.goal, 'Stage goal'), status, ready: status === 'done', ...decision(checklist, item) };
    }).filter(stage => stage.status !== 'skipped');
    for (const value of list(contract.tasks, 'Ask tasks')) {
      const task = record(value, 'Task');
      const name = featureName(task.name);
      const feature = state.features.find(row => row.name === name && row.ask === state.ask?.id);
      const passes = flag(task.passes, `${name}: task passes`);
      const item = `task:${name}`;
      state.reviews.push({ item, title: feature ? feature.description : name, status: passes ? 'marked passing' : 'pending',
        ready: passes && !!feature?.passes && feature.check?.exitCode === 0, ...decision(checklist, item) });
    }
    state.decisions = list(contract.decisions, 'Ask decisions').map(value => {
      const row = record(value, 'Decision');
      return { ts: text(row.ts, 'Decision timestamp'), stage: text(row.stage, 'Decision stage'),
        choice: text(row.choice, 'Decision choice'), why: text(row.why, 'Decision reason', true) };
    });
  }
  state.revision = reader.revision();
  return state;
}

module.exports = { askId, featureName, planDigest, snapshot };
