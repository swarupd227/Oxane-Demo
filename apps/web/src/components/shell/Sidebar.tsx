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
import { NavCount, NavIcon, NavSection, navItem, SidebarFrame } from "./frame";
import { useCase, type CaseStatus } from "../../lib/api";
import { useCasework } from "../../lib/casework";
import { NAV_ROLES, useRole } from "../../lib/persona";
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

export const CASE_STATUSES: Record<
  CaseStatus,
  { label: string; className: string }
> = {
  awaiting_pack: { label: "Awaiting pack", className: "bg-sand text-muted" },
  in_review: { label: "In review", className: "bg-warn-tint text-warn" },
  approved: { label: "Approved", className: "bg-ok-tint text-ok" },
  approved_with_open_items: {
    label: "Approved with open items",
    className: "bg-info-tint text-info",
  },
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
  const approved = data.terms.filter(
    (term) => termStatus(term, state) === "approved",
  ).length;
  const items = [...data.exceptions, ...state.heldItems];
  const open = items.filter((item) => !state.exceptions[item.id]).length;
  const counts: Record<string, string> = {
    "/intake": `${data.documents.length}/${data.documents.length + data.missing_documents.length}`,
    "/terms": `${approved}/${data.terms.length}`,
    "/rules": String(data.rules.length),
    "/exceptions": String(open),
  };
  if (casework) {
    const answered = casework.tracker.queries.filter(
      (query) => query.answer_waiting,
    ).length;
    counts["/queries"] = String(
      casework.tracker.open_with_client + casework.tracker.drafted + answered,
    );
    counts["/qc"] = casework.qc.open.length
      ? String(casework.qc.open.length)
      : "";
    counts["/backbook"] = String(
      casework.backbook.filter((deal) => !deal.loaded).length || "",
    );
  }
  const approvals =
    (state.ruleEdit?.status === "pending" ? 1 : 0) +
    (state.approvedAt ? 0 : 1) +
    (casework?.qc.can_release ? 1 : 0);
  counts["/approve"] = String(approvals || "");
  return counts;
}

export function Sidebar() {
  const { pathname } = useLocation();
  const counts = useCounts();
  const status = CASE_STATUSES[useCaseStatus()];
  const { data: caseView } = useCase();
  const { data: pipeline } = useCases();
  const current = sectionOf(pathname);
  // The case's own sections show only while that case is open: on its section pages or its
  // summary. Lists, My work, clients and settings belong to no case.
  // Named from the case itself, or from the pipeline while it loads (both name the borrower).
  const active = pipeline?.cases.find((item) => item.active);
  const caseNumber = caseView?.number ?? active?.number;
  const caseName = caseView?.deal.borrower.name ?? active?.facility;
  const inCase =
    current !== null ||
    (caseNumber !== undefined && pathname === `/cases/${caseNumber}`);
  const role = useRole();
  const casesActive = pathname === "/cases" || (pathname.startsWith("/cases/") && !inCase);

  return (
    <SidebarFrame
      current="onboarding"
      footer={
        role !== "client" && (
          <nav aria-label="Platform" className="space-y-0.5">
            <NavLink to="/agents" className={({ isActive }) => navItem(isActive)}>
              {({ isActive }) => (
                <>
                  <NavIcon icon={Bot} active={isActive} />
                  Agents
                </>
              )}
            </NavLink>
            {role === "admin" && (
              <NavLink to="/settings/ai-provider" className={({ isActive }) => navItem(isActive)}>
                {({ isActive }) => (
                  <>
                    <NavIcon icon={Settings} active={isActive} />
                    Settings
                  </>
                )}
              </NavLink>
            )}
          </nav>
        )
      }
    >
      <nav aria-label="Onboarding">
        <NavSection>
          <NavLink to="/work" className={({ isActive }) => navItem(isActive)}>
            {({ isActive }) => (
              <>
                <NavIcon icon={ListTodo} active={isActive} />
                My work
              </>
            )}
          </NavLink>
          {role && NAV_ROLES["/clients"].includes(role) && (
            <NavLink to="/clients" className={({ isActive }) => navItem(isActive)}>
              {({ isActive }) => (
                <>
                  <NavIcon icon={Building2} active={isActive} />
                  Clients
                </>
              )}
            </NavLink>
          )}
          <NavLink to="/cases" end className={navItem(casesActive)}>
            <NavIcon icon={FolderKanban} active={casesActive} />
            Onboarding cases
            <NavCount value={pipeline?.summary.cases} active={casesActive} />
          </NavLink>
        </NavSection>
      </nav>
      {inCase && (
        <div className="mt-4 rounded-lg border border-line bg-canvas/60 p-1.5">
          {caseNumber && caseName && (
            <div className="px-1.5 pt-1 pb-2">
              <div className="flex items-center justify-between gap-2">
                <p className="numeric text-[0.6875rem] font-medium text-subtle">Case {caseNumber}</p>
                <span className={clsx("inline-flex h-5 items-center rounded-full px-2 text-[0.6875rem] font-medium", status.className)}>
                  {status.label}
                </span>
              </div>
              <p className="mt-0.5 truncate text-[0.8125rem] font-semibold text-ink" title={caseName}>
                {caseName}
              </p>
            </div>
          )}
          <nav aria-label="Case sections" className="space-y-0.5">
            {sections.map((section) => {
              const Icon = ICONS[section.id];
              const open = current?.section.id === section.id;
              const leafActive = open && !section.children.length;
              return (
                <div key={section.id}>
                  <NavLink to={section.path} end className={navItem(leafActive)}>
                    <NavIcon icon={Icon} active={open} />
                    <span className={clsx(open && "font-medium text-ink", leafActive && "text-accent-strong")}>
                      {section.label}
                    </span>
                    {!section.children.length && <NavCount value={counts[section.path]} active={leafActive} />}
                  </NavLink>
                  {section.children.length > 0 && (
                    <div className="ml-[1.0625rem] border-l border-line pl-2">
                      {section.children.map((child) => (
                        <NavLink key={child.path} to={child.path} end className={({ isActive }) => navItem(isActive, true)}>
                          {({ isActive }) => (
                            <>
                              {child.label}
                              <NavCount value={counts[child.path]} active={isActive} />
                            </>
                          )}
                        </NavLink>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>
        </div>
      )}
    </SidebarFrame>
  );
}
