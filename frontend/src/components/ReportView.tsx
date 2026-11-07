import { urls } from '../api/api'

// The HTML report rendered by FastAPI (§8), shown in an iframe.
export default function ReportView({ missionId }: { missionId: string }) {
  return (
    <section className="space-y-2">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-bold tracking-tight">Raport de inspecție {missionId}</h1>
        <a href={urls.report(missionId)} target="_blank" rel="noreferrer" className="text-sm text-blue-700 underline">
          Deschide în tab nou
        </a>
      </header>
      <iframe
        data-testid="report-frame"
        title={`Raport ${missionId}`}
        src={urls.report(missionId)}
        className="h-[75vh] w-full rounded border border-neutral-200 bg-white"
      />
    </section>
  )
}
