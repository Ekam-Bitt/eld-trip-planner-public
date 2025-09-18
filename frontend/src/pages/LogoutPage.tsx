import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const API_BASE =
  import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function LogoutPage() {
  const navigate = useNavigate();
  const [message, setMessage] = useState("Logging out...");
  useEffect(() => {
    (async () => {
      const refresh = localStorage.getItem("refresh");
      if (refresh) {
        try {
          await fetch(`${API_BASE}/api/drivers/logout/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh }),
          });
        } catch {
          // ignore logout failures
        }
      }
      localStorage.removeItem("access");
      localStorage.removeItem("refresh");
      setMessage("Logged out");
      window.dispatchEvent(new Event("auth:changed"));
      setTimeout(() => navigate("/login"), 300);
    })();
  }, [navigate]);
  return (
    <div className="flex-1 flex items-center justify-center w-full py-8">
      <div className="max-w-md w-full bg-gray-800 p-8 rounded-xl shadow-lg text-center">
        {message}
      </div>
    </div>
  );
}
