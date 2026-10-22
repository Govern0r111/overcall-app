import { BetaNote } from "./BetaNote";
import { DashboardPreview } from "./DashboardPreview";
import { Faq } from "./Faq";
import { Footer } from "./Footer";
import { Hero } from "./Hero";
import { HowItWorks } from "./HowItWorks";
import { Nav } from "./Nav";
import { WhatWeCatch } from "./WhatWeCatch";
import "./landing.css";

export function LandingPage() {
  return (
    <div className="landing-page">
      <Nav />
      <main id="main-content">
        <Hero />
        <HowItWorks />
        <DashboardPreview />
        <WhatWeCatch />
        <BetaNote />
        <Faq />
      </main>
      <Footer />
    </div>
  );
}
