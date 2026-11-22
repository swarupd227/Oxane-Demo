import clsx from "clsx";

const TONES = [
  "bg-[#efe3d3] text-[#6b4a1f]",
  "bg-[#dfe8ef] text-[#2f4b63]",
  "bg-[#e6e2ef] text-[#4a3f6b]",
  "bg-[#dcebe3] text-[#2f5a44]",
  "bg-[#f3dfdc] text-[#7a3328]",
];

export function initialsOf(name: string): string {
  const words = name.replace(/[^A-Za-z ]/g, " ").split(/\s+/).filter(Boolean);
  if (words.length === 1 && words[0].length <= 3 && words[0] === words[0].toUpperCase()) {
    return words[0];
  }
  return words
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join("");
}

/** A person or team, as initials in a circle; the full name is in the title and for readers. */
export function Avatar({ name, size = "sm", className }: { name: string; size?: "sm" | "md"; className?: string }) {
  const initials = initialsOf(name);
  const tone = TONES[[...name].reduce((sum, char) => sum + char.charCodeAt(0), 0) % TONES.length];
  return (
    <span
      title={name}
      className={clsx(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold",
        size === "sm" ? "size-6 text-[0.625rem]" : "size-8 text-xs",
        tone,
        className,
      )}
    >
      <span aria-hidden>{initials}</span>
      <span className="sr-only">{name}</span>
    </span>
  );
}
