export default function Loading() {
  return (
    <div className="space-y-6 animate-pulse" aria-busy="true">
      <div className="h-8 w-72 rounded-md bg-slate-200" />
      <div className="h-4 w-96 rounded-md bg-slate-200" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="h-36 rounded-xl bg-slate-200/80" />
        <div className="h-36 rounded-xl bg-slate-200/80" />
        <div className="h-36 rounded-xl bg-slate-200/80" />
      </div>
    </div>
  );
}

