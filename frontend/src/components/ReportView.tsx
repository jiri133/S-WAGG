import { urls } from '../api/api'

// The HTML report rendered by FastAPI (§8), shown in an iframe.
export default function ReportView({ missionId }: { missionId: string }) {
  return (
    <section className="space-y-3">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-xl font-bold tracking-tight">Raport de inspecție {missionId}</h1>
        <a
          href={urls.report(missionId)}
          target="_blank"
          rel="noreferrer"
          className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm hover:bg-neutral-100"
        >
          Deschide în tab nou ↗
        </a>
      </header>
      <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-sm">
        <iframe
          data-testid="report-frame"
          title={`Raport ${missionId}`}
          src={urls.report(missionId)}
          className="h-[78vh] w-full bg-white"
        />
      </div>
    </section>
  )
}
