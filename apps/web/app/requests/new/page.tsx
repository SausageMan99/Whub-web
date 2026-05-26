import { createRequest } from "./actions";

export default function NewRequestPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-3xl font-bold">Nouveau CV W hub</h1>
      <form action={createRequest} className="mt-8 space-y-5 rounded-2xl bg-white p-6 shadow-sm">
        <input name="title" className="w-full rounded-lg border border-black/10 px-3 py-2" placeholder="Titre interne ex: CV Architecte Cloud" />
        <input name="candidate_first_name" className="w-full rounded-lg border border-black/10 px-3 py-2" placeholder="Prénom à afficher" />
        <input name="file" type="file" accept="application/pdf" required className="w-full rounded-lg border border-black/10 px-3 py-2" />
        <textarea name="instructions" rows={6} className="w-full rounded-lg border border-black/10 px-3 py-2" placeholder="Consignes: titre souhaité, points à mettre en avant, éléments à retirer..." />
        <select name="priority" className="w-full rounded-lg border border-black/10 px-3 py-2"><option value="normal">Normal</option><option value="high">Prioritaire</option><option value="urgent">Urgent</option></select>
        <button className="rounded-lg bg-whub px-5 py-3 font-semibold text-white">Créer la demande</button>
      </form>
    </main>
  );
}
