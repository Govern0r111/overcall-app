import { Accordion } from "../../components/ui/FaqAccordion";

const questions = [
  {
    question: "Do you store my prompts or request bodies?",
    answer: "No. Overcall stores metadata such as hashes, sizes, token counts, status, latency and cost. Request and response bodies are not stored.",
  },
  {
    question: "Do I give Overcall my OpenAI or Stripe key?",
    answer: "No. Your provider key stays in your app. Overcall uses a separate key to identify traffic sent through its proxy.",
  },
  {
    question: "Does using a proxy slow down my app?",
    answer: "A proxy adds a step to each request. We measure the overhead and will publish those measurements; we do not promise a specific number before it is tested.",
  },
  {
    question: "What about Stripe?",
    answer: "Stripe support is for test keys only. Live Stripe keys are not accepted.",
  },
  {
    question: "How accurate are the savings?",
    answer: "Savings are estimates based on observed request patterns and provider pricing. They are not a guarantee, and reliability findings are shown as a separate count.",
  },
];

export function Faq() {
  return (
    <section className="section section--bordered faq-section" aria-labelledby="faq-title">
      <div className="container faq-layout">
        <div className="section-heading">
          <p className="eyebrow">Good to know</p>
          <h2 id="faq-title">Questions, answered.</h2>
        </div>
        <Accordion items={questions} />
      </div>
    </section>
  );
}
