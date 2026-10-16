"use client";

import { useRouter } from "next/navigation";
import { useToast } from "@/components/ui/toast";
import { useLogout } from "@/lib/auth";

/** Sai da conta e volta para o login. */
export function useSignOut() {
  const router = useRouter();
  const toast = useToast();
  const logout = useLogout();
  return {
    pending: logout.isPending,
    signOut: () =>
      logout.mutate(undefined, {
        onSettled: () => {
          router.replace("/login");
          toast({ title: "Você saiu da conta" });
        },
      }),
  };
}
