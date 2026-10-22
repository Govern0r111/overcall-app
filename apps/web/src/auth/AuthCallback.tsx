import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { authClient } from "./authClient";
import { safeRedirect } from "./safeRedirect";

export function AuthCallback() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [error, setError] = useState("");
  const next = params.get("next");

  useEffect(() => {
    let active = true;
    authClient.me().then(
      (user) => {
        if (!active) return;
        if (user) navigate(safeRedirect(next), { replace: true });
        else setError("We could not confirm your sign-in. Please try again.");
      },
      () => {
        if (active) setError("We could not complete sign-in. Please try again.");
      },
    );
    return () => {
      active = false;
    };
  }, [navigate, next]);

  return (
    <main className="grid min-h-screen place-items-center bg-background px-6 text-center">
      {error ? (
        <div>
          <p className="text-sm text-destructive" role="alert">{error}</p>
          <a className="mt-4 inline-block text-sm text-primary underline" href="/login">Back to log in</a>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground" role="status">Completing sign-in…</p>
      )}
    </main>
  );
}
