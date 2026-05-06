import "./globals.css";
import type { Metadata } from "next";
import Sidebar from "./_shell/Sidebar";
import Topbar from "./_shell/Topbar";

export const metadata: Metadata = {
  title: "Joby",
  description: "A private, local-first job search workspace.",
  icons: {
    icon: [
      { url: "/brand/logo.svg", type: "image/svg+xml" },
      { url: "/brand/logo.png", type: "image/png" },
    ],
    shortcut: "/brand/logo.svg",
    apple: "/brand/logo.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen flex bg-transparent">
          <Sidebar />
          <div className="flex-1 flex flex-col min-w-0">
            <Topbar />
            <main className="flex-1 px-4 pb-10 pt-2 sm:px-6 lg:px-8">
              <div className="max-w-[1400px] mx-auto">{children}</div>
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
