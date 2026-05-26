import { login } from "./actions";

export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <h1 className="text-3xl font-bold">Connexion W hub CV Factory</h1>
      <p className="mt-3 text-sm text-black/60">Accès réservé aux emails whitelistés. MVP prévu pour 4-5 personnes W hub.</p>
      <form action={login} className="mt-8 space-y-4 rounded-2xl bg-white p-6 shadow-sm">
        <label className="block text-sm font-medium">Email W hub</label>
        <input name="email" type="email" required className="w-full rounded-lg border border-black/10 px-3 py-2" placeholder="prenom@whub.fr" />
        <button className="w-full rounded-lg bg-whub px-4 py-2 font-semibold text-white">Recevoir le lien magique</button>
      </form>
    </main>
  );
}
