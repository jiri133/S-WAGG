import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import EvalPage from './pages/Eval'
import FarmConfig from './pages/FarmConfig'
import Main from './pages/Main'
import NotFound from './pages/NotFound'
import PlanPage from './pages/Plan'
import ReportPage from './pages/Report'
import Simulation from './pages/Simulation'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Main />} />
          <Route path="/plan" element={<PlanPage />} />
          <Route path="/raport" element={<ReportPage />} />
          <Route path="/evaluare" element={<EvalPage />} />
          <Route path="/parc-config" element={<FarmConfig />} />
          <Route path="/farm-config" element={<Navigate to="/parc-config" replace />} />
          <Route path="/simulation" element={<Simulation />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
