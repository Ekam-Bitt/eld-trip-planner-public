import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

const API_BASE =
  import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function SignupPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [licenseNo, setLicenseNo] = useState("");
  const [truckType, setTruckType] = useState("");
  const [avgMpg, setAvgMpg] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/drivers/signup/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          email,
          password,
          license_no: licenseNo,
          truck_type: truckType,
          avg_mpg: avgMpg ? Number(avgMpg) : null,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Signup failed");
      }
      navigate("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center w-full py-8">
      <div className="max-w-md w-full bg-gray-800 p-8 rounded-xl shadow-lg">
        <h3 className="text-xl font-semibold mb-6">Signup</h3>
        <form onSubmit={onSubmit} className="grid gap-3">
          <input
            className="px-3 py-2 rounded-lg bg-gray-900 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Name"
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="px-3 py-2 rounded-lg bg-gray-900 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="px-3 py-2 rounded-lg bg-gray-900 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <input
            className="px-3 py-2 rounded-lg bg-gray-900 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="License No"
            autoComplete="off"
            value={licenseNo}
            onChange={(e) => setLicenseNo(e.target.value)}
          />
          <input
            className="px-3 py-2 rounded-lg bg-gray-900 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Truck Type"
            autoComplete="off"
            value={truckType}
            onChange={(e) => setTruckType(e.target.value)}
          />
          <input
            className="px-3 py-2 rounded-lg bg-gray-900 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Avg MPG"
            inputMode="decimal"
            autoComplete="off"
            value={avgMpg}
            onChange={(e) => setAvgMpg(e.target.value)}
          />
          <button
            type="submit"
            className="mt-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white"
          >
            Create account
          </button>
          {error && <div className="text-red-400 text-sm">{error}</div>}
        </form>
      </div>
    </div>
  );
}
