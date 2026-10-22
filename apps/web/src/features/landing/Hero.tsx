import { ArrowRight, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

export function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero__copy">
        <p className="eyebrow"><Sparkles aria-hidden="true" size={15} /> Free during beta</p>
        <h1 id="hero-title">See where your API money goes.</h1>
        <p className="hero__lead">
          Point your API base URL at Overcall. We log request metadata, spot wasteful patterns and
          show what fixing them would save.
        </p>
        <div className="hero__actions">
          <Link className="button button--primary" to="/app">
            Try the demo <ArrowRight aria-hidden="true" size={17} />
          </Link>
          <a className="button button--secondary" href="#how-it-works">See how it works</a>
        </div>
        <p className="hero__privacy">Your provider keys stay in your app. Request and response bodies are not stored.</p>
      </div>
      <div className="hero__note" aria-hidden="true">
        <span className="hero__note-line" />
        <span>Clearer API costs start with metadata, not prompt access.</span>
      </div>
    </section>
  );
}
