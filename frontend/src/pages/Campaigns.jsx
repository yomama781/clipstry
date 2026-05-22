import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Navbar } from "../components/Navbar";
import { StatusBadge } from "../components/StatusBadge";
import { api } from "../lib/api";

export default function Campaigns() {
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    const q = filter === "all" ? "" : `?status=${filter}`;
    api.get(`/campaigns${q}`).then((r) => setItems(r.data));
  }, [filter]);

  return (
    <div data-testid="campaigns-page" className="min-h-screen bg-white">
      <Navbar />
      <div className="max-w-7xl mx-auto px-6 py-10">
        <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="font-mono text-xs uppercase text-zinc-500 mb-2">// campaigns</div>
            <h1 className="font-display text-4xl lg:text-5xl">ALL CAMPAIGNS</h1>
          </div>
          <div className="flex gap-2">
            {["all", "active", "ended"].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`font-mono text-xs uppercase tracking-wider px-3 py-2 border-2 border-black ${
                  filter === f ? "bg-black text-white" : "bg-white"
                }`}
                data-testid={`filter-${f}`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        {items.length === 0 ? (
          <div className="brut-card-static p-12 text-center text-zinc-600">
            No campaigns to show.
          </div>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {items.map((c) => (
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
                <div className="mt-3 h-2 bg-zinc-200 border border-black">
                  <div
                    className="h-full bg-[#002FA7]"
                    style={{
                      width: `${Math.min(100, (c.total_views / c.goal_views) * 100)}%`,
                    }}
                  />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
