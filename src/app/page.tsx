import { Landing } from "@/components/heardit";

const publicOrigin = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

const faqs = [
  {
    question: "What does HeardIt measure?",
    answer: "It compares which interpretation listeners select after hearing a generated clip with the choices made by listeners who read the same sentence.",
  },
  {
    question: "How are listeners assigned?",
    answer: "HeardIt randomly assigns each browser to the audio or text condition and keeps that assignment stable for that test.",
  },
  {
    question: "Do listeners need an account?",
    answer: "No. A listener can open a shared test and respond without signing up.",
  },
  {
    question: "Can a listener vote more than once?",
    answer: "A stable browser identifier and a unique database constraint prevent ordinary repeat submissions from the same browser. This is not proof of a unique human identity.",
  },
  {
    question: "Are the results statistically conclusive?",
    answer: "No. Results describe the people who responded to a specific test. Small samples are marked preliminary and shown with Wilson confidence intervals.",
  },
  {
    question: "Does HeardIt measure voice quality?",
    answer: "No. It measures which interpretation people select. A difference between groups is exploratory, not proof of a universal voice effect.",
  },
];

const structuredData = [
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "HeardIt",
    url: `${publicOrigin}/`,
    logo: `${publicOrigin}/heardit-logo.svg`,
    description: "A listening experiment for exploring how people interpret AI-generated speech.",
  },
  {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "HeardIt",
    url: `${publicOrigin}/`,
    description: "Create a listening test and compare how people interpret the same sentence as audio or text.",
  },
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "HeardIt",
    applicationCategory: "EducationalApplication",
    operatingSystem: "Web",
    description: "An exploratory product experiment that compares listener interpretations of generated speech and its text transcript.",
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map(({ question, answer }) => ({
      "@type": "Question",
      name: question,
      acceptedAnswer: { "@type": "Answer", text: answer },
    })),
  },
];

export default function Page() {
  return <>
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }} />
    <Landing />
  </>;
}
