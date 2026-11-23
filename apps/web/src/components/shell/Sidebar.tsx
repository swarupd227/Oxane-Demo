import clsx from "clsx";
import {
  BarChart3,
  Bot,
  Settings,
  Building2,
  ListTodo,
  ClipboardCheck,
  FileStack,
  FolderKanban,
  GitCompareArrows,
  LayoutDashboard,
  ListChecks,
  MessagesSquare,
  ScrollText,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { useCase, type CaseStatus } from "../../lib/api";
import { useCasework } from "../../lib/casework";
import { useRole } from "../../lib/persona";
import { useCases } from "../../lib/cases";
import { sectionOf, sections } from "../../lib/scenes";
import { termStatus, useSession } from "../../lib/session";
import { useWorkbench } from "../../lib/workbench";

const ICONS: Record<string, LucideIcon> = {
  overview: LayoutDashboard,
  documents: FileStack,
  terms: ScrollText,
  rules: SlidersHorizontal,
  mapping: GitCompareArrows,
  validation: ListChecks,
  exceptions: MessagesSquare,
  approvals: ClipboardCheck,
  metrics: BarChart3,
};

export const CASE_STATUSES: Record<CaseStatus, { label: string; className: string }> = {
  awaiting_pack: { label: "Awaiting pack", className: "bg-sand text-muted" },
  in_review: { label: "In review", className: "bg-warn-tint text-warn" },
  approved: { label: "Approved", className: "bg-ok-tint text-ok" },
  approved_with_open_items: { label: "Approved with open items", className: "bg-info-tint text-info" },
};

export function useCaseStatus(): CaseStatus {
  const { data } = useCase();
  const { state } = useSession();
  if (state.approvedAt) {
    return "approved_with_open_items";
  }
  return state.intakeDone ? "in_review" : (data?.status ?? "awaiting_pack");
}

function useCounts(): Record<string, string> {
  const { data } = useWorkbench();
  const { data: casework } = useCasework();
  const { state } = useSession();
  if (!data || !state.intakeDone) {
    return {};
  }
  const approved = data.terms.filter((term) => termStatus(term, state) === "approved").length;
  const items = [...data.exceptions, ...state.heldItems];
  const open = items.filter((item) => !state.exceptions[item.id]).length;
  const counts: Record<string, string> = {
    "/intake": `${data.documents.length}/${data.documents.length + data.missing_documents.length}`,
    "/terms": `${approved}/${data.terms.length}`,
    "/rules": String(data.rules.length),
    "/exceptions": String(open),
  };
  if (casework) {
    const answered = casework.tracker.queries.filter((query) => query.answer_waiting).length;
    counts["/queries"] = String(casework.tracker.open_with_client + casework.tracker.drafted + answered);
    counts["/qc"] = casework.qc.open.length ? String(casework.qc.open.length) : "";
    counts["/backbook"] = String(casework.backbook.filter((deal) => !deal.loaded).length || "");
  }
  const approvals =
    (state.ruleEdit?.status === "pending" ? 1 : 0) + (state.approvedAt ? 0 : 1) + (casework?.qc.can_release ? 1 : 0);
  counts["/approve"] = String(approvals || "");
  return counts;
}

function Count({ value, active }: { value?: string; active?: boolean }) {
  if (!value || value === "0") {
    return null;
  }
  return (
    <span
      className={clsx(
        "numeric ml-auto rounded px-1.5 text-[0.6875rem] font-medium",
        active ? "bg-surface text-ink" : "bg-sand text-muted",
      )}
    >
      {value}
    </span>
  );
}

export function Sidebar() {
  const { pathname } = useLocation();
  const counts = useCounts();
  const status = CASE_STATUSES[useCaseStatus()];
  const { data: pipeline } = useCases();
  const current = sectionOf(pathname);
  const role = useRole();
  const link = (active: boolean) =>
    clsx(
      "flex h-8 items-center gap-2 rounded-md px-2 text-[0.8125rem] whitespace-nowrap",
      active ? "bg-sand font-semibold text-ink" : "text-muted hover:bg-sand/60 hover:text-ink",
    );

  return (
    <aside className="sticky top-12 hidden h-[calc(100vh-3rem)] w-56 shrink-0 flex-col overflow-y-auto border-r border-line bg-surface px-2 py-3 lg:flex">
      <nav aria-label="Onboarding">
        <NavLink to="/work" className={({ isActive }) => link(isActive)}>
          <ListTodo aria-hidden className="size-4 shrink-0" />
          My work
        </NavLink>
        <NavLink to="/clients" className={({ isActive }) => link(isActive)}>
          <Building2 aria-hidden className="size-4 shrink-0" />
          Clients
        </NavLink>
        <NavLink to="/cases" end className={({ isActive }) => link(isActive || pathname.startsWith("/cases/"))}>
          <FolderKanban aria-hidden className="size-4 shrink-0" />
          Onboarding cases
          <Count value={pipeline ? String(pipeline.summary.cases) : undefined} />
        </NavLink>
      </nav>
      <div className="mt-4 mb-1.5 px-2">
        <p className="text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">Case 0412</p>
        <span
          className={clsx(
            "mt-1 inline-flex h-5 items-center rounded px-1.5 text-[0.6875rem] font-medium",
            status.className,
          )}
        >
          {status.label}
        </span>
      </div>
      <nav aria-label="Case sections" className="space-y-0.5">
        {sections.map((section) => {
          const Icon = ICONS[section.id];
          const open = current?.section.id === section.id;
          return (
            <div key={section.id}>
              <NavLink to={section.path} end className={() => link(open && !section.children.length)}>
                <Icon aria-hidden className="size-4 shrink-0" />
                <span className={clsx(open && "font-semibold text-ink")}>{section.label}</span>
                {!section.children.length && <Count value={counts[section.path]} active={open} />}
              </NavLink>
              {section.children.length > 0 && (
                <div className="ml-4 border-l border-line pl-2">
                  {section.children.map((child) => (
                    <NavLink
                      key={child.path}
                      to={child.path}
                      end
                      className={({ isActive }) =>
                        clsx(
                          "flex h-7 items-center gap-2 rounded-md px-2 text-[0.8125rem] whitespace-nowrap",
                          isActive ? "bg-sand font-semibold text-ink" : "text-muted hover:bg-sand/60 hover:text-ink",
                        )
                      }
                    >
                      {child.label}
                      <Count value={counts[child.path]} active={pathname === child.path} />
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      {role !== "client" && (
        <nav aria-label="Platform" className="mt-auto border-t border-line pt-2">
          <NavLink to="/agents" className={({ isActive }) => link(isActive)}>
            <Bot aria-hidden className="size-4 shrink-0" />
            Agents
          </NavLink>
          {role === "admin" && (
            <NavLink to="/settings/ai-provider" className={({ isActive }) => link(isActive)}>
              <Settings aria-hidden className="size-4 shrink-0" />
              Settings
            </NavLink>
          )}
        </nav>
      )}
    </aside>
  );
}
