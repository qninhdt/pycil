import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "sonner";
import { AppSettingsProvider } from "@/providers";
import { ThemeProvider } from "@/components/providers";
import { QueryProvider } from "@/providers/query-provider";

export const metadata: Metadata = {
  title: "Pycil - Learning Made Simple",
  description:
    "Create, study, and master terms with our powerful learning platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <AppSettingsProvider>
          <ThemeProvider>
            <QueryProvider>
            {children}
            <Toaster position="top-right" richColors closeButton />
          </QueryProvider>
          </ThemeProvider>
        </AppSettingsProvider>
      </body>
    </html>
  );
}
