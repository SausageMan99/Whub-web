'use client';

import { useFormStatus } from 'react-dom';
import { addComment } from '@/app/requests/[id]/actions';

function SubmitRevisionButton({ nextVersionNumber }: { nextVersionNumber: number }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-2xl bg-whub px-5 py-3 font-black text-white shadow-violet disabled:cursor-not-allowed disabled:opacity-50"
    >
      {pending ? 'Création en cours...' : `Créer V${nextVersionNumber}`}
    </button>
  );
}

export function RevisionComposer({
  requestId,
  nextVersionNumber,
  category = 'other',
}: {
  requestId: string;
  nextVersionNumber: number;
  category?: string;
}) {
  return (
    <form action={addComment} className="mt-5 space-y-3 border-t border-amber-200 pt-5">
      <input type="hidden" name="request_id" value={requestId} />
      <input type="hidden" name="category" value={category} />
      <label htmlFor="draft-feedback" className="block text-sm font-black text-ink">
        Correction post-génération — crée V{nextVersionNumber}
      </label>
      <textarea
        id="draft-feedback"
        name="body"
        rows={4}
        className="w-full resize-none rounded-2xl border border-amber-200 bg-white/80 px-4 py-3 text-sm font-semibold leading-6 placeholder:text-ink/28"
        placeholder={`Ex. V${nextVersionNumber} : aérer la page 2, garder toutes les expériences, réduire seulement le bloc compétences...`}
      />
      <SubmitRevisionButton nextVersionNumber={nextVersionNumber} />
    </form>
  );
}
