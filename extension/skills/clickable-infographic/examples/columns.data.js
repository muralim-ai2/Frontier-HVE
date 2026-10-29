/* Example for layout 'columns': phases, a timeline, a comparison or categories. Copy over data.js to use. */
window.INFOGRAPHIC = {
  meta: {
    eyebrow: 'Sample · columns layout',
    title: 'From idea to release in four phases',
    sub: 'What each phase produces and what it needs before the next one starts.',
    mark: 'flag',
    foot: 'Select any box for details or the related document. Sample content.',
    exportFoot: 'Sample infographic · columns layout',
  },
  layout: 'columns',
  sequence: true, // arrows between column headers; false for comparisons
  kinds: {
    primary: { label: 'Phase', style: 'accent' },
    step: { label: 'Output', style: 'bar' },
    optional: { label: 'Optional', style: 'dashed' },
    planned: { label: 'Gate', style: 'muted' },
  },
  arrow: 'Then',
  columns: [
    { main: { id: 'c-disc', icon: 'search', title: 'Discover', via: 'Weeks 1-2', kind: 'primary', items: [['users', 'Interview users'], ['doc', 'Collect evidence']] },
      nodes: [
        { id: 'c-brief', icon: 'doc', title: 'Problem brief', via: 'One page', kind: 'step', detail: { text: '[What the brief contains.]' } },
        { id: 'c-notes', icon: 'folder', title: 'Research notes', via: 'Shared folder', kind: 'optional' },
        { id: 'c-g1', icon: 'check', title: 'Brief approved', via: 'Sponsor sign-off', kind: 'planned' },
      ],
      note: 'Ends when the problem is agreed.' },
    { main: { id: 'c-design', icon: 'grid', title: 'Design', via: 'Weeks 3-4', kind: 'primary', items: [['image', 'Sketch screens'], ['users', 'Test with users']] },
      nodes: [
        { id: 'c-proto', icon: 'image', title: 'Clickable prototype', via: 'Placeholder data', kind: 'step' },
        { id: 'c-spec', icon: 'doc', title: 'Design notes', via: 'Screens and states', kind: 'step' },
        { id: 'c-g2', icon: 'check', title: 'Design review', via: 'Team and users', kind: 'planned' },
      ],
      note: 'Ends when the flow tests well.' },
    { main: { id: 'c-build', icon: 'terminal', title: 'Build', via: 'Weeks 5-8', kind: 'primary', items: [['check', 'Tests per feature'], ['link', 'Small pull requests']] },
      nodes: [
        { id: 'c-feat', icon: 'bolt', title: 'Working features', via: 'Each one verified', kind: 'step' },
        { id: 'c-g4', icon: 'check', title: 'Code review', via: 'Every pull request', kind: 'planned' },
        { id: 'c-perf', icon: 'chart', title: 'Load test', via: 'If traffic is high', kind: 'optional' },
      ],
      note: 'Ends when every check passes.' },
    { main: { id: 'c-rel', icon: 'flag', title: 'Release', via: 'Week 9', kind: 'primary', items: [['shield', 'Security review'], ['mail', 'Announce']] },
      nodes: [
        { id: 'c-live', icon: 'cloud', title: 'Live service', via: 'Monitored', kind: 'step' },
        { id: 'c-docs', icon: 'doc', title: 'Release notes', via: 'For users', kind: 'step' },
        { id: 'c-g3', icon: 'check', title: 'Go-live approval', via: 'Owner sign-off', kind: 'planned' },
      ],
      note: 'Then measure and plan the next round.' },
  ],
};
