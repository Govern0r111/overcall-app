import "./App.css";
import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { AppProvider, useApp } from "./context/AppContext";
import { Sidebar } from "./components/Sidebar";
import { Topbar } from "./components/Topbar";
import { Toaster } from "./components/ui/sonner";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { LandingPage } from "./features/landing/LandingPage";

const Overview = lazy(() => import("./pages/Overview"));
const Issues = lazy(() => import("./pages/Issues"));
const Providers = lazy(() => import("./pages/Providers"));
const Settings = lazy(() => import("./pages/Settings"));
const Logs = lazy(() => import("./pages/Logs"));
const AuthPage = lazy(() => import("./pages/AuthPage"));

const Shell = () => {
  const { theme } = useApp();
  const location = useLocation();
  const page = location.pathname === "/issues" ? <Issues /> :
    location.pathname === "/logs" ? <Logs /> :
    location.pathname === "/providers" ? <Providers /> :
    location.pathname === "/settings" ? <Settings /> :
    <Overview />;
  return (
    <ProtectedRoute>
      <div className="flex min-h-screen bg-background text-foreground">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <main className="min-w-0 flex-1">
            <div className="mx-auto max-w-6xl px-6 py-10 lg:px-12">
              <Suspense fallback={<p role="status" className="text-sm text-muted-foreground">Loading your page…</p>}>
                {page}
              </Suspense>
            </div>
          </main>
        </div>
      </div>
      <Toaster theme={theme} position="bottom-right" />
    </ProtectedRoute>
  );
};

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<Suspense fallback={null}><AuthPage mode="login" /></Suspense>} />
        <Route path="/signup" element={<Suspense fallback={null}><AuthPage mode="signup" /></Suspense>} />
        <Route path="/forgot" element={<Suspense fallback={null}><AuthPage mode="forgot" /></Suspense>} />
        <Route
          path="/*"
          element={
            <AppProvider>
              <Shell />
            </AppProvider>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
