import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Navbar } from "../components/Navbar";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { toast } from "sonner";

export default function CreateCampaign() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    description: "",
    goal_views: 100000,
    payout_usd: 500,
  });
  const [submitting, setSubmitting] = useState(false);

  if (loading) return null;
  if (!user) return <Navigate to="/login" state={{ from: "/campaigns/new" }} replace />;

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const r = await api.post("/campaigns", form);
      toast.success("Campaign created.");
      navigate(`/campaigns/${r.data.id}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div data-testid="create-campaign-page" className="min-h-screen bg-white">
      <Navbar />
      <div className="max-w-2xl mx-auto px-6 py-10">
        <div className="font-mono text-xs uppercase text-zinc-500 mb-2">// new campaign</div>
        <h1 className="font-display text-4xl mb-8">CREATE CAMPAIGN</h1>
        <form onSubmit={submit} className="brut-card-static p-8 space-y-5">
          <div>
            <label className="font-mono text-xs uppercase block mb-2">Name</label>
            <input
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="brut-input"
              data-testid="campaign-name-input"
            />
          </div>
          <div>
            <label className="font-mono text-xs uppercase block mb-2">Description</label>
            <textarea
              rows="3"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="brut-input"
              data-testid="campaign-desc-input"
            />
          </div>
          <div className="grid grid-cols-2 gap-5">
            <div>
              <label className="font-mono text-xs uppercase block mb-2">Goal views</label>
              <input
                type="number"
                min="1"
                required
                value={form.goal_views}
                onChange={(e) => setForm({ ...form, goal_views: parseInt(e.target.value) || 0 })}
                className="brut-input"
                data-testid="campaign-goal-input"
              />
            </div>
            <div>
              <label className="font-mono text-xs uppercase block mb-2">Payout (USD)</label>
              <input
                type="number"
                min="0"
                step="0.01"
                required
                value={form.payout_usd}
                onChange={(e) => setForm({ ...form, payout_usd: parseFloat(e.target.value) || 0 })}
                className="brut-input"
                data-testid="campaign-payout-input"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="brut-btn w-full justify-center"
            data-testid="campaign-create-btn"
          >
            {submitting ? "..." : "LAUNCH CAMPAIGN"}
          </button>
        </form>
      </div>
    </div>
  );
}
