import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Navbar } from "../components/Navbar";
import { StatusBadge } from "../components/StatusBadge";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";

export default function CampaignDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [camp, setCamp] = useState(null);
  const [subs, setSubs] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [postUrl, setPostUrl] = useState("");
  const [accountId, setAccountId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [ending, setEnding] = useState(false);

  const load = async () => {
    const [c, s] = await Promise.all([
      api.get(`/campaigns/${id}`),
      api.get(`/campaigns/${id}/submissions`),
    ]);
    setCamp(c.data);
    setSubs(s.data);
    if (user) {
      const a = await api.get("/social/accounts");
      setAccounts(a.data.filter((x) => x.verified));
    }
  };

  useEffect(() => {
    load();
  }, [id, user]);

  if (!camp) {
    return (
      <div className="min-h-screen bg-white">
        <Navbar />
        <div className="max-w-4xl mx-auto px-6 py-20 font-mono">LOADING_</div>
      </div>
    );
  }

  const submit = async (e) => {
    e.preventDefault();
    if (!accountId) {
      toast.error("Pick a verified account first");
      return;
    }
    setSubmitting(true);
    try {
      await api.post(`/campaigns/${id}/submissions`, {
        post_url: postUrl,
        social_account_id: accountId,
      });
      toast.success("Submitted.");
      setPostUrl("");
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    } finally {
      setSubmitting(false);
    }
  };

  const refresh = async (subId) => {
    try {
      await api.post(`/submissions/${subId}/refresh`);
      toast.success("Refreshed.");
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  const endCampaign = async () => {
    if (!window.confirm("End this campaign? Submissions stop.")) return;
    setEnding(true);
    try {
      await api.post(`/campaigns/${id}/end`);
      toast.success("Campaign ended.");
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    } finally {
      setEnding(false);
    }
  };

  const progress = Math.min(100, (camp.total_views / camp.goal_views) * 100);
  const isOwner = user && camp.creator_user_id === user.id;

  return (
    <div data-testid="campaign-detail-page" className="min-h-screen bg-white">
      <Navbar />
      <div className="max-w-5xl mx-auto px-6 py-10">
        <Link to="/campaigns" className="font-mono text-xs uppercase brut-link" data-testid="back-to-campaigns">
          &larr; All campaigns
        </Link>
        <div className="mt-6 mb-10 flex flex-wrap items-start justify-between gap-4">
          <div>
            <StatusBadge status={camp.status} testId="campaign-status" />
            <h1 className="font-display text-4xl lg:text-5xl mt-3" data-testid="campaign-name">
              {camp.name}
            </h1>
            <p className="text-zinc-700 mt-2 max-w-2xl">{camp.description}</p>
            <div className="font-mono text-xs text-zinc-500 mt-2">ID: {camp.id}</div>
          </div>
          {isOwner && camp.status === "active" && (
            <button
              onClick={endCampaign}
              disabled={ending}
              className="brut-btn-secondary"
              style={{ color: "#EF4444", borderColor: "#EF4444" }}
              data-testid="end-campaign-btn"
            >
              {ending ? "..." : "END CAMPAIGN"}
            </button>
          )}
        </div>

        {/* Progress */}
        <div className="brut-card-static p-6 mb-10">
          <div className="grid grid-cols-3 gap-6 mb-4">
            <div>
              <div className="font-mono text-xs uppercase text-zinc-500">VIEWS</div>
              <div className="font-display text-3xl" data-testid="campaign-views">
                {camp.total_views.toLocaleString()}
              </div>
              <div className="font-mono text-xs text-zinc-500">
                of {camp.goal_views.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="font-mono text-xs uppercase text-zinc-500">PAYOUT</div>
              <div className="font-display text-3xl">
                ${(camp.payout_cents / 100).toFixed(2)}
              </div>
            </div>
            <div>
              <div className="font-mono text-xs uppercase text-zinc-500">SUBMISSIONS</div>
              <div className="font-display text-3xl">{camp.submission_count}</div>
            </div>
          </div>
          <div className="h-3 bg-zinc-200 border-2 border-black">
            <div className="h-full bg-[#002FA7]" style={{ width: `${progress}%` }} />
          </div>
        </div>

        {/* Submit */}
        {camp.status === "active" && user && (
          <section className="mb-10">
            <h2 className="font-display text-2xl mb-4">SUBMIT A POST</h2>
            {accounts.length === 0 ? (
              <div className="brut-card-static p-6 text-zinc-600">
                You need a <Link to="/dashboard" className="brut-link">verified social account</Link> first.
              </div>
            ) : (
              <form onSubmit={submit} className="brut-card-static p-6 grid md:grid-cols-12 gap-4 items-end">
                <div className="md:col-span-4">
                  <label className="font-mono text-xs uppercase block mb-2">Account</label>
                  <select
                    value={accountId}
                    onChange={(e) => setAccountId(e.target.value)}
                    className="brut-input"
                    data-testid="submission-account-select"
                  >
                    <option value="">Pick one...</option>
                    {accounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.platform} @{a.handle}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="md:col-span-5">
                  <label className="font-mono text-xs uppercase block mb-2">Post URL</label>
                  <input
                    type="url"
                    required
                    value={postUrl}
                    onChange={(e) => setPostUrl(e.target.value)}
                    placeholder="https://..."
                    className="brut-input"
                    data-testid="submission-url-input"
                  />
                </div>
                <div className="md:col-span-3">
                  <button
                    type="submit"
                    disabled={submitting}
                    className="brut-btn w-full justify-center"
                    data-testid="submission-submit-btn"
                  >
                    {submitting ? "..." : "SUBMIT"}
                  </button>
                </div>
              </form>
            )}
          </section>
        )}

        {/* Leaderboard */}
        <section>
          <h2 className="font-display text-2xl mb-4">LEADERBOARD</h2>
          {subs.length === 0 ? (
            <div className="brut-card-static p-8 text-center text-zinc-600">
              No submissions yet.
            </div>
          ) : (
            <div className="brut-card-static overflow-hidden">
              <table className="w-full text-left">
                <thead className="border-b-2 border-black bg-[#F4F4F5]">
                  <tr>
                    <th className="px-4 py-3 font-mono text-xs uppercase">#</th>
                    <th className="px-4 py-3 font-mono text-xs uppercase">Platform</th>
                    <th className="px-4 py-3 font-mono text-xs uppercase">Post</th>
                    <th className="px-4 py-3 font-mono text-xs uppercase text-right">Views</th>
                    <th className="px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {subs.map((s, i) => (
                    <tr
                      key={s.id}
                      className="border-b border-zinc-200 last:border-0"
                      data-testid={`submission-row-${s.id}`}
                    >
                      <td className="px-4 py-3 font-mono">{i + 1}</td>
                      <td className="px-4 py-3 font-mono text-xs uppercase">{s.platform}</td>
                      <td className="px-4 py-3 max-w-xs truncate">
                        <a
                          href={s.post_url}
                          target="_blank"
                          rel="noreferrer"
                          className="brut-link text-sm"
                        >
                          {s.post_url}
                        </a>
                      </td>
                      <td className="px-4 py-3 text-right font-display text-lg">
                        {s.current_views.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {user && s.user_id === user.id && (
                          <button
                            onClick={() => refresh(s.id)}
                            className="font-mono text-xs uppercase text-zinc-500 hover:text-black"
                            data-testid={`refresh-${s.id}`}
                          >
                            REFRESH
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
