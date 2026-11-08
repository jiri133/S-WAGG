import { urls, type FrameMeta } from '../api/api'

// Captured thermal frames, newest first. A red border marks a frame the data check rejected.
export default function FrameStrip({ frames }: { frames: FrameMeta[] }) {
  if (!frames.length) return <p className="text-sm text-ink-soft">Niciun cadru încă.</p>
  return (
    <div className="space-y-2">
      <p className="text-sm text-ink-soft">Cadre termice ({frames.length}), cele mai noi primele:</p>
      <div className="flex gap-1.5 overflow-x-auto pb-2" data-testid="frame-strip">
        {[...frames].reverse().map((f) => (
          <img
            key={f.id}
            src={urls.frameThumb(f.id)}
            alt={f.id}
            loading="lazy"
            data-testid={`frame-${f.id}`}
            title={`${f.id} · ${f.irradiance_wm2} W/m²${f.check_ok ? '' : ' · ' + f.problems.join(', ')}`}
            className={`h-14 shrink-0 rounded-md border-2 ${f.check_ok ? 'border-line' : 'border-negative'}`}
          />
        ))}
      </div>
    </div>
  )
}
