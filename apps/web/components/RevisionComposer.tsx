'use client';

import { useFormStatus } from 'react-dom';
import { addComment } from '@/app/requests/[id]/actions';

function SubmitRevisionButton({ nextVersionNumber }: { nextVersionNumber: number }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded-2xl bg-whub px-5 py-3 text-sm font-black text-white shadow-violet disabled:cursor-not-allowed disabled:opacity-50"
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
    <form action={addComment} className="mt-5 space-y-3 border-t border-ink/8 pt-5">
      <input type="hidden" name="request_id" value={requestId} />
      <input type="hidden" name="category" value={category} />
      <label htmlFor="draft-feedback" className="block text-sm font-semibold text-ink">
        Demander une correction
      </label>
      <textarea
        id="draft-feedback"
        name="body"
        rows={4}
        className="w-full resize-none rounded-2xl border border-ink/10 bg-white px-4 py-3 text-sm font-medium leading-6 placeholder:text-ink/28"
        placeholder={`Ex : change le titre en “Ingénieur QA”, garde le reste identique pour V${nextVersionNumber}.`}
      />
      <SubmitRevisionButton nextVersionNumber={nextVersionNumber} />
    </form>
  );
}
