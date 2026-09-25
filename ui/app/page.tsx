"use client";

import { useEffect, useState } from "react";

// Every request goes to THIS origin. The browser never learns the service's address and never
// holds its credential; the route handler under /api/agent forwards, having discarded whatever
// identity the client tried to assert.
const API = "/api/agent";

// Mirrors the service's seeded local personas. The picker is a DEV convenience: the server
// validates the selection against its own list, so a hand-crafted value cannot invent a persona.
const PERSONAS = ["analyst", "approver", "auditor", "other-tenant"];

// What happened to the human-review hand-off, in the words the user needs. A result that
// escalated but is not queued must say so rather than read as reviewed.
const REVIEW_ROUTING_TEXT: Record<string, string> = {
  routed: "Sent to the review console.",
  failed: "Could not reach the review console; this case is not queued for review.",
  off: "Review routing is off in this deployment; this case is not queued for review.",
};

function reviewRoutingOf(body: string): string | undefined {
  try {
    const parsed = JSON.parse(body) as { review_routing?: unknown };
    return typeof parsed.review_routing === "string" ? parsed.review_routing : undefined;
  } catch {
    return undefined;
  }
}

// The party kinds `ScreenRequest.kind` accepts; the kind changes how a name is matched.
const PARTY_KINDS = ["individual", "entity", "vessel", "unknown"];

// Read the optional payment-message fields: an object of string values, keyed by ISO 20022
// element name or SWIFT tag. Blank means no message, so only the subject is screened.
function parseMessage(raw: string): Record<string, string> {
  if (!raw.trim()) return {};
  const parsed: unknown = JSON.parse(raw);
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    Array.isArray(parsed) ||
    Object.values(parsed).some((value) => typeof value !== "string")
  ) {
    throw new Error("the payment message must be a JSON object of string fields");
  }
  return parsed as Record<string, string>;
}

interface CardSummary {
  name?: string;
  description?: string;
  skills?: { id: string; name: string }[];
}

export default function Home() {
  const [persona, setPersona] = useState(PERSONAS[0]);
  // Prefilled with a fictional subject on the local OFAC sample list, so the first submit shows a
  // real match, its arithmetic and the list entry it cites.
  const [subject, setSubject] = useState("Marisol Quintana (FICTIONAL)");
  const [kind, setKind] = useState("individual");
  const [dob, setDob] = useState("1975-09-30");
  const [jurisdiction, setJurisdiction] = useState("SG");
  const [messageText, setMessageText] = useState("");
  const [result, setResult] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState<CardSummary | null>(null);

  // The service names itself, so this UI carries no hardcoded product name to go stale.
  useEffect(() => {
    let live = true;
    fetch(API + "/.well-known/agent-card.json", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (live) setCard(body as CardSummary | null);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailed(false);
    try {
      const message = parseMessage(messageText);
      const response = await fetch(API + "/v1/screen", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Dev-Persona": persona },
        body: JSON.stringify({ subject, kind, dob, jurisdiction, message }),
      });
      const body = await response.text();
      setFailed(!response.ok);
      setResult(body);
    } catch (error) {
      setFailed(true);
      setResult(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>{card?.name ?? "Agent console"}</h1>
      <p className="sub">
        {card?.description ??
          "Screen a party. The match band is deterministic, cited, and every disposition is routed to a human reviewer."}
      </p>

      <form onSubmit={submit}>
        <fieldset>
          <legend>Who you are</legend>
          <label>
            Seeded dev persona (local profile only; the server resolves identity, not this field)
            <select value={persona} onChange={(event) => setPersona(event.target.value)}>
              {PERSONAS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <fieldset>
          <legend>The party to screen</legend>
          <label>
            Subject name
            <input value={subject} onChange={(event) => setSubject(event.target.value)} />
          </label>
          <label>
            Kind
            <select value={kind} onChange={(event) => setKind(event.target.value)}>
              {PARTY_KINDS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Date of birth (YYYY-MM-DD, optional; scored against the list entry&apos;s)
            <input value={dob} onChange={(event) => setDob(event.target.value)} />
          </label>
          <label>
            Jurisdiction (optional; recorded on the screened party, never scored into the band)
            <input value={jurisdiction} onChange={(event) => setJurisdiction(event.target.value)} />
          </label>
          <label>
            Payment message (optional JSON; each named party is screened too)
            <textarea
              value={messageText}
              placeholder={'{ "Cdtr/Nm": "Redsea Shipping Ltd (FICTIONAL)" }'}
              onChange={(event) => setMessageText(event.target.value)}
            />
          </label>
          <button type="submit" disabled={busy || !subject.trim()}>
            {busy ? "Working" : "Screen this party"}
          </button>
        </fieldset>
      </form>

      {result && REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""] ? (
        <p className="sub" data-review-routing={reviewRoutingOf(result)}>
          {REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""]}
        </p>
      ) : null}
      {result ? <pre className={failed ? "result error" : "result"}>{result}</pre> : null}

      <footer>
        Synthetic, obviously fictional data only. Identity is resolved server-side and the
        client-asserted actor is discarded; see ui/README.md for the embedding contract.
      </footer>
    </main>
  );
}
