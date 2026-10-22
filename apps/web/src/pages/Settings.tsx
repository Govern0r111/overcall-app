import thresholdContract from "../../../../contract/thresholds.json";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, PageHeader } from "../components/PageHeader";
import { DemoBanner, ErrorBox, Loading, Select } from "../components/common";
import { ThemeToggle } from "../components/ThemeToggle";
import { ApiError } from "../lib/api";
import {
  useAccuracy,
  useDeleteAllData,
  useDeleteDemo,
  useMe,
  useResetSettings,
  useRules,
  useSaveSettings,
  useSettings,
} from "../hooks/queries";
import type { Settings as SettingsT } from "../lib/api";

type DialogAction = "deleteDemo" | "deleteAll" | "reset" | "real" | null;
type ThresholdRule = { min: number; max: number; default: number };
const thresholdRules = thresholdContract.thresholds as Record<string, ThresholdRule>;

const Section = ({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) => (
  <Card className="mb-6 p-6">
    <h2 className="text-base font-semibold">{title}</h2>
    {hint && <p className="mt-1 text-sm text-muted-foreground">{hint}</p>}
    <div className="mt-4">{children}</div>
  </Card>
);

const num = "h-9 w-36 rounded-md border border-input bg-card px-2 font-mono text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary";

export default function Settings() {
  const { data, isLoading, error } = useSettings();
  const rules = useRules();
  const me = useMe();
  const accuracy = useAccuracy();
  const save = useSaveSettings();
  const reset = useResetSettings();
  const delDemo = useDeleteDemo();
  const delAll = useDeleteAllData();
  const [form, setForm] = useState<SettingsT | null>(null);
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [dialog, setDialog] = useState<DialogAction>(null);
  const [typedConfirmation, setTypedConfirmation] = useState("");
  const [realConfirmation, setRealConfirmation] = useState(false);
  const confirmationInputRef = useRef<HTMLInputElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  useEffect(() => {
    if (dialog === "deleteAll") confirmationInputRef.current?.focus();
    else if (dialog) cancelButtonRef.current?.focus();
  }, [dialog]);

  const validationErrors = useMemo(() => {
    const errors: Record<string, string> = {};
    if (!form) return errors;
    if (!Number.isFinite(form.usd_inr_rate) || form.usd_inr_rate <= 0 || form.usd_inr_rate > 1_000_000) {
      errors.usd_inr_rate = "Enter a rate greater than 0 and no more than 1,000,000.";
    }
    if (!Number.isInteger(form.retention_days) || form.retention_days < 1 || form.retention_days > 90) {
      errors.retention_days = "Choose a whole number from 1 to 90 days.";
    }
    Object.entries(thresholdRules).forEach(([key, spec]) => {
      const value = form.thresholds[key];
      if (!Number.isInteger(value) || value < spec.min || value > spec.max) {
        errors[key] = `Enter a whole number from ${spec.min} to ${spec.max}.`;
      }
    });
    const short = form.thresholds.short_window_s;
    const long = form.thresholds.long_window_s;
    if (Number.isFinite(short) && Number.isFinite(long) && long <= short) {
      errors.long_window_s = "Long window must be greater than the short window.";
    }
    return errors;
  }, [form]);

  const dirty = Boolean(form && JSON.stringify(form) !== JSON.stringify(data));
  useEffect(() => {
    if (!dirty) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [dirty]);

  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!form) return null;

  const set = (patch: Partial<SettingsT>) => {
    setServerErrors({});
    setForm((current) => current ? { ...current, ...patch } : current);
  };
  const fieldErrors = { ...validationErrors, ...serverErrors };
  const hasErrors = Object.keys(fieldErrors).length > 0;
  const saveSettings = () => {
    setServerErrors({});
    save.mutate(form, {
      onError: (cause) => {
        if (!(cause instanceof ApiError) || !cause.fields?.length) return;
        const mapped: Record<string, string> = {};
        for (const field of cause.fields) {
          const key = field.path.split(".").at(-1);
          if (key && (key in thresholdRules || key === "usd_inr_rate" || key === "retention_days")) {
            mapped[key] = field.message;
          }
        }
        setServerErrors(mapped);
      },
    });
  };
  const realBlocked = form.upstream_mode === "real" && (!form.confirm_real_upstream || !me.data?.real_upstream_available);
  const closeDialog = () => {
    setDialog(null);
    setTypedConfirmation("");
    setRealConfirmation(false);
  };
  const cancelDialog = () => {
    if (dialog === "real") {
      set({
        upstream_mode: data?.upstream_mode ?? "mock",
        confirm_real_upstream: data?.confirm_real_upstream ?? false,
      });
    }
    closeDialog();
  };
  const confirmDialog = () => {
    if (dialog === "deleteDemo") delDemo.mutate(undefined, { onSuccess: closeDialog });
    if (dialog === "deleteAll") delAll.mutate(undefined, { onSuccess: closeDialog });
    if (dialog === "reset") reset.mutate(undefined, { onSuccess: closeDialog });
    if (dialog === "real" && realConfirmation) {
      set({ confirm_real_upstream: true });
      closeDialog();
    }
  };
  const dialogTitle = {
    deleteDemo: "Delete demo data?",
    deleteAll: "Delete all data?",
    reset: "Reset settings?",
    real: "Enable real provider traffic?",
  }[dialog ?? "reset"];
  const dialogDescription = {
    deleteDemo: "This removes the demo requests and issues from this workspace. Real traffic is not affected.",
    deleteAll: "This permanently deletes all request logs and issues, including real traffic.",
    reset: "This restores the default settings. Your logs and issues are not changed.",
    real: "Requests will be sent to OpenAI using your provider key and may cost real money. Overcall does not control provider billing.",
  }[dialog ?? "reset"];
  const dialogCanConfirm =
    dialog !== "deleteAll" || typedConfirmation === "delete my data";
  const actionPending = delDemo.isPending || delAll.isPending || reset.isPending;

  return (
    <>
      <PageHeader
        title="Settings"
        description="Choose how findings are detected and displayed. Changes apply to the next detection run."
        actions={
          <>
            <Button variant="outline" onClick={() => setDialog("reset")} disabled={reset.isPending}>Reset to defaults</Button>
            <Button onClick={saveSettings} disabled={!dirty || save.isPending || realBlocked || hasErrors}>
              {save.isPending ? "Saving…" : "Save changes"}
            </Button>
          </>
        }
      />
      <DemoBanner />
      {dirty && <p className="mb-4 text-xs text-muted-foreground" role="status">You have unsaved changes. Save them before leaving this page.</p>}
      {hasErrors && (
        <p className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive" role="alert">
          Fix the highlighted values before saving.
        </p>
      )}

      <Section title="Appearance" hint="Choose a theme for this browser.">
        <ThemeToggle />
      </Section>

      <Section title="Currency" hint="Costs are stored in USD and converted for display. The exchange rate is set by you.">
        <div className="flex flex-wrap items-end gap-4">
          <Select label="Currency" value={form.currency} onChange={(value) => set({ currency: value as SettingsT["currency"] })} options={[
            { value: "INR", label: "INR (₹)" }, { value: "USD", label: "USD ($)" },
          ]} />
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            USD → INR rate (set by you)
            <input
              aria-invalid={Boolean(fieldErrors.usd_inr_rate)}
              type="number" step="0.1" min="0.01" max="1000000" className={num} value={form.usd_inr_rate}
              onChange={(event) => set({ usd_inr_rate: Number(event.target.value) })}
            />
            {fieldErrors.usd_inr_rate && <span className="text-destructive">{fieldErrors.usd_inr_rate}</span>}
          </label>
        </div>
      </Section>

      <Section title="Detection rules" hint="Turn rules on or off and tune their documented thresholds.">
        {rules.isLoading && <Loading />}
        {rules.error && <ErrorBox error={rules.error} />}
        <ul className="divide-y divide-border">
          {rules.data?.map((rule) => (
            <li key={rule.id} className="py-4" data-testid={`rule-${rule.id}`}>
              <div className="flex items-start gap-3">
                <input
                  id={`rule-${rule.id}-enabled`}
                  type="checkbox" className="mt-1 h-4 w-4" checked={form.rules_enabled[rule.id] ?? rule.default_enabled}
                  onChange={(event) => set({ rules_enabled: { ...form.rules_enabled, [rule.id]: event.target.checked } })}
                />
                <label htmlFor={`rule-${rule.id}-enabled`} className="cursor-pointer">
                  <span className="text-sm font-medium">{rule.name}</span>
                  <span className="ml-2 text-xs text-muted-foreground">tier {rule.tier}{rule.tier === 3 ? " · experimental" : ""}</span>
                  <span className="block text-sm text-muted-foreground">{rule.description}</span>
                </label>
              </div>
              <div className="ml-7 mt-3 flex flex-wrap gap-4">
                {rule.threshold_keys.map((key) => {
                  const spec = thresholdRules[key];
                  return (
                    <label key={key} className="flex flex-col gap-1 text-xs text-muted-foreground">
                      {key} ({spec.min}–{spec.max})
                      <input
                        aria-invalid={Boolean(fieldErrors[key])}
                        type="number" min={spec.min} max={spec.max} step="1" className={num}
                        value={Number.isFinite(form.thresholds[key]) ? form.thresholds[key] : ""}
                        onChange={(event) => set({
                          thresholds: { ...form.thresholds, [key]: event.target.value === "" ? Number.NaN : Number(event.target.value) },
                        })}
                      />
                      {fieldErrors[key] && <span className="max-w-56 text-destructive">{fieldErrors[key]}</span>}
                    </label>
                  );
                })}
              </div>
            </li>
          ))}
        </ul>
        <label className="mt-4 flex items-start gap-3 text-sm">
          <input type="checkbox" className="mt-1 h-4 w-4" checked={form.tier3_enabled}
            onChange={(event) => set({ tier3_enabled: event.target.checked })} />
          <span>Include experimental tier 3 findings in the results. These checks may be less accurate.</span>
        </label>
      </Section>

      <Section title="Upstream" hint="Mock mode uses the built-in provider simulator. Real mode can incur provider charges.">
        <Select
          label="Upstream mode"
          value={form.upstream_mode}
          onChange={(value) => {
            if (value === "real") {
              set({ upstream_mode: "real", confirm_real_upstream: false });
              setDialog("real");
            } else {
              set({ upstream_mode: value as SettingsT["upstream_mode"], confirm_real_upstream: false });
            }
          }}
          options={[
            { value: "mock", label: "Mock (local simulator)" },
            { value: "test", label: "Test" },
            ...(me.data?.real_upstream_available || form.upstream_mode === "real" ? [{ value: "real", label: "Real provider" }] : []),
          ]}
        />
        {form.upstream_mode === "real" && !me.data?.real_upstream_available && (
          <p className="mt-2 text-sm text-muted-foreground">Real upstream is disabled on this server. Choose Mock or Test.</p>
        )}
        <label className="mt-4 flex flex-col gap-1 text-xs text-muted-foreground">
          Keep logs for (days)
          <input
            aria-invalid={Boolean(fieldErrors.retention_days)}
            type="number" min="1" max="90" step="1" className={num} value={form.retention_days}
            onChange={(event) => set({ retention_days: Number(event.target.value) })}
          />
          {fieldErrors.retention_days && <span className="text-destructive">{fieldErrors.retention_days}</span>}
        </label>
      </Section>

      <Section title="Detection accuracy" hint="Synthetic and real-traffic results are kept separate.">
        {accuracy.isLoading && <Loading />}
        {accuracy.error && <ErrorBox error={accuracy.error} />}
        {accuracy.data?.datasets.map((dataset) => (
          <details key={dataset.id} className="mb-4 rounded-md border border-border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              {dataset.label} · {dataset.requests} requests
            </summary>
            <p className="mb-2 mt-2 text-xs text-muted-foreground">{dataset.note}</p>
            {dataset.rules.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="text-left text-muted-foreground">
                    <tr><th className="py-1">Rule</th><th>Precision</th><th>Recall</th><th>Flagged</th></tr>
                  </thead>
                  <tbody>
                    {dataset.rules.map((rule) => (
                      <tr key={rule.rule_id} className="border-t border-border/60 font-mono">
                        <td className="py-1.5">{rule.rule_id}</td>
                        <td>{rule.precision != null ? `${Math.round(rule.precision * 100)}%` : "—"}</td>
                        <td>{rule.recall != null ? `${Math.round(rule.recall * 100)}%` : "—"}</td>
                        <td>{rule.true_positives}/{rule.flagged}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="text-xs text-muted-foreground">Accuracy has not been measured for this dataset yet.</p>}
          </details>
        ))}
      </Section>

      <Section title="Data" hint="Destructive actions cannot be undone.">
        <div className="flex flex-wrap gap-3">
          <Button variant="outline" onClick={() => setDialog("deleteDemo")} disabled={delDemo.isPending}>Delete demo data</Button>
          <Button variant="destructive" onClick={() => setDialog("deleteAll")} disabled={delAll.isPending}>Delete all logs and issues</Button>
        </div>
      </Section>

      {dialog && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4">
          <section
            role="alertdialog" aria-modal="true" aria-labelledby="settings-dialog-title" aria-describedby="settings-dialog-description"
            className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-none"
          >
            <h2 id="settings-dialog-title" className="text-lg font-semibold">{dialogTitle}</h2>
            <p id="settings-dialog-description" className="mt-2 text-sm text-muted-foreground">{dialogDescription}</p>
            {dialog === "deleteAll" && (
              <label className="mt-4 block text-sm">
                Type <code className="font-mono">delete my data</code> to confirm
                <input ref={confirmationInputRef} value={typedConfirmation} onChange={(event) => setTypedConfirmation(event.target.value)}
                  className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 font-mono text-sm" />
              </label>
            )}
            {dialog === "real" && (
              <label className="mt-4 flex items-start gap-3 text-sm">
                <input type="checkbox" className="mt-1 h-4 w-4" checked={realConfirmation}
                  onChange={(event) => setRealConfirmation(event.target.checked)} />
                <span>I understand that real provider requests may incur charges.</span>
              </label>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <Button ref={cancelButtonRef} variant="outline" onClick={cancelDialog}>Cancel</Button>
              <Button
                variant={dialog === "deleteAll" ? "destructive" : "default"}
                onClick={confirmDialog}
                disabled={!dialogCanConfirm || actionPending || (dialog === "real" && !realConfirmation)}
              >
                {dialog === "real" ? "Confirm real mode" : dialog === "deleteDemo" ? "Delete demo data" : dialog === "deleteAll" ? "Delete all data" : dialog === "reset" ? "Reset settings" : ""}
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
