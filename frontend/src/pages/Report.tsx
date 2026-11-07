import ReportView from '../components/ReportView'
import { useMissionStore } from '../store/missionStore'

// Report tab: FastAPI renders the HTML, React only puts it in an iframe (§8, §10).
export default function ReportPage() {
  const missionId = useMissionStore((s) => s.mission?.id) ?? 'M-0001'
  return <ReportView missionId={missionId} />
}
