"use client";

import { useEffect } from "react";

function toText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value instanceof Error) return `${value.message}\n${value.stack || ""}`;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function isKnownExtensionOriginError(payload: {
  message?: string;
  filename?: string;
  stack?: string;
}): boolean {
  const message = (payload.message || "").toLowerCase();
  const filename = (payload.filename || "").toLowerCase();
  const stack = (payload.stack || "").toLowerCase();
  const combined = `${message}\n${filename}\n${stack}`;

  const hasTargetMessage = combined.includes("origin not allowed");
  const fromBrowserExtension =
    combined.includes("chrome-extension://") || combined.includes("inpage.js");

  return hasTargetMessage && fromBrowserExtension;
}

export function ExtensionErrorGuard() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      if (
        isKnownExtensionOriginError({
          message: event.message,
          filename: event.filename,
          stack: event.error?.stack,
        })
      ) {
        event.preventDefault();
      }
    };

    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      const reasonText = toText(event.reason);
      if (
        isKnownExtensionOriginError({
          message: reasonText,
          stack: reasonText,
        })
      ) {
        event.preventDefault();
      }
    };

    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    };
  }, []);

  return null;
}

