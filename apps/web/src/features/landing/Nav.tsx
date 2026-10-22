import { Link } from "react-router-dom";
import { ThemeToggle } from "../../components/ThemeToggle";

export function Nav() {
  return (
    <header className="site-header">
      <nav className="site-nav" aria-label="Main navigation">
        <Link aria-label="Overcall home" className="brand" to="/">
          <span aria-hidden="true" className="brand__mark">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 2.8 20 6v5.7c0 5.2-3.3 8.5-8 10.3-4.7-1.8-8-5.1-8-10.3V6l8-3.2Z" />
              <path d="m8.4 12.1 2.2 2.2 5-5.2" />
            </svg>
          </span>
          <span>Overcall</span>
        </Link>

        <div className="site-nav__actions">
          <a className="site-nav__how" href="#how-it-works">How it works</a>
          <ThemeToggle />
          <Link className="site-nav__login" to="/login">Log in</Link>
          <Link className="button button--primary site-nav__signup" to="/signup">Sign up</Link>
        </div>
      </nav>
    </header>
  );
}
