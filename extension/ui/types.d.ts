/** Data exchanged between Mission Control's host and its views. */
export interface Check {
  exitCode: number;
  command: string;
  output: string;
  source: string;
}
export interface Feature {
  name: string;
  description: string;
  command: string;
  passes: boolean;
  ask: string | null;
  check: Check | null;
}
export interface Review {
  item: string;
  title: string;
  status: string;
  decision: string;
  note: string;
  ready: boolean;
}
export interface Snapshot {
  workspace: string;
  revision: string;
  project: { name: string; goal: string } | null;
  ask: { id: string; title: string; request: string; agent: string; lifecycle: string; created: string; current: string | null; active: boolean } | null;
  features: Feature[];
  reviews: Review[];
  files: string[];
  planState: 'missing' | 'unsynced' | 'synced';
  plan: Plan | null;
  pendingPlanTicks: boolean;
  skills: { name: string; status: string; reason: string; why: string; tokens: number }[];
  skillLoad: { tokens: number; maxTokens: number; maxSkills: number; overBudget: boolean; choice: string | null } | null;
  pluginSkills: string[];
  options: { item: string; value: string }[];
  stages: { name: string; goal: string; status: string; persona: string }[];
  decisions: { ts: string; stage: string; choice: string; why: string }[];
}
export interface Pack {
  id: string;
  name: string;
  version: string;
  enabled: boolean;
  disabledReason: string | null;
  source: string;
  agents: string[];
  lifecycles: string[];
  knowledge: string[];
  templates: string[];
}
export type Page = 'live' | 'plan' | 'progress' | 'files' | 'others' | 'telemetry' | 'visuals' | 'skills' | 'settings';
export interface AskSummary {
  id: string;
  title: string;
  created: string;
  agent: string;
  stage: string | null;
  active: boolean;
}
export interface FileNode {
  name: string;
  path: string;
  kind: 'folder' | 'file' | 'other';
  size: number;
  modified: string;
  children: FileNode[];
}
export interface AskFiles {
  ask: string;
  path: string;
  entries: FileNode[];
  count: number;
  truncated: boolean;
}
export interface Claim {
  ask: string;
  how: 'started' | 'linked' | 'continued';
}
export interface Pending {
  ask: string;
  at: string;
}
export interface ChatLink {
  ask: string;
  how: 'started' | 'linked' | 'continued' | 'created' | 'opened' | 'edited';
}
export interface Chat {
  id: string;
  title: string | null;
  started: string;
  lastAt: string;
  status: 'working' | 'waiting' | 'idle';
  asks: ChatLink[];
}
export interface Signal {
  tone: 'error' | 'warn' | 'info';
  title: string;
  detail: string;
}
export interface Insights {
  chat: string;
  measured: boolean;
  agent: string | null;
  model: string | null;
  mode: string | null;
  context: { group: string; count: number; tokens: number; items: string[] }[];
  turns: number;
  toolCalls: number;
  commands: number;
  failures: number;
  skills: { count: number; names: string[]; tokens: number; measured: boolean };
  chatTokens: number;
  argTokens: number;
  thinkingTokens: number | null;
  input: number;
  output: number;
  total: number;
  aiu: number;
  signals: Signal[];
  method: string;
}
export interface ChatModelInfo {
  id: string;
  name: string;
  family: string;
}
export interface Analysis {
  topic: 'chat' | 'progress';
  model: string;
  question: string;
  chat: string;
  status: 'running' | 'done' | 'error';
  text: string;
  at: string;
}
export interface Handoff {
  title: string;
  description: string;
  from: string;
  at: string;
}
export interface Model {
  now: string;
  surface: 'sidebar' | 'editor';
  busy: boolean;
  error: string | null;
  workspace: { name: string; path: string } | null;
  workspaceMessage: string | null;
  connection: { version: string; python: string | null; guard: 'advise' | 'enforce' | null };
  telemetry: { enabled: boolean; file: string | null; bytes: number | null };
  transcripts: string | null;
  asks: AskSummary[] | null;
  asksError: string | null;
  snapshot: Snapshot | null;
  snapshotError: string | null;
  activity: Activity | null;
  activityError: string | null;
  pending: Pending | null;
  handoff: Handoff | null;
  handoffError: string | null;
  insights: Insights | null;
  models: ChatModelInfo[] | null;
  modelsError: string | null;
  analysis: Analysis | null;
  map: { built: string; bytes: number } | null;
  evaluations: string[];
  outputsError: string | null;
  files: AskFiles | null;
  filesError: string | null;
  packs: Pack[] | null;
  packsError: string | null;
  navigate: { page: Page; seq: number };
}
export interface UiState {
  page: Page;
  filter: 'all' | 'edits' | 'commands' | 'conversation' | 'problems';
  model?: string;
  question?: string;
  preset?: string;
  open: Record<string, boolean>;
  seq: number;
}
export interface Need {
  tone: 'error' | 'warn' | 'info';
  icon: string;
  title: string;
  detail: string;
  page?: string;
}
export interface Views {
  ICONS: Record<string, (string | { cx: number; cy: number; r: number })[]>;
  PAGES: [Page, string, string][];
  icon(name: string, extra?: string): VNode;
  ago(iso: string, now: number): string;
  count(value: number): string;
  plural(value: number, noun: string): string;
  pretty(slug: string): string;
  button(label: string, action: string, options?: { kind?: string; icon?: string; data?: Record<string, string>; disabled?: boolean; title?: string }): VNode;
  chip(model: Model): VNode;
  needs(model: Model): Need[];
  attention(items: Need[], compact: boolean): VNode | null;
  eventRow(event: ActivityEvent, now: number, compact: boolean): VNode;
  todoList(todos: Todo[], limit: number): VNode;
  bar(done: number, total: number, label: string): VNode;
  telemetrySwitch(model: Model): VNode;
  sessionState(model: Model): { key: string; label: string };
  askChats(model: Model): Chat[];
  noChat(model: Model): string;
  askPicker(model: Model): VNode | null;
  viewing(model: Model): VNode | null;
  handoffNotice(model: Model): VNode | null;
  sidebar(model: Model, ui: UiState, now: number): VNode;
}
export interface Pages {
  dashboard(model: Model, ui: UiState, now: number): VNode;
  live(model: Model, ui: UiState, now: number): Child[];
  plan(model: Model, ui: UiState, now: number): Child[];
  progress(model: Model, ui: UiState, now: number): Child[];
  files(model: Model, ui: UiState, now: number): Child[];
  others(model: Model, ui: UiState, now: number): Child[];
  telemetry(model: Model, ui: UiState, now: number): Child[];
  visuals(model: Model, ui: UiState, now: number): Child[];
  skills(model: Model): Child[];
  settings(model: Model): Child[];
}
export interface ActivityEvent {
  at: string;
  kind: 'prompt' | 'message' | 'read' | 'edit' | 'run' | 'search' | 'ask' | 'delegate' | 'todo' | 'guard' | 'tool';
  title: string;
  detail: string;
  files: string[];
  state: 'running' | 'ok' | 'failed' | 'stopped';
}
export interface Todo {
  title: string;
  status: 'not-started' | 'in-progress' | 'completed';
}
export interface Session {
  id: string;
  title: string | null;
  started: string;
  lastAt: string;
  status: 'working' | 'waiting' | 'idle';
  current: ActivityEvent | null;
  turns: number;
  tools: number;
  failures: number;
  commands: number;
  todos: Todo[];
  events: ActivityEvent[];
  files: { path: string; count: number; last: string }[];
  stats: SessionStats;
}
export interface SessionStats {
  chars: { user: number; agent: number; args: number };
  skills: { name: string; bytes: number }[];
  repeats: { title: string; count: number }[];
  gap: { from: string; to: string } | null;
  context: { group: string; count: number; bytes: number; items: string[] }[];
}
export interface TokenUse {
  model: string;
  calls: number;
  failed: number;
  input: number;
  output: number;
  cached: number;
  reasoning: number;
}
export interface ChatMeta {
  agent: string | null;
  model: string | null;
  mode: 'Local' | null;
}
export interface Activity {
  session: Session | null;
  chats: Chat[];
  meta: ChatMeta | null;
  errors: { paused: boolean; failures: { command: string; output: string }[] } | null;
  loadout: { skills: number; tokens: number; overBudget: boolean; maxSkills: number; maxTokens: number } | null;
  tokens: { models: TokenUse[]; aiu: number } | null;
}
declare global {
  function acquireVsCodeApi(): {
    postMessage(message: unknown): void;
    getState(): unknown;
    setState(state: unknown): void;
  };
  var hveVnode: {
    h(tag: string, attrs: Record<string, string | number | boolean | null | undefined> | null, ...children: Child[]): VNode;
    text(node: VNode | string): string;
    mount(node: VNode | string, doc: Document): Node;
  };
  var hveMarkdown: { render(source: string): VNode[]; inline(source: string): Child[] };
  var hveViews: Views;
  var hvePages: Pages;
  var hveTelemetry: { telemetry(model: Model, ui: UiState, now: number): Child[] };
}
export interface VNode {
  tag: string;
  attrs: Record<string, string>;
  children: (VNode | string)[];
}
export type Child = VNode | string | number | null | undefined | false | Child[];
export interface Plan {
  path: string;
  body: string;
  skills: string;
  status: 'empty' | 'draft' | 'agreed' | 'edited';
  revisions: number;
  agreedAt: string | null;
}
