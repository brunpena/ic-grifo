import { redirect } from "next/navigation";

// A entrada do sistema é o Assistente; sem login, o AppShell manda para /login.
export default function Home() {
  redirect("/assistente");
}
