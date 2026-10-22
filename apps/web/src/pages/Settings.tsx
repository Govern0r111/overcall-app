import { PageHeader } from "../components/PageHeader";
import { AppearanceSection } from "../components/settings/AppearanceSection";
import { RulesSection } from "../components/settings/RulesSection";
import { WindowsSection } from "../components/settings/WindowsSection";
import { UpstreamSection } from "../components/settings/UpstreamSection";
import { DataSection } from "../components/settings/DataSection";
import { AccuracySection } from "../components/settings/AccuracySection";
import { useApp } from "../context/AppContext";
import { PageSkeleton } from "./Overview";

export default function Settings() {
  const { settings } = useApp();
  if (!settings) return <PageSkeleton />;
  return (
    <div>
      <PageHeader title="Settings" description="Choose which checks run, tune their thresholds, and control how things look." />
      <div className="space-y-6">
        <AppearanceSection />
        <RulesSection />
        <WindowsSection />
        <UpstreamSection />
        <DataSection />
        <AccuracySection />
      </div>
    </div>
  );
}
