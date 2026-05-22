import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export const Navbar = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <nav
      data-testid="main-nav"
      className="sticky top-0 z-40 bg-white/90 backdrop-blur-xl border-b-2 border-black"
    >
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3" data-testid="nav-logo">
          <div className="w-8 h-8 bg-black flex items-center justify-center">
            <div className="w-3 h-3 bg-[#002FA7]" />
          </div>
          <span className="font-display text-xl">VIEWTRACKER</span>
        </Link>
        <div className="flex items-center gap-6 text-sm font-medium">
          <Link to="/campaigns" className="hover:underline" data-testid="nav-campaigns">
            Campaigns
          </Link>
          <Link to="/commands" className="hover:underline" data-testid="nav-commands">
            Bot&nbsp;Commands
          </Link>
          {user ? (
            <>
              <Link to="/dashboard" className="hover:underline" data-testid="nav-dashboard">
                Dashboard
              </Link>
              <button
                onClick={() => {
                  logout();
                  navigate("/");
                }}
                className="font-mono text-xs uppercase tracking-wider border-2 border-black px-3 py-1.5 hover:bg-black hover:text-white transition-colors"
                data-testid="nav-logout"
              >
                Logout
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="hover:underline" data-testid="nav-login">
                Login
              </Link>
              <Link
                to="/register"
                className="font-mono text-xs uppercase tracking-wider bg-black text-white px-3 py-1.5 border-2 border-black hover:bg-[#002FA7] transition-colors"
                data-testid="nav-register"
              >
                Sign&nbsp;Up
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
};
