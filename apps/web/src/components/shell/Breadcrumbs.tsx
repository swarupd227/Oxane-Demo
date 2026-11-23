import { ChevronRight } from "lucide-react";
import { Fragment } from "react";
import { Link, useLocation } from "react-router-dom";
import { useCase } from "../../lib/api";
import { useCases } from "../../lib/cases";
import { CASE_HOME, sectionOf } from "../../lib/scenes";

interface Crumb {
  label: string;
  to?: string;
}

export function Breadcrumbs() {
  const { pathname } = useLocation();
  const { data } = useCase();
  const { data: pipeline } = useCases();
  const crumbs: Crumb[] = [{ label: "Onboarding", to: "/cases" }];

  if (pathname === "/agents" || pathname.startsWith("/agents/")) {
    crumbs.splice(0, 1, { label: "Agents" });
  } else if (pathname === "/cases") {
    crumbs.push({ label: "Cases" });
  } else if (pathname.startsWith("/cases/")) {
    const item = pipeline?.cases.find((entry) => entry.number === pathname.split("/")[2]);
    if (item) {
      crumbs.push({ label: item.client }, { label: `${item.number} ${item.facility}` });
    }
  } else if (data) {
    const place = sectionOf(pathname);
    crumbs.push(
      { label: data.deal.lender.name },
      { label: `${data.number} ${data.deal.borrower.short_name}`, to: CASE_HOME },
    );
    if (place && place.section.path !== CASE_HOME) {
      crumbs.push({ label: place.section.label, to: place.child ? place.section.path : undefined });
      if (place.child && place.child.path !== place.section.path) {
        crumbs.push({ label: place.child.label });
      }
    }
  }

  return (
    <nav aria-label="Breadcrumb" className="mb-3 flex min-w-0 items-center gap-1 text-xs text-muted">
      {crumbs.map((crumb, index) => {
        const last = index === crumbs.length - 1;
        return (
          <Fragment key={`${crumb.label}-${index}`}>
            {index > 0 && <ChevronRight aria-hidden className="size-3 shrink-0 text-stone" />}
            {crumb.to && !last ? (
              <Link to={crumb.to} className="truncate hover:text-ink hover:underline">
                {crumb.label}
              </Link>
            ) : (
              <span aria-current={last ? "page" : undefined} className={last ? "truncate text-ink" : "truncate"}>
                {crumb.label}
              </span>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
