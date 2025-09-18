import type { ReactElement } from "react";

export default function Spinner({
  size = 24,
  className = "text-blue-500",
}: {
  size?: number;
  className?: string;
}): ReactElement {
  const s = { width: size, height: size } as const;
  return (
    <svg
      style={s}
      className={`animate-spin ${className}`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      role="status"
      aria-label="loading"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      ></circle>
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      ></path>
    </svg>
  );
}

