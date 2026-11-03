const base = { viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", "aria-hidden": true } as const;

export const IconSearch = () => (
  <svg {...base} strokeWidth="1.6"><circle cx="7" cy="7" r="5" /><path d="m11 11 3.5 3.5" /></svg>
);
export const IconPlus = () => (
  <svg {...base} strokeWidth="2"><path d="M8 3v10M3 8h10" /></svg>
);
export const IconDownload = () => (
  <svg {...base} strokeWidth="1.8"><path d="M8 2v8m-3.5-3.5L8 10l3.5-3.5M3 13.5h10" /></svg>
);
export const IconBack = () => (
  <svg {...base} strokeWidth="1.8"><path d="M10 3 5 8l5 5" /></svg>
);
export const IconCheck = () => (
  <svg {...base} width="16" height="16" strokeWidth="2"><path d="m3 8.5 3 3 7-7" /></svg>
);
