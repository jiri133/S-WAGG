import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import EvalPage from './pages/Eval'
import Main from './pages/Main'
import NotFound from './pages/NotFound'
import PlanPage from './pages/Plan'
import ReportPage from './pages/Report'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Main />} />
          <Route path="/plan" element={<PlanPage />} />
          <Route path="/raport" element={<ReportPage />} />
          <Route path="/evaluare" element={<EvalPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
