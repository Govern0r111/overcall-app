import { Link } from "react-router-dom";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="container site-footer__inner">
        <Link aria-label="Overcall home" className="brand brand--footer" to="/">
          <span aria-hidden="true" className="brand__mark">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 2.8 20 6v5.7c0 5.2-3.3 8.5-8 10.3-4.7-1.8-8-5.1-8-10.3V6l8-3.2Z" />
              <path d="m8.4 12.1 2.2 2.2 5-5.2" />
            </svg>
          </span>
          <span>Overcall</span>
        </Link>
        <p>Clearer API costs, without storing your prompts.</p>
        <span className="site-footer__copyright">© {new Date().getFullYear()} Overcall</span>
      </div>
    </footer>
  );
}
