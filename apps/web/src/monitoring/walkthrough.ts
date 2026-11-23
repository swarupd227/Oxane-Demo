/* Presenter mode's narration for the scripted monitoring cycle: one line per screen, naming the
 * facilities that carry this cycle's issues. It is scenario script, like lib/scenes.ts, so it
 * lives here rather than in the shell, which stays the same for any cycle. */
export const HINTS: Record<string, string> = {
  "/monitoring": "Whole book for the cycle. Six facilities carry this month's issues, including a 40-obligor middle-market book and a subscription line; the rest are routine.",
  "/monitoring/submissions": "Northmoor's servicer report and one Ravenglass obligor's financials are overdue and escalated. Schedules and Larkspur's daily feeds are on their own tabs.",
  "/monitoring/mapping": "Stored mapping reused; only Bramble's two new columns needed a suggestion. The layout library counts each obligor layout.",
  "/monitoring/validation": "Northmoor's duplicate row blocks the load. Record the resolution to release it.",
  "/monitoring/reconciliation": "Bramble roll-forward gap traced to 27 loans; charge-offs differ on 9.",
  "/monitoring/terms": "Switch to June: Amendment No. 2 changes the dealer limit.",
  "/monitoring/covenants": "Run the June what-if on Northmoor. Ravenglass obligor covenants; Wharfedale's exclusion forces a prepayment.",
  "/monitoring/collateral": "One VIN in both Bramble and Northmoor. Open both rows.",
  "/monitoring/triage": "Accept or change each suggestion; a change needs a reason.",
  "/monitoring/pack": "Resolve the QC variance, then switch user to approve. Thornbury needs three levels.",
  "/monitoring/monitor": "Headroom across the book. Pick a client request to draft an alert rule.",
  "/monitoring/status-call": "Weekly brief per client contact, every figure filled by code.",
  "/monitoring/results": "Measured against assumed, with the test-set results.",
};
