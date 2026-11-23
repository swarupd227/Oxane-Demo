import clsx from "clsx";
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-white shadow-[0_1px_2px_rgb(16_24_40/0.05)] hover:bg-accent-strong",
  secondary:
    "border border-line bg-surface text-ink-soft shadow-[0_1px_2px_rgb(16_24_40/0.05)] hover:bg-canvas hover:text-ink",
  ghost: "text-muted hover:bg-sand hover:text-ink",
};

const sizes: Record<Size, string> = {
  sm: "h-8 gap-1.5 px-3 text-[0.8125rem]",
  md: "h-10 gap-2 px-4 text-sm",
  lg: "h-12 gap-2 px-5 text-[0.9375rem]",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={clsx(
        "inline-flex cursor-pointer items-center justify-center rounded-lg font-medium whitespace-nowrap",
        "transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    />
  );
}
