import type { Metadata } from "next";
import "./globals.css";
import { TopNav } from "../components/top-nav";
import { I18nProvider } from "../lib/i18n-provider";
import { ExtensionErrorGuard } from "../components/extension-error-guard";

export const metadata: Metadata = {
  title: "PayFi Box",
  description: "Stablecoin settlement workspace for intake, funding, execution, and audit visibility",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="bg-slate-100 text-slate-900">
        <I18nProvider>
          <ExtensionErrorGuard />
          <TopNav />
          <div className="mx-auto w-full max-w-7xl px-4 py-6 lg:px-8 lg:py-8">{children}</div>
        </I18nProvider>
      </body>
    </html>
  );
}
