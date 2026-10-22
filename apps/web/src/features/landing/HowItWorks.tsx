const steps = [
  {
    number: "01",
    title: "Point your base URL at the proxy",
    description: "Keep your provider key in your app. Change the API URL and add your Overcall key.",
  },
  {
    number: "02",
    title: "We log and analyse",
    description: "Overcall records request metadata and checks for patterns that waste spend or hurt reliability.",
  },
  {
    number: "03",
    title: "See where money is wasted",
    description: "Review clear findings, understand why they matter and decide what to fix first.",
  },
];

export function HowItWorks() {
  return (
    <section className="section section--bordered" id="how-it-works" aria-labelledby="how-title">
      <div className="container">
        <div className="section-heading">
          <p className="eyebrow">A simple setup</p>
          <h2 id="how-title">One small change. A clearer API bill.</h2>
        </div>
        <ol className="steps">
          {steps.map(({ number, title, description }) => (
            <li className="step" key={number}>
              <span className="step__number">{number}</span>
              <h3>{title}</h3>
              <p>{description}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
