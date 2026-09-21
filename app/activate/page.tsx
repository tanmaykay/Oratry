import { OratryApp } from "@/features/app/oratry-app";

/**
 * The activation email is an external deep link, so Next.js needs a concrete
 * route before the client application can read its one-time token.
 */
export default function ActivatePage() {
  return <OratryApp />;
}
