import { useState } from "react";
import { NavLink } from "react-router-dom";
import { AlertTriangle, FileText, LayoutDashboard, LogOut, PanelLeftClose, PanelLeftOpen, Server, Settings, ShieldCheck } from "lucide-react";
import { cn } from "../lib/utils";
import { useOverview } from "../hooks/queries";
import { authClient } from "../auth/authClient";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

const NAV = [
  { to: "/app", label: "Overview", icon: LayoutDashboard, id: "overview" },
  { to: "/issues", label: "Issues", icon: AlertTriangle, id: "issues" },
  { to: "/logs", label: "Logs", icon: FileText, id: "logs" },
  { to: "/providers", label: "Providers", icon: Server, id: "providers" },
  { to: "/settings", label: "Settings", icon: Settings, id: "settings" },
];

export const Sidebar = ({ mobileOpen = false, onNavigate }: { mobileOpen?: boolean; onNavigate?: () => void }) => {
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("cg-sidebar") === "1");
  const { data } = useOverview();
  const openIssues = data?.has_data ? Object.values(data.severity_breakdown).reduce((a, b) => a + b, 0) : 0;

  const toggle = () => {
    localStorage.setItem("cg-sidebar", collapsed ? "0" : "1");
    setCollapsed(!collapsed);
  };

  return (
    <aside
      data-testid="sidebar"
      className={cn(
        "fixed inset-y-0 left-0 z-40 h-screen shrink-0 flex-col border-r border-border bg-card transition-[width,transform] duration-200 md:sticky md:top-0 md:z-auto md:translate-x-0",
        mobileOpen ? "flex translate-x-0" : "hidden md:flex",
        collapsed ? "w-[88px]" : "w-[232px]",
      )}
    >
      <div className={cn("flex h-16 items-center gap-2.5 border-b border-divider", collapsed ? "justify-center px-2" : "px-5")}>
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-primary/20 bg-primary/[0.06]">
          <ShieldCheck className="h-4.5 w-4.5 text-primary" strokeWidth={1.75} />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <span className="block truncate text-sm font-semibold tracking-tight">Overcall</span>
            <span className="block text-xs text-muted-foreground">API spend monitor</span>
          </div>
        )}
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-3" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon, id }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={onNavigate}
            data-testid={`nav-${id}-link`}
            className={({ isActive }) =>
              cn(
                "group relative flex items-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                collapsed ? "flex-col gap-1 px-1 py-2.5 text-xs" : "gap-3 px-3 py-2 text-sm",
                isActive && "bg-secondary font-medium text-foreground",
              )
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={cn(
                    "absolute left-0 top-1/2 h-5 -translate-y-1/2 rounded-r-full bg-primary transition-all duration-200",
                    isActive ? "w-0.5 opacity-100" : "w-0 opacity-0",
                  )}
                />
                <Icon
                  className="h-4 w-4 shrink-0 stroke-[1.75] transition-colors group-hover:text-foreground"
                  strokeWidth={1.75}
                />
                <span>{label}</span>
                {id === "issues" && openIssues > 0 && !collapsed && (
                  <span
                    data-testid="nav-issues-count"
                    className="ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full border border-border px-1.5 font-mono text-xs text-muted-foreground"
                  >
                    {openIssues}
                  </span>
                )}
                {id === "issues" && openIssues > 0 && collapsed && (
                  <span
                    data-testid="nav-issues-count"
                    className="absolute right-1.5 top-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full border border-border bg-card px-1 font-mono text-[10px] text-muted-foreground"
                  >
                    {openIssues}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-divider p-3">
        <button
          type="button"
          aria-label="Log out"
          title={collapsed ? "Log out" : undefined}
          onClick={async () => {
            try {
              await authClient.logout();
              navigate("/login", { replace: true });
            } catch (error) {
              toast.error(error instanceof Error ? error.message : "Could not log out.");
            }
          }}
          className={cn(
            "mb-1 flex w-full items-center rounded-md py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground",
            collapsed ? "justify-center" : "gap-3 px-3",
          )}
        >
          <LogOut className="h-4 w-4" strokeWidth={1.75} />
          {!collapsed && <span>Log out</span>}
        </button>
        <button
          type="button"
          onClick={toggle}
          data-testid="sidebar-toggle-button"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "flex w-full items-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
            collapsed ? "flex-col gap-1 py-2.5 text-xs" : "gap-3 px-3 py-2 text-sm",
          )}
        >
          {collapsed ? <PanelLeftOpen className="h-4 w-4" strokeWidth={1.75} /> : <PanelLeftClose className="h-4 w-4" strokeWidth={1.75} />}
          <span>{collapsed ? "Expand" : "Collapse"}</span>
        </button>
      </div>
    </aside>
  );
};
