/* SAMPLE CONTENT: replace everything in this object; keep the shape. Field guide: ../SKILL.md "Data schema". */
window.INFOGRAPHIC = {
  meta: {
    eyebrow: 'Sample · replace in data.js',
    title: 'How a support request gets resolved',
    sub: 'Where requests come in, what happens to them, and where they end.',
    mark: 'chat',
    foot: 'Select any box for details or the related document. Sample content.',
    exportFoot: 'Sample infographic · replace data.js with real content',
  },
  layout: 'lanes', // 'lanes' (flows, journeys, architectures) or 'columns' (phases, timelines, comparisons)
  // app: { page: '../index.html', themeParam: 'theme' }, // only when the subject has its own index.html; nodes then use `route`
  kinds: {
    primary: { label: 'Entry point', style: 'accent' },
    step: { label: 'Step', style: 'bar' },
    optional: { label: 'Optional', style: 'dashed' },
    planned: { label: 'Planned', style: 'muted' },
  },
  arrow: 'Leads to',
  rail: { title: 'Channels', foot: 'Where requests start' },
  lanes: [
    {
      entries: [{ id: 'r-mail', icon: 'mail', label: 'Email', to: 'n-inbox', start: 'Start here' }],
      main: {
        id: 'n-inbox', icon: 'mail', title: 'Shared inbox', via: 'Every email lands here', kind: 'primary', cap: 'Happens in place',
        items: [['flag', 'Tagged by topic'], ['grid', 'Duplicates merged'], ['clock', 'Priority set']],
        detail: { text: 'The shared inbox receives every request. [Describe the real behaviour here.]', links: [['Skill guide', '../SKILL.md']] },
      },
      rows: [
        { node: { id: 'n-assign', icon: 'user', title: 'Assign owner', via: 'Routed by topic', kind: 'step' },
          note: 'One owner per request. <b>Reassign</b> sends it back to the inbox.' },
        { node: { id: 'n-auto', icon: 'bolt', title: 'Auto-reply', via: 'After hours', kind: 'optional' },
          note: 'Confirms receipt. No owner yet.' },
        { node: { id: 'n-esc', icon: 'shield', title: 'Escalate', via: 'Highest priority only', kind: 'step' },
          chain: { id: 'n-oncall', icon: 'users', title: 'On-call team', via: 'Paged', kind: 'optional' },
          note: '<b>Resolve</b> or hand back to the owner.' },
      ],
    },
    {
      entries: [
        { id: 'r-chat', icon: 'chat', label: 'Chat', to: 'n-chat' },
        { id: 'r-form', icon: 'doc', label: 'Form', to: 'n-form' },
      ],
      direct: [
        { node: { id: 'n-chat', icon: 'chat', title: 'Live chat', via: 'Answered in the session', kind: 'step' }, note: 'Unresolved chats become an inbox request.' },
        { node: { id: 'n-form', icon: 'doc', title: 'Self-service form', via: 'Not built yet', kind: 'planned' }, note: '[Placeholder - to be designed]' },
      ],
    },
    {
      entries: [{ id: 'r-owner', icon: 'user', label: 'Owner', to: 'n-work' }],
      main: {
        id: 'n-work', icon: 'grid', title: 'Work queue', via: 'Owner\'s open requests', kind: 'primary', cap: 'Happens in place',
        items: [['chat', 'Reply and add notes'], ['link', 'Link related requests']],
      },
      rows: [
        { node: { id: 'n-resolve', icon: 'check', title: 'Resolve', via: 'Owner closes it', kind: 'step' },
          note: 'Customer is notified. <b>Reopen</b> returns it to the queue.' },
        { node: { id: 'n-survey', icon: 'star', title: 'Survey', via: 'Sent after closing', kind: 'optional' } },
      ],
    },
  ],
  panel: {
    icon: 'chart', title: 'Measures', sub: 'Shared by every channel',
    from: 'n-survey', label: 'Feeds',
    nodes: [
      { id: 'p-first', icon: 'clock', title: 'First response', via: '[target - to be confirmed]' },
      { id: 'p-resolve', icon: 'check', title: 'Time to resolve', via: '[target - to be confirmed]' },
      { id: 'p-csat', icon: 'star', title: 'Satisfaction', via: 'From the survey' },
    ],
    facts: [
      ['doc', 'Definitions live in the related policy document.'],
      ['users', 'Reviewed by the team lead each week.'],
    ],
  },
};
