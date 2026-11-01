import clsx from "clsx";
import { ArrowRight, BellRing, CircleAlert, Loader2, Play } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { StatusPill } from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Card, SectionLabel } from "../components/ui/layout";
import { NeedsIntake, PageHeader } from "../components/ui/PageHeader";
import { AnimatedMoney } from "../components/validation/AnimatedMoney";
import { Bridge } from "../components/validation/Bridge";
import { LoanDrill } from "../components/validation/LoanDrill";
import { formatCount, formatUsd } from "../lib/format";
import { useSession } from "../lib/session";
import { useValidationRun, type RunResult } from "../lib/workbench";

const ALERT_FLOOR = 500_000;

function Comparison({ run }: { run: RunResult }) {
  const rows: [string, number, number][] = [
    ["Eligible pool", run.borrower.eligible_pool, run.system.eligible_pool],
    ["Excess concentration", run.borrower.excess, run.system.excess],
    ["Reserve", run.borrower.reserve, run.system.reserve],
    ["Borrowing base", run.borrower.borrowing_base, run.system.borrowing_base],
    ["Availability", run.borrower.availability, run.system.availability],
  ];
  return (
    <table className="w-full text-left">
      <thead>
        <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
          <th className="py-2.5 pr-3 pl-5">April 2026</th>
          <th className="py-2.5 pr-3 text-right">Borrower's certificate</th>
          <th className="py-2.5 pr-3 text-right">System</th>
          <th className="py-2.5 pr-5 text-right">Difference</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([label, borrower, system]) => {
          const hero = label === "Borrowing base" || label === "Availability";
          return (
            <tr key={label} className="border-b border-sand last:border-0">
              <td className={clsx("py-2.5 pr-3 pl-5 text-sm", hero && "font-semibold")}>{label}</td>
              <td className="numeric py-2.5 pr-3 text-right text-sm text-muted">
                {formatUsd(borrower)}
              </td>
              <td className="py-2.5 pr-3 text-right">
                <AnimatedMoney value={system} className={clsx("text-sm", hero && "font-semibold")} />
              </td>
              <td className="py-2.5 pr-5 text-right">
                <AnimatedMoney value={system - borrower} className="text-sm font-medium" />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function RuleResults({ run }: { run: RunResult }) {
  return (
    <ul className="divide-y divide-sand">
      {run.rules.map((rule) => (
        <li key={rule.id} className="flex items-center gap-3 px-5 py-1.5 text-sm">
          <span className="numeric w-8 font-semibold">{rule.id}</span>
          <span className="min-w-0 flex-1 truncate text-muted">{rule.label}</span>
          {rule.status === "not_evaluated" ? (
            <StatusPill status="missing" label="Not evaluated" />
          ) : (
            <span className="numeric font-medium">{rule.failed} failed</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function ConcentrationBar({ share, limit }: { share: number; limit: number }) {
  const scale = Math.max(limit * 1.3, share * 1.1);
  return (
    <div className="relative h-2 rounded bg-sand" aria-hidden>
      <motion.div
        layout
        className={clsx("h-full rounded", share > limit ? "bg-danger" : "bg-subtle")}
        style={{ width: `${(share / scale) * 100}%` }}
      />
      <span
        className="absolute -top-1 h-4 w-0.5 bg-ink"
        style={{ left: `${(limit / scale) * 100}%` }}
      />
    </div>
  );
}

function Concentrations({ run }: { run: RunResult }) {
  return (
    <ul className="divide-y divide-sand">
      {run.concentrations.map((item) => (
        <li key={item.id} className="px-5 py-2.5">
          <div className="numeric flex items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 truncate">
              <span className="font-semibold">{item.id}</span>{" "}
              <span className="text-muted">{item.largest}</span>
            </span>
            <span className="shrink-0 font-medium">
              {item.share_pct.toFixed(2)}% against {item.limit_pct}% limit
            </span>
          </div>
          <div className="mt-2">
            <ConcentrationBar share={item.share_pct} limit={item.limit_pct} />
          </div>
          {item.excess > 0 && (
            <p className="numeric mt-1.5 text-xs font-medium text-danger">
              Over the limit by {formatUsd(item.excess)}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

function Covenants({ run }: { run: RunResult }) {
  const { tests, leverage_without_carve_out: raw, delinquency } = run.covenants;
  const unit = (name: string, value: number) =>
    name.includes("leverage") ? `${value.toFixed(2)} to 1` : formatUsd(value * 1000);
  return (
    <ul className="divide-y divide-sand">
      {tests.map((test) => (
        <li key={test.name} className="px-5 py-2.5">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-medium">{test.name}</span>
            <StatusPill status={test.passed ? "approved" : "missing"} label={test.passed ? "Pass" : "Breach"} />
          </div>
          <p className="numeric mt-0.5 text-[0.8125rem] text-muted">
            {unit(test.name, test.value)} against {unit(test.name, test.limit)}, Section {test.clause}
          </p>
          {test.name.includes("leverage") && (
            <p className="numeric mt-0.5 text-xs text-muted">
              Without the 6.12(c) carve-out: {raw.toFixed(2)} to 1.
            </p>
          )}
        </li>
      ))}
      <li className="px-5 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium">Delinquency trigger</span>
          <StatusPill status={delinquency.tripped ? "missing" : "approved"} label={delinquency.tripped ? "Tripped" : "Clear"} />
        </div>
        <p className="numeric mt-0.5 text-[0.8125rem] text-muted">
          {delinquency.average_pct.toFixed(2)}% three-month average against{" "}
          {delinquency.trigger_pct.toFixed(1)}%, Section 7.1
        </p>
      </li>
    </ul>
  );
}

const TABS = ["Rules", "Concentration", "Covenants"] as const;

export function ValidationPage() {
  const { state, dispatch } = useSession();
  const navigate = useNavigate();
  const [running, setRunning] = useState(false);
  const [selected, setSelected] = useState<string | null>("E1");
  const [tab, setTab] = useState<(typeof TABS)[number]>("Rules");
  const { data: run, isError, refetch } = useValidationRun(state.dealerMatched, state.ran);

  useEffect(() => {
    if (!running) {
      return;
    }
    const timer = setTimeout(() => {
      setRunning(false);
      dispatch({ type: "run" });
    }, 900);
    return () => clearTimeout(timer);
  }, [running, dispatch]);

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }

  const line = run?.pool_bridge.lines.find((item) => item.rule_id === selected);

  return (
    <div className="space-y-4">
      <PageHeader
        title="First validation run"
        summary="System recalculation against the borrower's certificate, April 2026."
        actions={
          state.ran && (
            <Button size="lg" onClick={() => navigate("/exceptions")}>
              View exception queue
              <ArrowRight aria-hidden className="size-4" />
            </Button>
          )
        }
      />

      {!state.ran && (
        <Card className="flex h-72 flex-col items-center justify-center gap-3 text-center">
          <p className="text-lg font-medium">Ready to run</p>
          <p className="text-sm text-muted">
            {formatCount(2400)} loans through 16 rules. E7 cannot run until Schedule 4 arrives.
          </p>
          <Button size="lg" disabled={running} onClick={() => setRunning(true)}>
            {running ? (
              <Loader2 aria-hidden className="size-4 animate-spin" />
            ) : (
              <Play aria-hidden className="size-4" />
            )}
            {running ? "Running the April tape" : "Run the April tape"}
          </Button>
        </Card>
      )}

      {isError && (
        <Card role="alert" className="p-5">
          <p className="font-medium">The run could not be completed.</p>
          <Button variant="secondary" className="mt-3" onClick={() => void refetch()}>
            Try again
          </Button>
        </Card>
      )}

      {state.ran && run && (
        <>
          {run.provisional && (
            <p className="flex items-center gap-2 rounded-lg bg-warn-tint px-3 py-2 text-sm text-warn">
              <CircleAlert aria-hidden className="size-4 shrink-0" />
              Provisional: E7 not run. Schedule 4 is not in the pack, so one eligibility test is outstanding.
            </p>
          )}
          <AnimatePresence>
            {run.system.availability < ALERT_FLOOR && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                className="flex items-center gap-2 overflow-hidden rounded-lg bg-danger-tint px-3 py-2 text-sm font-medium text-danger"
              >
                <BellRing aria-hidden className="size-4 shrink-0" />
                Availability is below the Calderwood alert threshold of US$500,000.
              </motion.p>
            )}
          </AnimatePresence>

          <div className="grid grid-cols-[minmax(0,1fr)_26rem] items-start gap-4">
            <div className="space-y-4">
              <Card className="overflow-hidden">
                <Comparison run={run} />
              </Card>
              <Card className="overflow-hidden">
                <h2 className="border-b border-line px-5 py-3 font-semibold">
                  Eligible pool bridge
                </h2>
                <Bridge run={run} selected={selected} onSelect={setSelected} />
              </Card>
              {line && (
                <Card className="overflow-hidden">
                  <LoanDrill line={line} />
                </Card>
              )}
            </div>

            <Card className="sticky top-32 overflow-hidden">
              <div role="tablist" className="flex gap-1 border-b border-line p-2">
                {TABS.map((name) => (
                  <button
                    key={name}
                    role="tab"
                    type="button"
                    aria-selected={tab === name}
                    onClick={() => setTab(name)}
                    className={clsx(
                      "h-8 flex-1 cursor-pointer rounded-md text-[0.8125rem] font-medium",
                      tab === name ? "bg-ink text-white" : "text-muted hover:bg-sand",
                    )}
                  >
                    {name}
                  </button>
                ))}
              </div>
              {tab === "Rules" && <RuleResults run={run} />}
              {tab === "Concentration" && <Concentrations run={run} />}
              {tab === "Covenants" && <Covenants run={run} />}
              <div className="border-t border-line px-5 py-2.5">
                <SectionLabel>Run digest</SectionLabel>
                <p className="mt-0.5 font-mono text-[0.6875rem] text-muted">
                  {run.digest.slice(0, 32)}
                </p>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
