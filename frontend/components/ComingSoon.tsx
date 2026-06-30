export default function ComingSoon({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-md">
        <div className="text-4xl mb-3">🚧</div>
        <h1 className="text-xl font-bold mb-2">{title}</h1>
        <p className="text-sm text-dim">{desc}</p>
        <div className="chip mt-4 inline-block">Fase berikutnya</div>
      </div>
    </div>
  );
}
