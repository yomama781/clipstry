import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Navbar } from "../components/Navbar";
import { StatusBadge } from "../components/StatusBadge";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { toast } from "sonner";

const PLATFORMS = ["instagram", "tiktok", "twitter", "youtube"];

export default function Dashboard() {
  const { user, loading: authLoading } = useAuth();
  const [accounts, setAccounts] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [platform, setPlatform] = useState("instagram");
  const [handle, setHandle] = useState("");
  const [verifying, setVerifying] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [copiedId, setCopiedId] = useState(null);

  const loadAll = async () => {
    const [a, c] = await Promise.all([
      api.get("/social/accounts"),
      api.get("/campaigns"),
    ]);
    setAccounts(a.data);
    setCampaigns(c.data);
  };

  useEffect(() => {
    if (user) loadAll();
  }, [user]);

  if (authLoading) return null;
  if (!user) return <Navigate to="/login" replace />;

  const startVerify = async (e) => {
    e.preventDefault();
    if (!handle.trim()) return;
    setSubmitting(true);
    try {
      await api.post("/social/start-verification", { platform, handle });
      toast.success("Code generated. Paste it in your bio.");
      setHandle("");
      await loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to start");
    } finally {
      setSubmitting(false);
    }
  };

  const verifyNow = async (id) => {
    setVerifying(id);
    try {
      await api.post(`/social/verify/${id}`);
      toast.success("VERIFIED.");
      await loadAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Code not found in bio yet");
    } finally {
      setVerifying(null);
    }
  };

  const removeAccount = async (id) => {
    if (!window.confirm("Remove this social account?")) return;
    await api.delete(`/social/accounts/${id}`);
    await loadAll();
  };

  const copyCode = (id, code) => {
    navigator.clipboard.writeText(code);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  return (
    <div data-testid="dashboard-page" className="min-h-screen bg-white">
      <Navbar />
      <div className="max-w-7xl mx-auto px-6 py-10">
        <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="font-mono text-xs uppercase text-zinc-500 mb-2">
              // dashboard / {user.email}
            </div>
            <h1 className="font-display text-4xl lg:text-5xl">CONTROL PANEL</h1>
          </div>
          <Link to="/campaigns/new" className="brut-btn" data-testid="dashboard-new-campaign">
            + NEW CAMPAIGN
          </Link>
        </div>

        {/* Add Social Account */}
        <section className="mb-12">
          <h2 className="font-display text-2xl mb-4">VERIFY A SOCIAL ACCOUNT</h2>
          <form
            onSubmit={startVerify}
            className="brut-card-static p-6 grid md:grid-cols-12 gap-4 items-end"
          >
            <div className="md:col-span-3">
              <label className="font-mono text-xs uppercase block mb-2">Platform</label>
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                className="brut-input"
                data-testid="verify-platform-select"
              >
                {PLATFORMS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-6">
              <label className="font-mono text-xs uppercase block mb-2">Handle / URL</label>
              <input
                value={handle}
                onChange={(e) => setHandle(e.target.value)}
                placeholder="@yourhandle"
                className="brut-input"
                data-testid="verify-handle-input"
              />
            </div>
            <div className="md:col-span-3">
              <button
                type="submit"
                disabled={submitting}
                className="brut-btn w-full justify-center"
                data-testid="verify-generate-code-btn"
              >
                {submitting ? "..." : "GENERATE CODE"}
              </button>
            </div>
          </form>
        </section>

        {/* Accounts list */}
        <section className="mb-12">
          <h2 className="font-display text-2xl mb-4">
            YOUR ACCOUNTS&nbsp;
            <span className="font-mono text-sm text-zinc-500">({accounts.length})</span>
          </h2>
          {accounts.length === 0 ? (
            <div className="brut-card-static p-8 text-center text-zinc-600">
              No accounts yet. Generate a verification code above.
            </div>
          ) : (
            <div className="grid md:grid-cols-2 gap-6">
              {accounts.map((a) => (
                <div
                  key={a.id}
                  className="brut-card-static p-6"
                  data-testid={`account-card-${a.id}`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="font-mono text-xs uppercase text-zinc-500">
                        {a.platform}
                      </div>
                      <a
                        href={a.profile_url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-display text-xl brut-link"
                      >
                        @{a.handle}
                      </a>
                    </div>
                    <StatusBadge
                      status={a.verified ? "verified" : "pending"}
                      testId={`account-status-${a.id}`}
                    />
                  </div>
                  {!a.verified && (
                    <>
                      <div className="font-mono text-xs uppercase text-zinc-500 mb-2">
                        Paste this in your bio:
                      </div>
                      <div
                        className="code-block flex items-center justify-between cursor-pointer mb-4"
                        onClick={() => copyCode(a.id, a.verification_code)}
                        data-testid={`account-code-${a.id}`}
                      >
                        <span>{a.verification_code}</span>
                        <span className="text-xs text-zinc-500 ml-2">
                          {copiedId === a.id ? "COPIED" : "CLICK TO COPY"}
                        </span>
                      </div>
                      <div className="flex gap-3">
                        <button
                          onClick={() => verifyNow(a.id)}
                          disabled={verifying === a.id}
                          className="brut-btn flex-1 justify-center"
                          data-testid={`account-verify-btn-${a.id}`}
                        >
                          {verifying === a.id ? "CHECKING..." : "I'VE ADDED IT — VERIFY"}
                        </button>
                        <button
                          onClick={() => removeAccount(a.id)}
                          className="brut-btn-secondary"
                          data-testid={`account-remove-btn-${a.id}`}
                        >
                          REMOVE
                        </button>
                      </div>
                    </>
                  )}
                  {a.verified && (
                    <div className="flex justify-end">
                      <button
                        onClick={() => removeAccount(a.id)}
                        className="font-mono text-xs uppercase text-zinc-500 hover:text-red-600"
                        data-testid={`account-remove-btn-${a.id}`}
                      >
                        Remove
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Campaigns */}
        <section>
          <h2 className="font-display text-2xl mb-4">
            CAMPAIGNS&nbsp;
            <span className="font-mono text-sm text-zinc-500">({campaigns.length})</span>
          </h2>
          {campaigns.length === 0 ? (
            <div className="brut-card-static p-8 text-center text-zinc-600">
              No campaigns yet.{" "}
              <Link to="/campaigns/new" className="brut-link">
                Create one
              </Link>
              .
            </div>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
              {campaigns.map((c) => (
                <Link
                  key={c.id}
                  to={`/campaigns/${c.id}`}
                  className="brut-card p-6 block"
                  data-testid={`campaign-card-${c.id}`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <h3 className="font-display text-xl">{c.name}</h3>
                    <StatusBadge status={c.status} />
                  </div>
                  <p className="text-sm text-zinc-600 mb-4 line-clamp-2">
                    {c.description || "—"}
                  </p>
                  <div className="grid grid-cols-2 gap-2 font-mono text-xs">
                    <div>
                      <div className="text-zinc-500">VIEWS</div>
                      <div className="text-lg text-black">
                        {c.total_views.toLocaleString()}/{c.goal_views.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-zinc-500">PAYOUT</div>
                      <div className="text-lg text-black">
                        ${(c.payout_cents / 100).toFixed(2)}
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
