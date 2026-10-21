import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type BrowserAccess = {
  csrf: string;
  invalidate: () => void;
  logout: () => Promise<void>;
};
type Session = { csrf_token: string; expires_at: number };
type Mode = "loading" | "bearer" | "browser-session" | "unavailable";

// The cookie stays HttpOnly. Only short-lived CSRF metadata reaches this component.
export function AuthBoundary({
  children,
}: {
  children: (access: BrowserAccess | null) => ReactNode;
}) {
  const [mode, setMode] = useState<Mode>("loading");
  const [session, setSession] = useState<Session | null>(null);
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const generation = useRef(0);
  const invalidate = useCallback(() => {
    generation.current += 1;
    setActive(false);
    setMessage(
      "Workspace access ended. Sign in again or check your membership.",
    );
  }, []);

  const check = useCallback(async () => {
    const current = ++generation.current;
    setBusy(true);
    setActive(false);
    try {
      const config = await fetch("/auth/config", {
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
      });
      if (current !== generation.current) return;
      if (config.status === 404) {
        setMode("bearer");
        return;
      }
      if (!config.ok || (await config.json()).mode !== "browser-session")
        throw new Error("Sign-in settings could not be loaded. Try again.");
      if (current !== generation.current) return;
      setMode("browser-session");
      const response = await fetch("/auth/session", {
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
      });
      if (current !== generation.current) return;
      if (response.status === 401) {
        setSession(null);
        setMessage("");
        return;
      }
      if (!response.ok)
        throw new Error("Your sign-in could not be checked. Try again.");
      const data = await response.json();
      if (current !== generation.current) return;
      if (
        !/^[A-Za-z0-9_-]{43}$/.test(data.csrf_token) ||
        !Number.isSafeInteger(data.expires_at) ||
        data.expires_at * 1000 <= Date.now() ||
        data.expires_at * 1000 > Date.now() + 901000
      )
        throw new Error("Your sign-in has expired or could not be checked.");
      setSession(data);
      setActive(true);
      setMessage("");
    } catch (error) {
      if (current !== generation.current) return;
      setMode("unavailable");
      setMessage(
        error instanceof Error
          ? error.message
          : "Sign-in is unavailable. Try again.",
      );
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }, []);

  useEffect(() => {
    void check();
    return () => {
      generation.current += 1;
    };
  }, [check]);

  useEffect(() => {
    if (!active || !session) return;
    function expired() {
      if (session && Date.now() >= session.expires_at * 1000) invalidate();
    }
    const timer = setTimeout(
      invalidate,
      Math.max(0, session.expires_at * 1000 - Date.now()),
    );
    window.addEventListener("focus", expired);
    document.addEventListener("visibilitychange", expired);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("focus", expired);
      document.removeEventListener("visibilitychange", expired);
    };
  }, [active, session, invalidate]);

  async function logout() {
    // Unmount first, even if the network cannot confirm server-side logout.
    const current = ++generation.current;
    setActive(false);
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/auth/logout", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        headers: session ? { "X-Atlas-CSRF": session.csrf_token } : {},
      });
      if (current !== generation.current) return;
      if (response.status !== 204)
        throw new Error("Sign-out was not confirmed. Please try again.");
      setSession(null);
      setMessage(
        "Signed out of ATLAS. Your identity provider may still be signed in.",
      );
    } catch {
      if (current === generation.current)
        setMessage(
          "Sign-out was not confirmed. Your workspace is hidden; retry sign-out to end the server session.",
        );
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }

  if (mode === "bearer") return children(null);
  if (mode === "browser-session" && active && session)
    return children({ csrf: session.csrf_token, invalidate, logout });
  return (
    <main className="content">
      <section className="connect" aria-label="Workspace sign-in">
        <div>
          <h1>ATLAS</h1>
          <h2>
            {busy ? "Checking your sign-in…" : "Sign in to your workspace"}
          </h2>
          {message && <p role="alert">{message}</p>}
          {!busy && mode === "browser-session" && (
            <form method="post" action="/auth/start">
              <button className="primary" type="submit">
                Sign in
              </button>
            </form>
          )}
          {!busy && (
            <button className="secondary" onClick={() => void check()}>
              Check sign-in
            </button>
          )}
          {!busy && session && (
            <button className="secondary" onClick={() => void logout()}>
              Retry sign-out
            </button>
          )}
        </div>
      </section>
    </main>
  );
}
