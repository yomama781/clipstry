import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Navbar } from "../components/Navbar";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      toast.success("Welcome back.");
      const redirect = location.state?.from || "/dashboard";
      navigate(redirect);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="login-page" className="min-h-screen bg-white">
      <Navbar />
      <div className="max-w-md mx-auto px-6 py-16">
        <div className="font-mono text-xs uppercase text-zinc-500 mb-3">// access</div>
        <h1 className="font-display text-4xl mb-8">LOG IN</h1>
        <form onSubmit={submit} className="brut-card-static p-8 space-y-5">
          <div>
            <label className="font-mono text-xs uppercase tracking-wider block mb-2">
              Email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="brut-input"
              data-testid="login-email-input"
            />
          </div>
          <div>
            <label className="font-mono text-xs uppercase tracking-wider block mb-2">
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="brut-input"
              data-testid="login-password-input"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="brut-btn w-full justify-center"
            data-testid="login-submit-btn"
          >
            {loading ? "..." : "LOG IN"}
          </button>
          <p className="text-sm text-zinc-600 text-center">
            No account?{" "}
            <Link to="/register" className="brut-link" data-testid="login-go-register">
              Sign up
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
