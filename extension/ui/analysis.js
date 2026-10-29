'use strict';
/** Experimental chat analysis: list the Copilot models VS Code offers and ask one to review the chat on screen from its activity log. */
const vscode = require('vscode');
const { digest, analysisPrompt } = require('./insights');
const { errorText } = require('./validate');

/** @typedef {import('./mission-control').MissionControl} MissionControl */

/** Read the Copilot chat models this window may use; a failure shows on the Telemetry page.
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

/** Ask the chosen model for three crisp findings about the chat on screen, showing its answer as it streams in.
 * @param {MissionControl} mc
 * @param {string} id
 * @param {string} question
 * @returns {Promise<void>}
 */
async function analyze(mc, id, question) {
  if (mc.state.analysis?.status === 'running') throw new Error('An analysis is already running.');
  const run = mc.state.activity;
  const summary = mc.state.insights;
  if (!run?.session || !summary) throw new Error('There is no chat to analyse: start or choose a chat on the Live page first.');
  if (question.length > 1000) throw new Error('Keep the question under 1,000 characters.');
  const [model] = await vscode.lm.selectChatModels({ vendor: 'copilot', id });
  if (!model) throw new Error(`The model ${id} is not available in this window.`);
  const analysis = { model: model.name, question, chat: summary.chat, status: /** @type {import('./types').Analysis['status']} */ ('running'), text: '', at: new Date().toISOString() };
  mc.state.analysis = analysis;
  mc.paint();
  const cancel = new vscode.CancellationTokenSource();
  try {
    const response = await model.sendRequest([vscode.LanguageModelChatMessage.User(analysisPrompt(question, digest(run, summary)))],
      { justification: 'Frontier HVE Mission Control reviews the chat on screen from its activity log, at your request.' }, cancel.token);
    for await (const chunk of response.text) {
      analysis.text += chunk;
      mc.paint();
    }
    analysis.status = 'done';
  } catch (error) {
    analysis.status = 'error';
    analysis.text = `The analysis failed: ${errorText(error)}`;
    throw error;
  } finally {
    cancel.dispose();
    mc.paint();
  }
}

module.exports = { loadModels, analyze };
