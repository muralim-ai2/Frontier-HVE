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
  ask: { id: string; request: string; agent: string; lifecycle: string; current: string | null } | null;
  features: Feature[];
  reviews: Review[];
  files: string[];
  planState: 'missing' | 'unsynced' | 'synced';
  plan: Plan | null;
  pendingPlanTicks: boolean;
  skills: { name: string; status: string; reason: string }[];
  decisions: { ts: string; stage: string; choice: string; why: string }[];
}
export interface ViewState {
  snapshot: Snapshot | null;
  connection: string;
  python: string;
  guard: string;
  telemetry: boolean;
  busy: boolean;
  error: string | null;
  workspaceMessage: string | null;
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
}
export interface TokenUse {
  model: string;
  calls: number;
  failed: number;
  input: number;
  output: number;
  cached: number;
}
export interface Activity {
  session: Session | null;
  sessions: number;
  reason: string | null;
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
