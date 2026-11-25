import { redirect } from "next/navigation";

// A entrada do sistema é o Assistente; sem login, o AppShell manda para o login.
export default async function Home({ params }: PageProps<"/[lang]">) {
  redirect(`/${(await params).lang}/assistente`);
}
