import { ReactNode, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { authClient, AuthUser } from "./authClient";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    authClient.me().then((session) => {
      setUser(session);
      setReady(true);
    });
  }, []);

  if (!ready) return <div className="grid min-h-screen place-items-center bg-background text-muted-foreground">Loading your workspace…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}
