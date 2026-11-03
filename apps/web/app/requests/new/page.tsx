import { redirect } from "next/navigation";

type NewRequestPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

// La création se fait désormais dans la fenêtre « Nouveau CV » de l'écran Demandes.
export default async function NewRequestPage({ searchParams }: NewRequestPageProps) {
  const params = await searchParams;
  const error = Array.isArray(params?.error) ? params?.error[0] : params?.error;
  redirect(error ? `/demandes?nouveau=1&error=${encodeURIComponent(error)}` : "/demandes?nouveau=1");
}
