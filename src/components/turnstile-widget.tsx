"use client";

import { useEffect, useRef } from "react";

type TurnstileOptions = {
  sitekey: string;
  callback: (token: string) => void;
  "expired-callback": () => void;
  "error-callback": () => void;
};

declare global {
  interface Window {
    turnstile?: {
      render: (element: HTMLElement, options: TurnstileOptions) => string;
      remove: (widgetId: string) => void;
    };
    __hearditTurnstileLoad?: Promise<void>;
  }
}

function loadTurnstile(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  if (window.__hearditTurnstileLoad) return window.__hearditTurnstileLoad;

  window.__hearditTurnstileLoad = new Promise((resolve, reject) => {
    const current = document.querySelector<HTMLScriptElement>("script[data-heardit-turnstile]");
    const script = current ?? document.createElement("script");
    script.addEventListener("load", () => resolve(), { once: true });
    script.addEventListener("error", () => reject(new Error("Security check could not load.")), { once: true });
    if (!current) {
      script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      script.async = true;
      script.defer = true;
      script.dataset.hearditTurnstile = "true";
      document.head.appendChild(script);
    } else if (window.turnstile) {
      resolve();
    }
  });

  return window.__hearditTurnstileLoad;
}

export function TurnstileWidget({
  siteKey,
  onToken,
  onError,
}: {
  siteKey: string;
  onToken: (token: string) => void;
  onError: (message: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const tokenHandler = useRef(onToken);
  const errorHandler = useRef(onError);

  useEffect(() => {
    tokenHandler.current = onToken;
    errorHandler.current = onError;
  }, [onToken, onError]);

  useEffect(() => {
    if (!siteKey || !container.current) return;
    let active = true;
    loadTurnstile().then(() => {
      if (!active || !container.current || !window.turnstile) return;
      widgetId.current = window.turnstile.render(container.current, {
        sitekey: siteKey,
        callback: token => tokenHandler.current(token),
        "expired-callback": () => tokenHandler.current(""),
        "error-callback": () => errorHandler.current("Security verification failed to load. Please retry the check."),
      });
    }).catch(error => {
      if (active) errorHandler.current(error instanceof Error ? error.message : "Security check could not load.");
    });
    return () => {
      active = false;
      if (widgetId.current && window.turnstile) window.turnstile.remove(widgetId.current);
      widgetId.current = null;
    };
  }, [siteKey]);

  if (!siteKey) return null;
  return <div className="hi-turnstile"><div ref={container}/><p>Complete the security check to continue.</p></div>;
}
