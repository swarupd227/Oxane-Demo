import clsx from "clsx";
import type { HTMLAttributes, ReactNode } from "react";

const cardTones = {
  default: "border border-line bg-surface shadow-card",
  inverse: "bg-ink text-white",
  outline: "border border-dashed border-line",
};

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  tone?: keyof typeof cardTones;
}

export function Card({ tone = "default", className, ...props }: CardProps) {
  return <div className={clsx("rounded-xl", cardTones[tone], className)} {...props} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={clsx("animate-pulse rounded bg-sand", className)} />;
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[0.6875rem] font-semibold tracking-[0.08em] text-muted uppercase">
      {children}
    </p>
  );
}

export function Money({ value, className }: { value: string; className?: string }) {
  return <span className={clsx("numeric", className)}>{value}</span>;
}
