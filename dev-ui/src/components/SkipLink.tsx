import { useEffect, useState } from "react";

/** Skip to main content link for keyboard users - standard accessibility
 * pattern. Only visible on focus. */
export function SkipLink() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Tab") setVisible(true);
    }
    function handleClick() {
      setVisible(false);
    }
    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("click", handleClick);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("click", handleClick);
    };
  }, []);

  return (
    <a
      href="#main-content"
      className={`sr-only focus:not-sr-only fixed top-4 left-4 z-[100] rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white transition-opacity ${
        visible ? "opacity-100" : "opacity-0 pointer-events-none"
      }`}
    >
      Skip to main content
    </a>
  );
}