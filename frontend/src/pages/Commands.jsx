import { useEffect, useState } from "react";
import { Navbar } from "../components/Navbar";
import { api } from "../lib/api";

const COMMANDS = [
  {
    cmd: "/verify",
    args: "platform:<instagram|tiktok|twitter|youtube> handle:<@handle>",
    desc: "Bot generates a unique code (e.g. VRFY-9F2A41). Paste it anywhere in your bio.",
  },
  {
    cmd: "/verify-check",
    args: "platform:<...> handle:<@handle>",
    desc: "Bot fetches your public bio and checks that the code is present. If yes → VERIFIED.",
  },
  {
    cmd: "/create-campaign",
    args: "name:<text> goal_views:<int> payout:<usd> description:<text>",
    desc: "Spin up a new campaign for your server. Anyone can submit posts.",
  },
  {
    cmd: "/end-campaign",
    args: "campaign_id:<id>",
    desc: "Close the campaign. Only the creator can run this.",
  },
  {
    cmd: "/submit",
    args: "campaign_id:<id> post_url:<url>",
    desc: "Submit a post to a campaign. You must own a verified account for that platform.",
  },
  {
    cmd: "/campaigns",
    args: "",
    desc: "List active campaigns in the server.",
  },
  {
    cmd: "/accounts",
    args: "",
    desc: "Show your verified social accounts (only visible to you).",
  },
];

export default function Commands() {
  const [bot, setBot] = useState(null);

  useEffect(() => {
    api.get("/bot/status").then((r) => setBot(r.data)).catch(() => setBot({ running: false }));
  }, []);

  return (
    <div data-testid="commands-page" className="min-h-screen bg-white">
      <Navbar />
      <div className="max-w-5xl mx-auto px-6 py-10">
        <div className="font-mono text-xs uppercase text-zinc-500 mb-2">// reference</div>
        <h1 className="font-display text-4xl lg:text-5xl mb-2">SLASH COMMANDS</h1>
        <p className="text-zinc-700 mb-6 max-w-2xl">
          All commands run inside Discord. Invite the bot, then type{" "}
          <span className="font-mono">/</span> to get autocomplete.
        </p>
        <div className="brut-card-static p-4 mb-10 flex items-center justify-between">
          <div className="font-mono text-sm">
            BOT STATUS:&nbsp;
            <span
              className={bot?.running ? "text-[#10B981]" : "text-[#EF4444]"}
              data-testid="bot-status"
            >
              {bot ? (bot.running ? `ONLINE (${bot.user})` : "OFFLINE") : "..."}
            </span>
          </div>
        </div>

        <div className="space-y-4">
          {COMMANDS.map((c) => (
            <div key={c.cmd} className="brut-card-static p-5">
              <div className="flex flex-wrap items-baseline gap-3 mb-2">
                <code className="font-mono text-base bg-[#09090B] text-white px-2 py-1">
                  {c.cmd}
                </code>
                <code className="font-mono text-xs text-zinc-500">{c.args}</code>
              </div>
              <p className="text-sm text-zinc-700">{c.desc}</p>
            </div>
          ))}
        </div>

        <div className="mt-12 brut-card-static p-6 bg-[#F4F4F5]">
          <h3 className="font-display text-xl mb-3">VERIFICATION FLOW</h3>
          <ol className="space-y-3 text-sm text-zinc-700">
            <li>
              <span className="font-mono text-xs bg-black text-white px-1.5 py-0.5 mr-2">1</span>
              Run <code className="font-mono">/verify platform:tiktok handle:@me</code>
            </li>
            <li>
              <span className="font-mono text-xs bg-black text-white px-1.5 py-0.5 mr-2">2</span>
              Bot DMs you a code like <code className="font-mono">VRFY-9F2A41</code>
            </li>
            <li>
              <span className="font-mono text-xs bg-black text-white px-1.5 py-0.5 mr-2">3</span>
              Paste the code anywhere in your TikTok bio (you can remove it after verification)
            </li>
            <li>
              <span className="font-mono text-xs bg-black text-white px-1.5 py-0.5 mr-2">4</span>
              Run <code className="font-mono">/verify-check platform:tiktok handle:@me</code>
            </li>
            <li>
              <span className="font-mono text-xs bg-black text-white px-1.5 py-0.5 mr-2">5</span>
              Bot scrapes your public bio &mdash; if the code is there, you&rsquo;re VERIFIED.
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
}
