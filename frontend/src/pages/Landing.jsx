import { Link } from "react-router-dom";
import { Navbar } from "../components/Navbar";

const Feature = ({ num, title, body }) => (
  <div className="brut-card-static p-8 relative">
    <div className="font-mono text-xs text-zinc-500 mb-4">[ {num} ]</div>
    <h3 className="font-display text-2xl mb-3">{title}</h3>
    <p className="text-zinc-700 leading-relaxed">{body}</p>
  </div>
);

const Cmd = ({ cmd, desc }) => (
  <div className="flex items-start gap-4 py-3 border-b border-zinc-200 last:border-0">
    <code className="font-mono text-sm bg-[#09090B] text-white px-2 py-1 whitespace-nowrap">
      {cmd}
    </code>
    <span className="text-sm text-zinc-700 pt-1">{desc}</span>
  </div>
);

export default function Landing() {
  return (
    <div data-testid="landing-page" className="min-h-screen bg-white">
      <Navbar />
      {/* HERO */}
      <section className="relative overflow-hidden border-b-2 border-black">
        <div className="absolute inset-0 brut-grid-bg pointer-events-none" />
        <div className="max-w-7xl mx-auto px-6 py-20 lg:py-28 grid lg:grid-cols-12 gap-10 items-center relative">
          <div className="lg:col-span-7">
            <div className="inline-flex items-center gap-2 border-2 border-black px-3 py-1 font-mono text-xs uppercase mb-8">
              <span className="w-2 h-2 bg-[#10B981] inline-block" />
              Discord Bot • Online
            </div>
            <h1
              className="font-display text-5xl sm:text-6xl lg:text-7xl leading-[0.95] mb-6"
              data-testid="hero-title"
            >
              TRACK VIEWS.
              <br />
              <span className="text-[#002FA7]">VERIFY OWNERSHIP.</span>
              <br />
              PAY CREATORS.
            </h1>
            <p className="text-lg text-zinc-700 mb-10 max-w-xl">
              The Discord-native campaign tracker. Creators prove they own a
              social account by pasting a one-time code in their bio &mdash;
              then submit posts that the bot counts toward your payout goal.
            </p>
            <div className="flex flex-wrap gap-4">
              <Link to="/register" className="brut-btn" data-testid="hero-cta-register">
                GET STARTED &rarr;
              </Link>
              <Link to="/commands" className="brut-btn-secondary" data-testid="hero-cta-commands">
                BOT COMMANDS
              </Link>
            </div>
          </div>
          <div className="lg:col-span-5">
            <div className="brut-card-static p-6 font-mono text-sm bg-[#09090B] text-white">
              <div className="flex items-center gap-2 mb-4 text-zinc-500">
                <span className="w-3 h-3 bg-[#EF4444]" />
                <span className="w-3 h-3 bg-[#F59E0B]" />
                <span className="w-3 h-3 bg-[#10B981]" />
                <span className="ml-2">discord &mdash; #campaigns</span>
              </div>
              <div className="space-y-2">
                <div className="text-zinc-400">$ /verify platform:tiktok handle:@you</div>
                <div className="text-[#10B981]">→ Paste this in your bio:</div>
                <div className="bg-black/40 border border-zinc-700 px-2 py-1">
                  VRFY-9F2A41
                </div>
                <div className="text-zinc-400 mt-3">$ /verify-check ...</div>
                <div className="text-[#10B981]">✓ VERIFIED tiktok/@you</div>
                <div className="text-zinc-400 mt-3">$ /submit campaign:abc123 post:...</div>
                <div className="text-[#002FA7]">► Submitted. 18,432 views tracked.</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="max-w-7xl mx-auto px-6 py-20 border-b-2 border-black">
        <div className="mb-12 max-w-2xl">
          <div className="font-mono text-xs uppercase text-zinc-500 mb-3">
            // How it works
          </div>
          <h2 className="font-display text-4xl lg:text-5xl">
            Four steps. No middlemen.
          </h2>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Feature
            num="01"
            title="Connect Discord"
            body="Invite the bot to your server. Slash commands available instantly to all members."
          />
          <Feature
            num="02"
            title="Verify Account"
            body="Creator runs /verify, drops the code in their TikTok / IG / X / YouTube bio, runs /verify-check."
          />
          <Feature
            num="03"
            title="Run a Campaign"
            body="/create-campaign with a view goal and payout. Members submit posts to compete."
          />
          <Feature
            num="04"
            title="Auto-Track"
            body="Bot scrapes public view counts and ranks submissions on a live leaderboard."
          />
        </div>
      </section>

      {/* PLATFORMS */}
      <section className="bg-[#09090B] text-white border-b-2 border-black">
        <div className="max-w-7xl mx-auto px-6 py-20 grid lg:grid-cols-2 gap-10 items-center">
          <div>
            <div className="font-mono text-xs uppercase text-zinc-400 mb-3">// Platforms</div>
            <h2 className="font-display text-4xl lg:text-5xl mb-6">
              We watch the&nbsp;feeds.
            </h2>
            <p className="text-zinc-300 max-w-lg">
              Bio-code verification + view tracking on the four feeds that move
              the needle.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {["INSTAGRAM", "TIKTOK", "TWITTER / X", "YOUTUBE"].map((p) => (
              <div
                key={p}
                className="border-2 border-white p-6 text-center font-display text-xl hover:bg-[#002FA7] transition-colors"
              >
                {p}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* SLASH COMMANDS */}
      <section className="max-w-7xl mx-auto px-6 py-20">
        <div className="grid lg:grid-cols-12 gap-10">
          <div className="lg:col-span-5">
            <div className="font-mono text-xs uppercase text-zinc-500 mb-3">
              // Slash commands
            </div>
            <h2 className="font-display text-4xl lg:text-5xl mb-6">
              Type. Submit. Done.
            </h2>
            <p className="text-zinc-700 mb-6">
              Every command runs from inside Discord. No leaving the chat.
            </p>
            <Link to="/commands" className="brut-btn" data-testid="landing-view-all-commands">
              VIEW ALL COMMANDS
            </Link>
          </div>
          <div className="lg:col-span-7 brut-card-static p-8">
            <Cmd cmd="/verify" desc="Start verifying a social account" />
            <Cmd cmd="/verify-check" desc="Confirm the code is in your bio" />
            <Cmd cmd="/create-campaign" desc="Start a new campaign with goal + payout" />
            <Cmd cmd="/end-campaign" desc="Close a campaign and tally views" />
            <Cmd cmd="/submit" desc="Submit a post URL to a campaign" />
            <Cmd cmd="/campaigns" desc="List active campaigns" />
            <Cmd cmd="/accounts" desc="See your verified accounts" />
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="border-t-2 border-black bg-[#F4F4F5]">
        <div className="max-w-7xl mx-auto px-6 py-10 flex flex-wrap items-center justify-between gap-4">
          <div className="font-display text-lg">VIEWTRACKER</div>
          <div className="font-mono text-xs uppercase text-zinc-600">
            Built for creator campaigns
          </div>
        </div>
      </footer>
    </div>
  );
}
