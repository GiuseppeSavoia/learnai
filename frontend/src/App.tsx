import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import PuzzlePage from './pages/PuzzlePage'
import PlayPage from './pages/PlayPage'
import AnalysisList from './pages/AnalysisList'
import AnalysisReview from './pages/AnalysisReview'
import Settings from './pages/Settings'
import Home from './pages/Home'
import StudyPage from './pages/StudyPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="scacchi" element={<Dashboard />} />
          <Route path="studio/:exam" element={<StudyPage />} />
          <Route path="tattica" element={<PuzzlePage />} />
          <Route path="gioca" element={<PlayPage />} />
          <Route path="gioca/:id" element={<PlayPage />} />
          <Route path="analisi" element={<AnalysisList />} />
          <Route path="analisi/:id" element={<AnalysisReview />} />
          <Route path="impostazioni" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
