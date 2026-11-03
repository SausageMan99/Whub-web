import { redirect } from "next/navigation";

// Ancienne adresse de la liste des demandes, gardée pour les liens existants.
export default function DashboardPage() {
  redirect("/demandes");
}
