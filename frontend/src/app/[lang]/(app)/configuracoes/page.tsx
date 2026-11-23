import { msg } from "@/lib/i18n/core";
import { localizedMetadata } from "@/lib/i18n/metadata";
import { SettingsView } from "@/components/settings/settings-view";

export const generateMetadata = () => localizedMetadata(msg("Configurações"));

export default function Page() {
  return <SettingsView />;
}
