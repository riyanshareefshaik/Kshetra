export default function Placeholder({ title, feature }) {
  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="mt-2 text-stone-600">{feature} — not built yet.</p>
    </div>
  );
}
