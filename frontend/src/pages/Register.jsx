import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Navbar } from "../components/Navbar";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (password.length < 6) {
      toast.error("Password must be at least 6 characters");
      return;
    }
    setLoading(true);
    try {
      await register(email, password);
      toast.success("Account created.");
      navigate("/dashboard");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="register-page" className="min-h-screen bg-white">
      <Navbar />
      <div className="max-w-md mx-auto px-6 py-16">
        <div className="font-mono text-xs uppercase text-zinc-500 mb-3">// new account</div>
        <h1 className="font-display text-4xl mb-8">SIGN UP</h1>
        <form onSubmit={submit} className="brut-card-static p-8 space-y-5">
          <div>
            <label className="font-mono text-xs uppercase tracking-wider block mb-2">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="brut-input"
              data-testid="register-email-input"
            />
          </div>
          <div>
            <label className="font-mono text-xs uppercase tracking-wider block mb-2">
              Password &nbsp;<span className="text-zinc-500">(6+ chars)</span>
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="brut-input"
              data-testid="register-password-input"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="brut-btn w-full justify-center"
            data-testid="register-submit-btn"
          >
            {loading ? "..." : "CREATE ACCOUNT"}
          </button>
          <p className="text-sm text-zinc-600 text-center">
            Already have one?{" "}
            <Link to="/login" className="brut-link" data-testid="register-go-login">
              Log in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
