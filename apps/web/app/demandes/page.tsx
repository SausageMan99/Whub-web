import type { Metadata } from "next";

export const metadata: Metadata = { title: "Demandes" };

export default function DemandesPage() {
  return (
    <div className="welcome-empty">
      <h1>Choisis une demande</h1>
      <p>Les CV à relire sont en haut de la liste. Pour en lancer un nouveau, glisse le PDF n’importe où dans la fenêtre ou utilise « Nouveau CV ».</p>
    </div>
  );
}
