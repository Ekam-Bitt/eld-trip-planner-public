import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import { useEffect, useState, type ReactElement } from "react";
import { ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import LogoutPage from "./pages/LogoutPage";
import ProfileSettings from "./pages/ProfileSettings";
import TripPlannerPage from "./pages/TripPlannerPage";
import TripHistoryPage from "./pages/TripHistoryPage";
import TripDetailPage from "./pages/TripDetailPage";
import MapKeyModal from "./components/MapKeyModal";
import { DriversAPI } from "./api";
import DashboardPage from "./pages/DashboardPage";

function useAuth() {
  const [token, setToken] = useState<string | null>(null);
  useEffect(() => {
    const update = () => setToken(localStorage.getItem("access"));
    update();
    window.addEventListener("auth:changed", update);
    return () => window.removeEventListener("auth:changed", update);
  }, []);
  return token;
}

function Home(): ReactElement {
  const token = useAuth();
  const [askKey, setAskKey] = useState(false);
  useEffect(() => {
    (async () => {
      if (!token) return;
      try {
        const me = await DriversAPI.me();
        if (!me.has_mapbox_key) setAskKey(true);
      } catch {
        // ignore profile fetch errors on home load
      }
    })();
  }, [token]);
  return (
    <div className="py-6">
      <h1 className="text-3xl font-extrabold mb-6 text-blue-500">ELD Trip Planner</h1>
      {token ? (
        <div className="grid gap-4">
          <div className="text-text-muted">Welcome. Use Trip Planner to create a route.</div>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <Link
              className="rounded-2xl shadow-lg bg-slate-800 p-6 hover:shadow-xl transition"
              to="/planner"
            >
              <div className="text-lg font-semibold">Trip Planner</div>
              <div className="text-sm text-text-muted">Plan a new route and see guidance</div>
            </Link>
            <Link
              className="rounded-2xl shadow-lg bg-slate-800 p-6 hover:shadow-xl transition"
              to="/trips"
            >
              <div className="text-lg font-semibold">Trip History</div>
              <div className="text-sm text-text-muted">Review your previous trips</div>
            </Link>
            <Link
              className="rounded-2xl shadow-lg bg-slate-800 p-6 hover:shadow-xl transition"
              to="/settings"
            >
              <div className="text-lg font-semibold">Profile Settings</div>
              <div className="text-sm text-text-muted">Manage your driver profile</div>
            </Link>
            <Link
              className="rounded-2xl shadow-lg bg-slate-800 p-6 hover:shadow-xl transition"
              to="/dashboard"
            >
              <div className="text-lg font-semibold">Dashboard</div>
              <div className="text-sm text-text-muted">HOS overview and recent trips</div>
            </Link>
          </div>
        </div>
      ) : (
        <div className="max-w-md mx-auto rounded-2xl shadow-lg bg-slate-800 p-8">
          <h2 className="text-2xl font-bold mb-4">Welcome</h2>
          <p className="text-text-muted mb-6">Please login or signup to plan trips.</p>
          <div className="flex gap-3">
            <Link
              className="px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold shadow"
              to="/login"
            >
              Login
            </Link>
            <Link
              className="px-5 py-2.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-gray-100"
              to="/signup"
            >
              Signup
            </Link>
          </div>
        </div>
      )}
      <MapKeyModal open={askKey} onClose={() => setAskKey(false)} />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col bg-slate-900 text-gray-100 font-sans">
        <NavBar />
        <main className="flex-1 container mx-auto px-4 py-6 w-full">
          <div className="w-full max-w-7xl mx-auto">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/signup" element={<SignupPage />} />
              <Route path="/logout" element={<LogoutPage />} />
              <Route path="/settings" element={<ProfileSettings />} />
              <Route path="/planner" element={<TripPlannerPage />} />
              <Route path="/trips" element={<TripHistoryPage />} />
              <Route path="/trips/:id" element={<TripDetailPage />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </div>
        </main>
        <ToastContainer position="bottom-right" autoClose={3000} hideProgressBar newestOnTop closeOnClick pauseOnHover theme="dark" />
        <footer className="py-4 text-center text-sm text-gray-500 bg-slate-800 border-t border-slate-700">
          © {new Date().getFullYear()} ELD Trip Planner
        </footer>
      </div>
    </BrowserRouter>
  );
}

function NavBar() {
  const token = useAuth();
  return (
    <nav className="sticky top-0 z-50 flex justify-between items-center px-6 py-4 bg-slate-800 shadow-md border-b border-slate-700">
      <div className="flex items-center gap-4">
        <Link className="text-xl font-bold text-blue-500" to="/">
          ELD Trip Planner
        </Link>
      </div>
      <div className="flex items-center gap-2">
        {token ? (
          <>
            <Link className="px-3 py-1.5 rounded-lg hover:bg-slate-700" to="/dashboard">
              Dashboard
            </Link>
            <Link className="px-3 py-1.5 rounded-lg hover:bg-slate-700" to="/planner">
              Planner
            </Link>
            <Link className="px-3 py-1.5 rounded-lg hover:bg-slate-700" to="/trips">
              Trips
            </Link>
            <Link className="px-3 py-1.5 rounded-lg hover:bg-slate-700" to="/settings">
              Profile
            </Link>
            <Link className="px-3 py-1.5 rounded-lg hover:bg-slate-700" to="/logout">
              Logout
            </Link>
          </>
        ) : (
          <>
            <Link className="px-3 py-1.5 rounded-lg hover:bg-slate-700" to="/login">
              Login
            </Link>
            <Link className="px-3 py-1.5 rounded-lg hover:bg-slate-700" to="/signup">
              Signup
            </Link>
          </>
        )}
      </div>
    </nav>
  );
}
