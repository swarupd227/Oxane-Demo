/* Covenants for the middle-market facility and the subscription line. Every figure is the
 * engine's; this only lays it out. */
import clsx from "clsx";
import { CircleAlert, FileText, Scale, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/layout";
import type { Cycle, Obligor, Source } from "../cycle";
import { Stat, usd2 } from "../parts";
import { Badge, when } from "../ui";

const m = (v: number) => `US$${(v / 1e6).toFixed(2)}m`;

function Box({
  title,
  clause,
  badge,
  children,
}: {
  title: string;
  clause?: ReactNode;
  badge?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card className="p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[0.8125rem] font-semibold">{title}</p>
          {clause && <p className="text-xs text-muted">{clause}</p>}
        </div>
        {badge}
      </div>
      <div className="mt-3">{children}</div>
    </Card>
  );
}

function ClauseButtons({
  clauses,
  onSource,
}: {
  clauses: Source[];
  onSource: (s: Source | null) => void;
}) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {clauses.map((clause) => (
        <Button
          key={clause.label}
          size="sm"
          variant="secondary"
          onClick={() => onSource(clause)}
        >
          <FileText aria-hidden className="size-3.5" />
          {clause.label?.split(", ")[1] ?? clause.label}
        </Button>
      ))}
    </div>
  );
}

function obligorStatus(o: Obligor): {
  label: string;
  tone: "ok" | "warn" | "danger" | "neutral";
} {
  if (!o.received) return { label: "No Q1 financials", tone: "danger" };
  if (!o.leverage_passed || !o.icr_passed)
    return { label: "Over covenant", tone: "danger" };
  if (o.addbacks_flagged) return { label: "Expert review", tone: "warn" };
  if (o.max_leverage_basis.startsWith("Waiver"))
    return { label: "Waived level", tone: "warn" };
  if (o.headroom < 0.5) return { label: "Near", tone: "warn" };
  return { label: "Pass", tone: "ok" };
}

export function RavenglassCovenants({
  cycle,
  onSource,
}: {
  cycle: Cycle;
  onSource: (s: Source | null) => void;
}) {
  const t = cycle.tests.ravenglass;
  const bb = t.borrowing_base;
  const [filter, setFilter] = useState<"flagged" | "all">("flagged");
  const flagged = t.obligors.filter((o) => obligorStatus(o).label !== "Pass");
  const rows = filter === "all" ? t.obligors : flagged;
  const extracted = t.extraction.status === "recorded";
  const addbacks = t.obligors.filter((o) => o.addbacks_flagged);
  return (
    <div className="space-y-3">
      <Box
        title="Obligor financial covenants"
        clause={`Tested at ${when(t.quarter_end)} on each obligor's covenant in force, after waivers · tolerance ${t.tolerance_x.toFixed(2)}x on reported ratios`}
        badge={
          <Badge tone="danger">
            {
              t.obligors.filter(
                (o) => o.received && !(o.leverage_passed && o.icr_passed),
              ).length
            }{" "}
            over covenant
          </Badge>
        }
      >
        <div className="grid grid-cols-5 gap-3">
          <Stat
            label="Obligors"
            value={t.obligors.length}
            note={`${t.received} reported for Q1`}
          />
          <Stat
            label="Over covenant"
            value={
              t.obligors.filter((o) => o.received && !o.leverage_passed).length
            }
            tone="danger"
            note="Material Obligor Event"
          />
          <Stat
            label="Add-backs over cap"
            value={addbacks.length}
            tone="warn"
            note={`Cap ${t.cap_pct}% of EBITDA`}
          />
          <Stat
            label="Waived levels"
            value={t.covenant_changes.length}
            note="Notified under Section 7.3"
          />
          <Stat
            label="Figures from"
            value={extracted ? "Documents" : "Fund report"}
            note={
              extracted
                ? `${t.extraction.verified} of ${t.received} verified`
                : "Obligor reading pending recording"
            }
            tone={extracted ? "ok" : "warn"}
          />
        </div>
        <div className="mt-3 flex items-center gap-1 text-xs">
          {(["flagged", "all"] as const).map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
              className={clsx(
                "h-6 cursor-pointer rounded-md px-2 font-medium",
                filter === f
                  ? "bg-accent-tint text-accent-strong font-medium"
                  : "bg-sand text-muted hover:text-ink",
              )}
            >
              {f === "flagged"
                ? `Needs attention (${flagged.length})`
                : `All obligors (${t.obligors.length})`}
            </button>
          ))}
        </div>
        <div className="mt-2 max-h-96 overflow-auto rounded-md border border-line">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-canvas">
              <tr className="text-[0.6875rem] font-semibold tracking-[0.04em] text-muted uppercase">
                <th className="py-1.5 pr-2 pl-2">Obligor</th>
                <th className="py-1.5 pr-2 text-right">Outstanding</th>
                <th className="py-1.5 pr-2 text-right">Net debt, EBITDA</th>
                <th className="py-1.5 pr-2 text-right">Leverage</th>
                <th className="py-1.5 pr-2 text-right">Max</th>
                <th className="py-1.5 pr-2 text-right">ICR</th>
                <th className="py-1.5 pr-2 text-right">Add-backs</th>
                <th className="py-1.5 pr-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => {
                const s = obligorStatus(o);
                const source = Object.values(o.sources).find(Boolean) ?? null;
                return (
                  <tr
                    key={o.id}
                    onClick={() => onSource(source)}
                    className={clsx(
                      "border-t border-sand align-top",
                      source && "cursor-pointer hover:bg-canvas",
                      !o.eligible && "bg-danger-tint/30",
                    )}
                  >
                    <td className="max-w-60 py-1.5 pr-2 pl-2">
                      <span
                        className="block truncate font-medium"
                        title={o.name}
                      >
                        {o.name}
                      </span>
                      <span className="block truncate text-[0.6875rem] text-muted">
                        <span className="font-mono">{o.id}</span> · {o.facility}{" "}
                        · {o.sector}
                      </span>
                    </td>
                    <td className="numeric py-1.5 pr-2 text-right">
                      {m(o.outstanding)}
                    </td>
                    <td className="numeric py-1.5 pr-2 text-right whitespace-nowrap text-muted">
                      {o.net_debt_k.toLocaleString("en-GB")}
                      <span className="block">
                        {o.covenant_ebitda_k.toLocaleString("en-GB")}
                      </span>
                    </td>
                    <td
                      className={clsx(
                        "numeric py-1.5 pr-2 text-right font-semibold",
                        !o.leverage_passed && "text-danger",
                      )}
                    >
                      {o.leverage.toFixed(2)}x
                      {o.reported_leverage !== null && o.leverage_difference ? (
                        <span className="block text-[0.6875rem] font-normal text-muted">
                          reported {o.reported_leverage.toFixed(2)}x
                        </span>
                      ) : null}
                    </td>
                    <td className="numeric py-1.5 pr-2 text-right">
                      {o.max_leverage.toFixed(2)}x
                      {o.max_leverage_basis.startsWith("Waiver") && (
                        <span className="block text-[0.6875rem] text-warn">
                          was {o.original_max_leverage.toFixed(2)}x
                        </span>
                      )}
                    </td>
                    <td className="numeric py-1.5 pr-2 text-right">
                      {o.icr.toFixed(2)}x
                      <span className="block text-[0.6875rem] text-muted">
                        min {o.min_icr.toFixed(2)}x
                      </span>
                    </td>
                    <td
                      className={clsx(
                        "numeric py-1.5 pr-2 text-right",
                        o.addbacks_flagged && "font-semibold text-warn",
                      )}
                    >
                      {o.addback_pct ? `${o.addback_pct.toFixed(0)}%` : "–"}
                    </td>
                    <td className="py-1.5 pr-2 whitespace-nowrap">
                      <Badge tone={s.tone}>{s.label}</Badge>
                      {o.stale && (
                        <span className="block text-[0.6875rem] text-muted">
                          report shows {when(o.financials_as_of)}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <ClauseButtons clauses={t.clauses.slice(0, 3)} onSource={onSource} />
      </Box>
      <div className="grid grid-cols-2 gap-3">
        <Box
          title="Borrowing base"
          clause="Section 2.4 · each eligible loan at its advance rate"
          badge={
            <Badge tone={bb.passed ? "ok" : "danger"}>
              {bb.passed ? "Within base" : "Over base"}
            </Badge>
          }
        >
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
                <th />
                <th className="pb-1 text-right">Recomputed</th>
                <th className="pb-1 pl-3 text-right">Certificate</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["Eligible balance", bb.eligible, bb.certificate.eligible],
                [
                  "Borrowing base",
                  bb.borrowing_base,
                  bb.certificate.borrowing_base,
                ],
                ["Availability", bb.availability, bb.certificate.availability],
              ].map(([label, mine, theirs]) => (
                <tr
                  key={label as string}
                  className="border-b border-sand last:border-0"
                >
                  <td className="py-1.5">{label}</td>
                  <td className="numeric py-1.5 text-right whitespace-nowrap">
                    {m(mine as number)}
                  </td>
                  <td className="numeric py-1.5 pl-3 text-right whitespace-nowrap text-muted">
                    {m(theirs as number)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[0.6875rem] font-semibold text-muted uppercase">
            Bridge to the certificate
          </p>
          <ul className="mt-1 space-y-1 text-xs">
            {bb.excluded.map((x) => (
              <li key={x.obligor} className="flex justify-between gap-2">
                <span>
                  <span className="font-mono text-muted">{x.obligor}</span>{" "}
                  {x.name} · {x.reason}
                </span>
                <span className="numeric">{usd2(x.value)}</span>
              </li>
            ))}
            <li className="flex justify-between gap-2 border-t border-sand pt-1 font-semibold">
              <span>Certificate above recomputed</span>
              <span className="numeric">{usd2(bb.difference)}</span>
            </li>
          </ul>
          {bb.sensitivity.map((s) => (
            <p key={s.obligor} className="mt-2 text-xs text-warn">
              If {s.name} is excluded on expert review: base falls by{" "}
              {usd2(s.if_excluded)}
            </p>
          ))}
        </Box>
        <div className="space-y-3">
          <Box
            title="Concentration"
            clause="Section 1.1 · per obligor and per sector"
          >
            <div className="flex gap-6">
              <Stat
                label="Largest obligor"
                value={`${bb.largest.pct.toFixed(2)}%`}
                note={`${bb.largest.name} · limit ${bb.single_limit_pct}%`}
              />
              <Stat
                label="Largest sector"
                value={`${bb.largest_sector.pct.toFixed(2)}%`}
                note={`${bb.largest_sector.sector} · limit ${bb.sector_limit_pct}%`}
              />
            </div>
            <p className="numeric mt-2 text-xs text-muted">
              Concentration excess {usd2(bb.excess_reduction)}
            </p>
          </Box>
          {addbacks.map((o) => (
            <Box
              key={o.id}
              title={`Add-backs: ${o.name}`}
              clause={`Covenant EBITDA: cost savings, synergies and restructuring capped at ${t.cap_pct}%`}
              badge={<Badge tone="warn">Expert review</Badge>}
            >
              <ul className="space-y-1 text-xs">
                {o.readings.map((r) => (
                  <li
                    key={r.name}
                    className="flex items-center justify-between gap-2"
                  >
                    <span>{r.name}</span>
                    <span
                      className={clsx(
                        "numeric font-semibold",
                        r.passed ? "text-ok" : "text-danger",
                      )}
                    >
                      {r.leverage.toFixed(2)}x {r.passed ? "pass" : "breach"}
                    </span>
                  </li>
                ))}
              </ul>
              {o.addback_items.length > 0 ? (
                <ul className="mt-2 space-y-1 border-t border-sand pt-2 text-xs">
                  {o.addback_items.map((a) => (
                    <li key={a.description}>
                      <button
                        type="button"
                        onClick={() => onSource(a.source)}
                        className="cursor-pointer text-left hover:underline"
                      >
                        {a.description}: US${a.amount_k.toLocaleString("en-GB")}
                        k · {a.kind}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-muted">
                  Add-backs not itemised: the certificate reading is pending
                  recording, so every add-back is read under the cap.
                </p>
              )}
            </Box>
          ))}
          {t.covenant_changes.map((c) => (
            <Box
              key={c.obligor}
              title={`Waiver: ${t.obligors.find((o) => o.id === c.obligor)?.name ?? c.obligor}`}
              clause={`${c.covenant} ${c.old_value} to ${c.new_value} · test dates ${c.test_dates.map(when).join(", ")}`}
              badge={
                c.verified ? (
                  <Badge tone="ok">Quote found</Badge>
                ) : (
                  <Badge tone="danger">Quote not found</Badge>
                )
              }
            >
              <button
                type="button"
                onClick={() => onSource(c.source)}
                className="cursor-pointer text-left text-xs text-info hover:underline"
              >
                <FileText
                  aria-hidden
                  className="mr-1 inline size-3 align-[-2px]"
                />
                {c.document.split("/").pop()} ·{" "}
                {c.by === "AI" ? "Read by AI" : c.by}
              </button>
            </Box>
          ))}
        </div>
      </div>
    </div>
  );
}

export function WharfedaleCovenants({
  cycle,
  onSource,
}: {
  cycle: Cycle;
  onSource: (s: Source | null) => void;
}) {
  const w = cycle.tests.wharfedale;
  const bb = w.borrowing_base;
  const before = w.before_exclusion;
  const [all, setAll] = useState(false);
  const rows = all
    ? w.investors
    : w.investors.filter(
        (r) =>
          r.exclusion_event ||
          r.excess ||
          r.difference ||
          r.class !== r.prior_class,
      );
  return (
    <div className="space-y-3">
      <Box
        title="Borrowing base and mandatory prepayment"
        clause={`Section 2.5 · loans within the lesser of commitment and borrowing base · ${bb.advance_rates.Included}% included, ${bb.advance_rates.Designated}% designated`}
        badge={
          <Badge tone={bb.passed ? "ok" : "danger"}>
            {bb.passed ? "Within base" : "Prepayment due"}
          </Badge>
        }
      >
        <div className="grid grid-cols-4 gap-4">
          <Stat
            label="Before the exclusion"
            value={m(before.borrowing_base)}
            note="Register's designations"
          />
          <Stat
            label="Borrowing base"
            value={m(bb.borrowing_base)}
            note={`Concentration ${m(bb.concentration_reduction)} off`}
            tone="danger"
          />
          <Stat
            label="Loans outstanding"
            value={m(bb.drawn)}
            note={`Commitment ${m(bb.commitment)}`}
          />
          <Stat
            label="Mandatory prepayment"
            value={usd2(bb.prepayment)}
            note="Within two business days"
            tone="danger"
          />
        </div>
        <ClauseButtons clauses={w.clauses} onSource={onSource} />
      </Box>
      <div className="grid grid-cols-2 gap-3">
        <Box
          title="Investor eligibility"
          clause={`Exclusion Event below ${"BBB-"} · ${w.classes.Included} included, ${w.classes.Designated} designated, ${w.classes.Excluded} excluded`}
          badge={
            w.exclusions.length ? (
              <Badge tone="danger">{w.exclusions.length} exclusion event</Badge>
            ) : undefined
          }
        >
          {w.exclusions.map((r) => (
            <div
              key={r.id}
              className="rounded-md border border-danger/40 p-2.5 text-sm"
            >
              <p className="flex items-center gap-1.5 font-semibold">
                <CircleAlert aria-hidden className="size-4 text-danger" />
                {r.name}
              </p>
              <p className="numeric mt-0.5 text-xs">
                {r.prior_rating} to{" "}
                <strong className="text-danger">{r.rating}</strong> on{" "}
                {when(r.rating_date)} · uncalled {usd2(r.uncalled)}
              </p>
              <p className="mt-0.5 text-xs text-muted">
                Register still shows {r.register_designation}; excluded by the
                agreement.
              </p>
            </div>
          ))}
        </Box>
        <Box
          title="Concentration"
          clause={`Single investor ${bb.single_limit_pct}% · designated together ${bb.designated_limit_pct}%`}
          badge={
            bb.concentration_reduction ? (
              <Badge tone="danger">Over limit</Badge>
            ) : (
              <Badge tone="ok">Pass</Badge>
            )
          }
        >
          <div className="flex gap-6">
            <Stat
              label="Largest investor"
              value={`${w.largest.share_pct.toFixed(2)}%`}
              note={`${w.largest.name}`}
              tone={w.largest.excess ? "danger" : undefined}
            />
            <Stat
              label="Designated"
              value={`${bb.designated_pct.toFixed(2)}%`}
              note={`Limit ${bb.designated_limit_pct}%`}
            />
          </div>
          <p className="numeric mt-2 text-xs text-muted">
            Counts up to {usd2(bb.single_limit)}; excess{" "}
            {usd2(w.largest.excess)} · before the exclusion the limit was{" "}
            {usd2(before.single_limit)}
          </p>
        </Box>
      </div>
      <Box
        title="Notices against the register"
        clause="Each investor's share of each notice, and its uncalled rolled from April"
      >
        <div className="grid grid-cols-3 gap-3 text-xs">
          {[
            {
              label: `Capital call ${w.notices.capital_call.number}`,
              n: w.notices.capital_call,
              note: `${usd2(w.notices.capital_call.total)} · due ${when(w.notices.capital_call.due)}`,
            },
            {
              label: `Distribution ${w.notices.distribution.number}`,
              n: w.notices.distribution,
              note: `${usd2(w.notices.distribution.total)} · ${usd2(w.notices.distribution.recallable ?? 0)} recallable`,
            },
          ].map(({ label, n, note }) => (
            <div key={label} className="rounded-md border border-line p-2.5">
              <p className="flex items-center justify-between gap-2 font-semibold">
                {label}{" "}
                <Badge tone={n.reconciles ? "ok" : "danger"}>
                  {n.reconciles ? "Reconciles" : "Differs"}
                </Badge>
              </p>
              <p className="numeric mt-0.5 text-muted">{note}</p>
              <p className="mt-0.5 text-muted">
                {n.lines.length} investors · sum difference{" "}
                {usd2(n.sum_difference)}
              </p>
            </div>
          ))}
          <div
            className={clsx(
              "rounded-md border p-2.5",
              w.register_breaks.length ? "border-warn/60" : "border-line",
            )}
          >
            <p className="flex items-center gap-1.5 font-semibold">
              <TriangleAlert aria-hidden className="size-3.5 text-warn" />{" "}
              Register breaks: {w.register_breaks.length}
            </p>
            {w.register_breaks.map((r) => (
              <p key={r.id} className="numeric mt-0.5">
                {r.name}: register {usd2(r.register_uncalled)}, expected{" "}
                {usd2(r.expected_uncalled)}
              </p>
            ))}
          </div>
        </div>
      </Box>
      <Box
        title="Investors"
        clause={`${w.investors.length} investors · ${usd2(w.commitments)} committed · ${usd2(w.uncalled)} uncalled`}
        badge={
          <button
            type="button"
            aria-pressed={all}
            onClick={() => setAll(!all)}
            className="h-6 cursor-pointer rounded-md bg-sand px-2 text-xs font-medium text-muted hover:text-ink"
          >
            {all ? "Show changes only" : `Show all ${w.investors.length}`}
          </button>
        }
      >
        <div className="max-h-80 overflow-auto rounded-md border border-line">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-canvas">
              <tr className="text-[0.6875rem] font-semibold tracking-[0.04em] text-muted uppercase">
                <th className="py-1.5 pr-2 pl-2">Investor</th>
                <th className="py-1.5 pr-2 text-right">Commitment</th>
                <th className="py-1.5 pr-2 text-right">Uncalled</th>
                <th className="py-1.5 pr-2">Rating</th>
                <th className="py-1.5 pr-2">Class</th>
                <th className="py-1.5 pr-2 text-right">Counted</th>
                <th className="py-1.5 pr-2 text-right">Excess</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className={clsx(
                    "border-t border-sand",
                    r.exclusion_event && "bg-danger-tint/30",
                  )}
                >
                  <td className="max-w-60 py-1.5 pr-2 pl-2">
                    <span className="block truncate font-medium" title={r.name}>
                      {r.name}
                    </span>
                    <span className="block truncate text-[0.6875rem] text-muted">
                      <span className="font-mono">{r.id}</span> · {r.type}
                    </span>
                  </td>
                  <td className="numeric py-1.5 pr-2 text-right">
                    {m(r.commitment)}
                  </td>
                  <td className="numeric py-1.5 pr-2 text-right">
                    {m(r.uncalled)}
                    {r.difference ? (
                      <span className="block text-[0.6875rem] text-warn">
                        register {m(r.register_uncalled)}
                      </span>
                    ) : null}
                  </td>
                  <td className="py-1.5 pr-2 font-mono whitespace-nowrap">
                    {r.prior_rating !== r.rating
                      ? `${r.prior_rating} → ${r.rating}`
                      : r.rating}
                  </td>
                  <td className="py-1.5 pr-2">
                    <Badge
                      tone={
                        r.class === "Excluded"
                          ? "danger"
                          : r.class === "Designated"
                            ? "info"
                            : "ok"
                      }
                    >
                      {r.class}
                    </Badge>
                  </td>
                  <td className="numeric py-1.5 pr-2 text-right">
                    {m(r.counted)}
                  </td>
                  <td className="numeric py-1.5 pr-2 text-right">
                    {r.excess ? m(r.excess) : "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Box>
      <p className="flex items-center gap-1.5 text-xs text-muted">
        <Scale aria-hidden className="size-3.5" />
        Classes from each investor's rating and the class the lender approved;
        the register's own designation is shown where it differs.
      </p>
    </div>
  );
}
