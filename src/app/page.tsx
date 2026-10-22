import { Landing } from "@/components/heardit";
import { loadDemoSamples } from "@/lib/demo-audio";
import type { components } from "@/lib/api-schema";

type PublicStats = components["schemas"]["PublicProductStats"];

function isPublicStats(value: unknown): value is PublicStats {
  if (!value || typeof value !== "object") return false;
  const stats = value as Record<string, unknown>;
  return Number.isInteger(stats.published_tests)
    && Number.isInteger(stats.tests_with_responses)
    && Number.isInteger(stats.listener_responses);
}

export const revalidate = 300;

async function getPublicStats(): Promise<PublicStats | null> {
  const apiOrigin = process.env.API_INTERNAL_URL?.replace(/\/$/, "");
  if (!apiOrigin) return null;
  try {
    const response = await fetch(`${apiOrigin}/api/v1/stats/public`, { next: { revalidate } });
    if (!response.ok) return null;
    const value: unknown = await response.json();
    return isPublicStats(value) ? value : null;
  } catch {
    return null;
  }
}

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

export default async function Page() {
  const [publicStats, demoSamples] = await Promise.all([getPublicStats(), loadDemoSamples()]);
  return <>
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }} />
    <Landing publicStats={publicStats} demoSamples={demoSamples} />
  </>;
}
