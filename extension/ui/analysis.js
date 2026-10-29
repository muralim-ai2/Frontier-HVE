'use strict';
/** Experimental model reviews: list the Copilot models VS Code offers, review the chat on screen from its activity log, and summarize the ask's progress. */
const vscode = require('vscode');
const fs = require('node:fs');
const { digest, analysisPrompt } = require('./insights');
const { containedPath, boundedText } = require('./file-access');
const { errorText } = require('./validate');

/** @typedef {import('./mission-control').MissionControl} MissionControl */

/** Read the Copilot chat models this window may use; a failure shows where the models are offered.
 * @param {MissionControl} mc
 * @returns {Promise<void>}
 */
async function loadModels(mc) {
  try {
    const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
    const seen = new Set();
    mc.state.models = models.filter(model => !seen.has(model.id) && seen.add(model.id)).map(model => ({ id: model.id, name: model.name, family: model.family }));
    mc.state.modelsError = mc.state.models.length ? null : 'No Copilot models are available in this window. Sign in to GitHub Copilot, then open this page again.';
  } catch (error) {
    mc.state.models = null;
    mc.state.modelsError = errorText(error);
    mc.output.appendLine(`Chat models: ${mc.state.modelsError}`);
  }
  mc.paint();
}

/** Send one prompt to the chosen model and stream its answer into the view.
 * @param {MissionControl} mc
 * @param {string} id
 * @param {string} prompt
 * @param {import('./types').Analysis['topic']} topic
 * @param {string} subject
 * @param {string} question
 * @returns {Promise<void>}
 */
async function run(mc, id, prompt, topic, subject, question) {
  if (mc.state.analysis?.status === 'running') throw new Error('A model review is already running.');
  const [model] = await vscode.lm.selectChatModels({ vendor: 'copilot', id });
  if (!model) throw new Error(`The model ${id} is not available in this window.`);
  /** @type {import('./types').Analysis} */
  const analysis = { topic, model: model.name, question, chat: subject, status: 'running', text: '', at: new Date().toISOString() };
  mc.state.analysis = analysis;
  mc.paint();
  const cancel = new vscode.CancellationTokenSource();
  try {
    const response = await model.sendRequest([vscode.LanguageModelChatMessage.User(prompt)],
      { justification: 'Frontier HVE Mission Control reviews the chat or ask on screen, at your request.' }, cancel.token);
    for await (const chunk of response.text) {
      analysis.text += chunk;
      mc.paint();
    }
    analysis.status = 'done';
  } catch (error) {
    analysis.status = 'error';
    analysis.text = `The review failed: ${errorText(error)}`;
    throw error;
  } finally {
    cancel.dispose();
    mc.paint();
  }
}

/** Ask the chosen model for three crisp findings about the chat on screen.
 * @param {MissionControl} mc
 * @param {string} id
 * @param {string} question
 * @returns {Promise<void>}
 */
async function analyze(mc, id, question) {
  const activity = mc.state.activity;
  const summary = mc.state.insights;
  if (!activity?.session || !summary) throw new Error('There is no chat to analyse: start or choose a chat on the Live page first.');
  if (question.length > 1000) throw new Error('Keep the question under 1,000 characters.');
  await run(mc, id, analysisPrompt(question, digest(activity, summary)), 'chat', summary.chat, question);
}

/** Ask the chosen model for a three-bullet summary of the ask on screen from its state, provenance and latest evaluation.
 * @param {MissionControl} mc
 * @param {string} id
 * @returns {Promise<void>}
 */
async function summarize(mc, id) {
  const snap = mc.state.snapshot;
  if (!snap?.ask) throw new Error('There is no ask on screen to summarize.');
  const root = mc.target().uri.fsPath;
  /** @param {string} relative @param {number} limit @returns {string | null} */
  const read = (relative, limit) => { const file = containedPath(root, relative); return fs.existsSync(file) ? boundedText(file).slice(0, limit) : null; };
  const provenance = read(`.hve/asks/${snap.ask.id}/provenance.md`, 8000);
  const report = mc.state.evaluations.find(file => file.endsWith('report.json'));
  const evaluation = report ? read(report, 6000) : null;
  const passing = snap.features.filter(feature => feature.passes).length;
  const prompt = ['Summarize where this ask stands for its owner in exactly 3 bullets, one crisp sentence each: what is delivered against the plan, '
    + 'what the evaluation and checks say (or that none ran), and what the owner needs to do next. Use only the material below.',
  `Ask: ${snap.ask.title} (${snap.ask.id}), agent ${snap.ask.agent}, plan ${snap.plan ? snap.plan.status : 'none'}.`,
  `Stages: ${snap.stages.map(stage => `${stage.name} ${stage.status}`).join(', ') || 'none'}. Features passing: ${passing} of ${snap.features.length}.`,
  `Sign-offs: ${snap.reviews.map(review => `${review.item} ${review.decision}`).join(', ') || 'none'}.`,
  `Recent decisions: ${snap.decisions.slice(-8).map(decision => `${decision.stage}: ${decision.choice}`).join('; ') || 'none'}.`,
  provenance ? `provenance.md:\n${provenance}` : 'No provenance.md yet.', evaluation ? `Latest evaluation (${report}):\n${evaluation}` : 'No evaluation report yet.'].join('\n\n');
  await run(mc, id, prompt, 'progress', snap.ask.title, 'Where does this ask stand?');
}

module.exports = { loadModels, analyze, summarize };
