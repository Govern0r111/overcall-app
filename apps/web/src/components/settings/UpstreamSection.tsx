import { useApp } from "../../context/AppContext";
import { useSaveSettings } from "../../hooks/queries";
import { Segmented, SettingRow, SettingsSection } from "./SettingsSection";

export const UpstreamSection = () => {
  const { settings } = useApp();
  const save = useSaveSettings();
  const s = settings!;
  return (
    <SettingsSection
      testId="settings-upstream"
      title="Proxy upstreams"
      description="Your API keys travel in the Authorization header, are forwarded to the provider, and are never stored or logged. We keep metadata and payload hashes only."
    >
      <SettingRow
        label="OpenAI requests go to"
        help={
          s.openai_upstream === "mock"
            ? "The built-in mock LLM server. No real calls, no cost — good for trying things out."
            : "api.openai.com using the key your app sends. Real calls, real cost. Streaming responses are buffered in v1."
        }
        control={
          <Segmented<"mock" | "real">
            testIdPrefix="openai-upstream"
            value={s.openai_upstream}
            options={[{ value: "mock", label: "Local mock" }, { value: "real", label: "Real OpenAI" }]}
            onChange={(v) => save.mutate({ ...s, openai_upstream: v })}
          />
        }
      />
      <SettingRow
        label="Stripe requests go to"
        help="Stripe test mode. Live keys (sk_live_…) are rejected by the proxy in v1."
        control={<span className="font-mono text-xs text-muted-foreground">test mode</span>}
      />
      <SettingRow
        label="AWS"
        help="Stubbed. The pricing slot exists but requests aren't forwarded yet."
        control={<span className="font-mono text-xs text-muted-foreground">stub</span>}
      />
    </SettingsSection>
  );
};
