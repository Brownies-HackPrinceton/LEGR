"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Home" },
  { href: "/connect", label: "Connect" },
];

export function Navbar() {
  const path = usePathname() ?? "/";
  return (
    <header className="navbar">
      <div className="brand">Flux</div>
      <nav>
        {TABS.map((t) => {
          const active = t.href === "/" ? path === "/" : path.startsWith(t.href);
          return (
            <Link
              key={t.href}
              href={t.href}
              className={active ? "active" : undefined}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
