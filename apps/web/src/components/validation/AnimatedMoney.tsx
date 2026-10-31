import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { formatUsd } from "../../lib/format";

/** A figure that counts to its new value, so a recalculation is visible as it happens. */
export function AnimatedMoney({ value, className }: { value: number; className?: string }) {
  const [shown, setShown] = useState(value);
  const previous = useRef(value);
  const reduced = useReducedMotion();

  useEffect(() => {
    if (previous.current === value) {
      return;
    }
    const from = previous.current;
    previous.current = value;
    if (reduced) {
      setShown(value);
      return;
    }
    const controls = animate(from, value, { duration: 0.7, ease: "easeOut", onUpdate: setShown });
    return () => controls.stop();
  }, [value, reduced]);

  return <span className={`numeric ${className ?? ""}`}>{formatUsd(Math.round(shown))}</span>;
}
