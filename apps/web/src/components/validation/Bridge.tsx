import clsx from "clsx";
import { ChevronRight } from "lucide-react";
import { motion } from "motion/react";
import { formatUsd } from "../../lib/format";
import type { RunResult } from "../../lib/workbench";
import { Tooltip } from "../ui/Tooltip";
import { AnimatedMoney } from "./AnimatedMoney";

export interface Step {
  id: string;
  label: string;
  detail: string;
  amount: number;
  drill: boolean;
}

export function bridgeSteps(run: RunResult): Step[] {
  const steps: Step[] = run.pool_bridge.lines.map((line) => ({
    id: line.rule_id,
    label: line.rule_id === "E1" ? "Over 30 days past due" : "Duplicate VINs",
    detail: `${line.loans} loans failing ${line.rule_id}, counted as eligible by the borrower`,
    amount: line.amount,
    drill: true,
  }));
  if (run.system.excess > 0) {
    steps.push({
      id: "C2",
      label: "Dealer concentration",
      detail: "Sunrise Motors, as matched, exceeds the 5% limit",
      amount: run.system.excess,
      drill: false,
    });
  }
  return steps;
}

function Total({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <div className="grid grid-cols-[17rem_minmax(0,1fr)_11rem] items-center gap-5 px-5 py-3">
      <div>
        <p className="text-sm font-semibold">{label}</p>
        <p className="text-xs text-muted">{note}</p>
      </div>
      <div aria-hidden className="h-px bg-line" />
      <AnimatedMoney value={value} className="text-right text-lg font-semibold tracking-tight" />
    </div>
  );
}

interface BridgeProps {
  run: RunResult;
  selected: string | null;
  onSelect: (id: string) => void;
}

/**
 * The gap is about 2% of the pool, so a chart from zero would hide it and a cut axis would
 * exaggerate it. Totals are figures, and the bars are drawn to the scale of the gap alone.
 */
export function Bridge({ run, selected, onSelect }: BridgeProps) {
  const steps = bridgeSteps(run);
  const total = steps.reduce((sum, step) => sum + step.amount, 0);
  const borrower = run.pool_bridge.borrower;
  let offset = 0;

  return (
    <div>
      <Total label="Borrower's eligible pool" value={borrower} note="From the certificate" />
      <div className="border-y border-sand">
        {steps.map((step) => {
          const left = (offset / total) * 100;
          const width = (step.amount / total) * 100;
          offset += step.amount;
          const body = (
            <>
              <div className="min-w-0">
                <p className="flex items-center gap-1 text-sm font-medium">
                  {step.label}
                  {step.drill && <ChevronRight aria-hidden className="size-3.5 text-muted" />}
                </p>
                <p className="truncate text-xs text-muted">{step.detail}</p>
              </div>
              <div className="relative h-6">
                <motion.div
                  layout
                  initial={{ opacity: 0, scaleX: 0 }}
                  animate={{ opacity: 1, scaleX: 1 }}
                  transition={{ duration: 0.45, ease: "easeOut" }}
                  className={clsx(
                    "absolute inset-y-0 origin-left rounded",
                    selected === step.id ? "bg-ink" : "bg-subtle",
                  )}
                  style={{ left: `${left}%`, width: `${width}%` }}
                />
              </div>
              <span className="numeric text-right text-sm font-medium">
                -{formatUsd(step.amount)}
              </span>
            </>
          );
          const row =
            "grid w-full grid-cols-[17rem_minmax(0,1fr)_11rem] items-center gap-5 px-5 py-2.5 text-left";
          return (
            <Tooltip key={step.id} content={`${formatUsd(step.amount)}: ${step.detail}`}>
              {step.drill ? (
                <button
                  type="button"
                  aria-pressed={selected === step.id}
                  onClick={() => onSelect(step.id)}
                  className={clsx(row, "cursor-pointer hover:bg-canvas",
                    selected === step.id && "bg-sand")}
                >
                  {body}
                </button>
              ) : (
                <motion.div
                  layout
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className={row}
                  tabIndex={0}
                >
                  {body}
                </motion.div>
              )}
            </Tooltip>
          );
        })}
      </div>
      <Total
        label={run.system.excess > 0 ? "System eligible pool after excess concentration" : "System eligible pool"}
        value={run.system.eligible_pool - run.system.excess}
        note={`Unexplained: ${formatUsd(run.pool_bridge.unexplained)}`}
      />
      <p className="px-5 pb-3 text-xs text-muted">
        Bars show the {formatUsd(total)} difference only, not the whole pool.
      </p>
    </div>
  );
}
