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
declare global {
  function acquireVsCodeApi(): {
    postMessage(message: unknown): void;
    getState(): unknown;
    setState(state: unknown): void;
  };
}
