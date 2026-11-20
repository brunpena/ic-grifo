"use client";

import { useRouter } from "next/navigation";
import { useToast } from "@/components/ui/toast";
import { useLogout } from "@/lib/auth";
import { useT } from "@/lib/i18n";

/** Sai da conta e volta para o login. */
export function useSignOut() {
  const router = useRouter();
  const toast = useToast();
  const logout = useLogout();
  const t = useT();
  return {
    pending: logout.isPending,
    signOut: () =>
      logout.mutate(undefined, {
        onSettled: () => {
          router.replace("/login");
          toast({ title: t("Você saiu da conta") });
        },
      }),
  };
}
