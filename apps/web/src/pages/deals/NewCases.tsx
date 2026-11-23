/* Cases opened in the workbench, listed above the pipeline on the cases page. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ActionButton } from "../../components/deals/parts";
import { Card } from "../../components/ui/layout";
import { STAGE_LABEL, usd, useDealCases } from "../../lib/deals";
import { useRole } from "../../lib/persona";
import { NoAiBadge } from "../../monitoring/parts";
import { NewCaseDialog } from "./ClientsPage";

export function NewCasesPanel() {
  const { data } = useDealCases();
  const role = useRole();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  return (
    <Card className="mb-4 overflow-x-auto">
      <div className="flex items-center justify-between border-b border-line px-4 py-2">
        <p className="text-[0.8125rem] font-semibold">Opened on the platform <span className="numeric ml-1 text-muted">{data?.length ?? 0}</span></p>
        <ActionButton reason={role === "onboarding_analyst" ? null : "For the onboarding analyst"} onClick={() => setOpen(true)}>New case</ActionButton>
      </div>
      <ul aria-label="Cases opened on the platform" className="max-h-72 overflow-y-auto text-[0.8125rem]">
        {(data ?? []).map((c) => (
          <li key={c.id}>
            <button type="button" onClick={() => navigate(`/deals/cases/${c.id}`)} className="grid w-full cursor-pointer grid-cols-[6rem_minmax(0,2fr)_minmax(0,1.5fr)_8rem_9rem_4rem_5rem_6rem_9rem] items-center gap-2 border-b border-sand px-4 py-2 text-left last:border-0 hover:bg-canvas">
              <span className="font-mono text-xs font-semibold">{c.ref}</span>
              <span className="truncate font-medium">{c.facility_name}</span>
              <span className="flex items-center gap-1.5 truncate text-muted">{c.client.name}{!c.client.ai_permitted && <NoAiBadge compact />}</span>
              <span>{c.deal_type}</span>
              <span><span className="rounded bg-sand px-1.5 py-px text-[0.6875rem] font-medium">{STAGE_LABEL[c.stage]}</span></span>
              <span className="numeric text-right">{c.documents} docs</span>
              <span className="numeric text-right">{c.terms.total ? `${c.terms.approved}/${c.terms.total}` : "–"}</span>
              <span className="numeric text-right">{c.exceptions_open ? `${c.exceptions_open} open` : <span className="text-muted">0 open</span>}</span>
              <span className="numeric text-right">{usd(c.commitment_cents)}</span>
            </button>
          </li>
        ))}
        {data && data.length === 0 && <li className="px-4 py-4 text-center text-muted">No cases opened yet.</li>}
      </ul>
      {open && <NewCaseDialog open={open} onOpenChange={setOpen} />}
    </Card>
  );
}
