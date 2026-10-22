import { Landing } from "@/components/heardit";

const publicOrigin = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

const faqs = [
  {
    question: "What does HeardIt measure?",
    answer: "It compares which interpretation listeners select after hearing a generated clip with the choices made by listeners who read the same sentence.",
  },
  {
    question: "Are the results statistically conclusive?",
    answer: "No. Results describe the people who responded to a specific test. Small samples are marked preliminary and shown with Wilson confidence intervals.",
  },
  {
    question: "Does the demo use real audio?",
    answer: "When a genuine sample clip is configured, the demo player uses that file. If no clip is configured, the page says so and offers the creator studio.",
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
