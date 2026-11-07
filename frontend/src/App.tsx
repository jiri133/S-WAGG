import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import FarmConfig from './pages/FarmConfig'
import Home from './pages/Home'
import NotFound from './pages/NotFound'
import Simulation from './pages/Simulation'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/farm-config" element={<FarmConfig />} />
          <Route path="/simulation" element={<Simulation />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
