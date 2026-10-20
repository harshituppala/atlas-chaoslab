import { useLayoutEffect, useRef, type ReactNode } from "react";

const focusableSelector =
  'a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function Dialog({
  name,
  className,
  canClose = true,
  onClose,
  children,
}: {
  name: string;
  className: string;
  canClose?: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDialogElement>(null);
  const controls = () =>
    Array.from(
      panel.current?.querySelectorAll<HTMLElement>(focusableSelector) || [],
    ).filter((element) => element.getClientRects().length > 0);
  useLayoutEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    if (panel.current && !panel.current.open) panel.current.showModal();
    (controls()[0] || panel.current)?.focus();
    return () => {
      panel.current?.close();
      document.body.style.overflow = previousOverflow;
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return (
    <dialog
      ref={panel}
      role="dialog"
      aria-modal="true"
      aria-label={name}
      tabIndex={-1}
      className={className}
      onCancel={(event) => {
        event.preventDefault();
        if (canClose) onClose();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && canClose) {
          event.preventDefault();
          event.stopPropagation();
          onClose();
        }
        if (event.key === "Tab") {
          const elements = controls();
          const first = elements[0];
          const last = elements.at(-1);
          if (!first) {
            event.preventDefault();
            panel.current?.focus();
          } else if (
            event.shiftKey &&
            (document.activeElement === first ||
              document.activeElement === panel.current)
          ) {
            event.preventDefault();
            last?.focus();
          } else if (
            !event.shiftKey &&
            (document.activeElement === last ||
              document.activeElement === panel.current)
          ) {
            event.preventDefault();
            first.focus();
          }
        }
      }}
    >
      {children}
    </dialog>
  );
}
