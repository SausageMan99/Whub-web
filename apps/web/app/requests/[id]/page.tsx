import { redirect } from "next/navigation";

// Ancienne adresse d'une demande, gardée pour les liens existants.
export default async function RequestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/demandes/${id}`);
}
