import { ReactNode, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { authClient, AuthUser } from "./authClient";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    let active = true;
    authClient.me().then(
      (session) => {
        if (active) {
          setUser(session);
          setReady(true);
        }
      },
      () => {
        if (active) {
          setAuthError("Could not check your session. Refresh the page and try again.");
          setReady(true);
        }
      },
    );
    const unsubscribe = authClient.onAuthStateChange((session) => setUser(session));
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  if (!ready) return <div className="grid min-h-screen place-items-center bg-background text-muted-foreground">Loading your workspace…</div>;
  if (authError) return <div className="grid min-h-screen place-items-center bg-background px-6 text-sm text-destructive" role="alert">{authError}</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}
