import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Login from './pages/Login'
import Totp from './pages/Totp'
import Callback from './pages/Callback'
import Logout from './pages/Logout'

export default function App() {
  return (
    <BrowserRouter basename="/__auth">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/totp" element={<Totp />} />
        <Route path="/callback" element={<Callback />} />
        <Route path="/logout" element={<Logout />} />
        <Route path="*" element={<Login />} />
      </Routes>
    </BrowserRouter>
  )
}
