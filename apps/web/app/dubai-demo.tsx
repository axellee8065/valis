import { Attestation, fmtUsd, getAttestations, getStats, shortHex } from "@/lib/api";

/**
 * Dubai × Sukuk demo mode (docs/08). Rendered by app/page.tsx when
 * DEMO_MARKET=AE — the Korea site stays intact underneath, hidden by the flag.
 * All values are "Valuation Estimates" (not RERA appraisals — docs/06 §2.3).
 */

const LINKS = {
  github: "https://github.com/axellee8065/valis",
  integration:
    "https://github.com/axellee8065/valis/blob/main/docs/07-sukuk-integration.md",
  suiscan: "https://suiscan.xyz/testnet/object/",
};

const CHAIN = {
  packageId:
    "0x7f8400996b4712aaf2b8a386415f0b6e1389dcc4b14aa182e841756d1d6ebdc0",
  feed: "0xe76f7031e20c49971819158dc7ccf4086353533be32af950b15ad0e2db6e3454",
  sukukPackage:
    process.env.NEXT_PUBLIC_SUKUK_PACKAGE_ID ??
    "0x286459135e4a1fb6b2f6aae6b2b5b34e202c5766115545d50e92a470117a9fcf",
  spvObject:
    process.env.NEXT_PUBLIC_SUKUK_SPV_ID ??
    "0xb1892c02538523fc50e6291b5910513c51ad57bd899fda53b53953d3a475f7e5",
};

export default async function DubaiDemo() {
  const [{ stats, live }, attestations] = await Promise.all([
    getStats("AE"),
    getAttestations("AE"),
  ]);

  return (
    <div className="min-h-screen">
      <Nav />
      <main>
        <Hero live={live} featured={attestations[0]} />
        <Metrics
          stats={[
            { label: "DLD sale transactions", value: stats.transactions },
            { label: "Unit classes tracked", value: stats.properties },
            { label: "Buildings covered", value: stats.complexes },
            { label: "On-chain attestations", value: stats.active_attestations },
          ]}
        />
        <SukukFlow />
        <OnChain attestations={attestations} />
        <Disclosure />
        <CtaBand />
      </main>
      <Footer />
    </div>
  );
}

function Nav() {
  return (
    <nav className="top-nav sticky top-0 z-20">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-6">
        <a href="#" className="flex items-center gap-2.5">
          <span
            className="grid h-7 w-7 place-items-center rounded-full text-[13px] font-semibold"
            style={{ background: "var(--primary)", color: "var(--on-primary)" }}
          >
            V
          </span>
          <span className="title-sm" style={{ letterSpacing: "-0.01em" }}>
            Valis<span style={{ color: "var(--muted)" }}>.protocol</span>
          </span>
          <span className="badge-pill ml-2">Dubai</span>
        </a>
        <div className="hidden items-center gap-7 md:flex">
          <a className="nav-link" href="#sukuk">Sukuk flow</a>
          <a className="nav-link" href="#onchain">On-chain</a>
          <a className="nav-link" href={LINKS.integration}>Integration guide</a>
        </div>
        <a className="btn-primary" href={LINKS.integration}>
          Read the integration guide
        </a>
      </div>
    </nav>
  );
}

function Hero({ live, featured }: { live: boolean; featured?: Attestation }) {
  return (
    <section className="mx-auto max-w-[1200px] px-6 pb-24 pt-24">
      <div className="grid items-center gap-14 lg:grid-cols-[7fr_5fr]">
        <div>
          <span className="badge-pill">
            <span className="dot" />
            {live ? "Live on Sui Testnet" : "Sui Testnet"} · Dubai pilot
          </span>
          <h1 className="display-xl mt-6" style={{ textWrap: "balance" }}>
            Verified collateral for
            <br />
            sukuk issuance
          </h1>
          <p className="body-md mt-6 max-w-[56ch]" style={{ color: "var(--muted)" }}>
            Valis turns Dubai Land Department transaction records into on-chain
            Valuation Estimates with explicit confidence intervals. A sukuk SPV
            reads them through a collateral gate: excessive uncertainty is
            refused — not priced. Quantified gharar, enforced by code.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <a className="btn-primary" href="#sukuk">
              See the issuance flow
            </a>
            <a className="btn-secondary" href={LINKS.github} target="_blank" rel="noreferrer">
              GitHub
            </a>
          </div>
        </div>
        <FeaturedCard att={featured} />
      </div>
    </section>
  );
}

function FeaturedCard({ att }: { att?: Attestation }) {
  if (!att) {
    return (
      <div className="hero-mockup-card">
        <div className="caption" style={{ color: "var(--muted)" }}>
          LATEST DUBAI ATTESTATION
        </div>
        <div className="body-sm mt-4" style={{ color: "var(--muted)" }}>
          First Dubai attestations are being issued — refresh shortly.
        </div>
      </div>
    );
  }
  const conf = (att.confidence_score_bps / 100).toFixed(2);
  return (
    <div className="hero-mockup-card">
      <div className="flex items-center justify-between">
        <span className="caption" style={{ color: "var(--muted)" }}>
          LATEST DUBAI ATTESTATION
        </span>
        <span className="badge-pill">
          <span className="dot" />
          {att.confidence_score_bps >= 8500 ? "AUTO_ISSUE" : "REVIEW · pilot"}
        </span>
      </div>
      <div className="mt-4">
        <div className="title-md">{att.complex_name ?? "Dubai apartment"}</div>
        <div className="body-sm" style={{ color: "var(--muted)" }}>
          {att.admin_level_2} · {att.net_area_sqm} m² class
        </div>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-4">
        <div>
          <div className="caption" style={{ color: "var(--muted)" }}>
            Valuation Estimate
          </div>
          <div className="display-sm tnum">{fmtUsd(att.value_usd_cents)}</div>
        </div>
        <div>
          <div className="caption" style={{ color: "var(--muted)" }}>
            Confidence
          </div>
          <div className="display-sm tnum">{conf}%</div>
        </div>
      </div>
      <div className="mt-4 body-sm tnum" style={{ color: "var(--muted)" }}>
        95% CI {fmtUsd(att.ci_lower_usd_cents)} – {fmtUsd(att.ci_upper_usd_cents)}
      </div>
      <a
        className="text-link body-sm mono mt-4 block"
        href={`https://suiscan.xyz/testnet/tx/${att.sui_tx_digest}`}
        target="_blank"
        rel="noreferrer"
      >
        tx {shortHex(att.sui_tx_digest, 10, 8)}
      </a>
    </div>
  );
}

function Metrics({ stats }: { stats: { label: string; value: number }[] }) {
  return (
    <section className="mx-auto max-w-[1200px] px-6 pb-20">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="feature-card">
            <div className="display-md tnum">{s.value.toLocaleString("en-US")}</div>
            <div className="body-sm mt-2" style={{ color: "var(--muted)" }}>
              {s.label}
            </div>
          </div>
        ))}
      </div>
      <p className="caption mt-4" style={{ color: "var(--muted)" }}>
        Source: Dubai Land Department open transaction data (residential unit
        sales). Metrics computed on a fully isolated holdout window.
      </p>
    </section>
  );
}

function SukukFlow() {
  const steps = [
    {
      n: "①",
      title: "Attest",
      body: "DLD sale records → AVM Valuation Estimate → on-chain attestation with a 95% CI, confidence score, and report hash. Published to the shared ValuationFeed.",
      code: "valis::batch::register_and_attest(...)",
    },
    {
      n: "②",
      title: "Gate",
      body: "The SPV can only be created if the asset passes the collateral gate: fresh attestation, confidence ≥ the scholar-approved floor, target raise ≤ LTV-bounded max issuance.",
      code: "valis::collateral::check_and_log(feed, id, clock, 7000, 90d, 5000)",
    },
    {
      n: "③",
      title: "Issue",
      body: "Investors subscribe for SukukCertificate objects. Every subscription re-checks the gate — a stale or degraded valuation halts issuance automatically.",
      code: "sukuk_demo::spv::subscribe(spv, feed, face_value, clock)",
    },
  ];
  return (
    <section id="sukuk" className="mx-auto max-w-[1200px] px-6 pb-24">
      <h2 className="display-lg" style={{ textWrap: "balance" }}>
        Asset-backed, provably
      </h2>
      <p className="body-md mt-4 max-w-[60ch]" style={{ color: "var(--muted)" }}>
        Ijarah sukuk is asset-backed by religious requirement. The hard part has
        always been the oracle: what is the asset actually worth? Valis answers
        with calibrated uncertainty — and the gate turns that answer into an
        issuance ceiling no transaction can cross.
      </p>
      <div className="mt-10 grid gap-4 lg:grid-cols-3">
        {steps.map((s, i) => (
          <div key={s.n} className={i === 1 ? "tier-card-featured" : "tier-card"}>
            <div className="caption" style={{ color: i === 1 ? "var(--on-dark-soft)" : "var(--muted)" }}>
              STEP {s.n}
            </div>
            <div className="title-lg mt-2">{s.title}</div>
            <p className="body-sm mt-3" style={{ lineHeight: 1.6 }}>
              {s.body}
            </p>
            <div
              className="mono mt-5 rounded-lg p-3 text-[12px]"
              style={{
                background: i === 1 ? "var(--surface-dark-elevated)" : "var(--surface-card)",
                color: i === 1 ? "var(--on-dark-soft)" : "var(--ink)",
                overflowWrap: "anywhere",
              }}
            >
              {s.code}
            </div>
          </div>
        ))}
      </div>
      {CHAIN.spvObject && (
        <div className="mockup-card mt-6">
          <span className="caption" style={{ color: "var(--muted)" }}>
            LIVE DEMO SPV
          </span>
          <a
            className="text-link mono body-sm mt-2 block addr"
            href={`${LINKS.suiscan}${CHAIN.spvObject}`}
            target="_blank"
            rel="noreferrer"
          >
            {CHAIN.spvObject}
          </a>
        </div>
      )}
    </section>
  );
}

function OnChain({ attestations }: { attestations: Attestation[] }) {
  return (
    <section id="onchain" className="mx-auto max-w-[1200px] px-6 pb-24">
      <h2 className="display-md">Recent Dubai attestations</h2>
      <div className="mockup-card mt-6" style={{ overflowX: "auto" }}>
        <table className="ledger">
          <thead>
            <tr>
              <th>Building</th>
              <th>Area</th>
              <th>Estimate</th>
              <th>95% CI</th>
              <th>Confidence</th>
              <th>Tx</th>
            </tr>
          </thead>
          <tbody>
            {attestations.length === 0 && (
              <tr>
                <td colSpan={6} style={{ color: "var(--muted)" }}>
                  Issuing…
                </td>
              </tr>
            )}
            {attestations.map((a) => (
              <tr key={a.attestation_uid}>
                <td>{a.complex_name ?? shortHex(a.global_id)}</td>
                <td>{a.admin_level_2}</td>
                <td className="tnum">{fmtUsd(a.value_usd_cents)}</td>
                <td className="tnum">
                  {fmtUsd(a.ci_lower_usd_cents)}–{fmtUsd(a.ci_upper_usd_cents)}
                </td>
                <td className="tnum">
                  {(a.confidence_score_bps / 100).toFixed(1)}%
                </td>
                <td>
                  <a
                    className="text-link mono"
                    href={`https://suiscan.xyz/testnet/tx/${a.sui_tx_digest}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {shortHex(a.sui_tx_digest, 6, 4)}
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex flex-wrap gap-x-8 gap-y-1">
        <a className="text-link body-sm mono" href={`${LINKS.suiscan}${CHAIN.packageId}`} target="_blank" rel="noreferrer">
          package {shortHex(CHAIN.packageId)}
        </a>
        <a className="text-link body-sm mono" href={`${LINKS.suiscan}${CHAIN.feed}`} target="_blank" rel="noreferrer">
          feed {shortHex(CHAIN.feed)}
        </a>
      </div>
    </section>
  );
}

function Disclosure() {
  return (
    <section className="mx-auto max-w-[1200px] px-6 pb-24">
      <div className="feature-card">
        <div className="title-md">What this is — and is not</div>
        <p className="body-sm mt-3 max-w-[75ch]" style={{ color: "var(--muted)", lineHeight: 1.7 }}>
          Valis publishes Valuation Estimates — statistical reference values with
          calibrated uncertainty — not RERA-registered appraisals. Physical
          condition, insurance, and legal title remain off-chain diligence.
          Identity is a unit class (building × bedrooms × built-up area), the
          finest identity the public DLD record supports — which caps Dubai
          confidence in the REVIEW tier, so the pilot gate compensates with a
          lower LTV (50%) on top of the confidence haircut. Nothing is hidden:
          the demo SPV was created with pilot parameters (70% floor, 50% LTV)
          visible in its on-chain creation event. Data vintage: DLD open data
          snapshot through 2024-08; live top-up resumes when the DLD gateway is
          back online.
        </p>
      </div>
    </section>
  );
}

function CtaBand() {
  return (
    <section className="mx-auto max-w-[1200px] px-6 pb-24">
      <div className="cta-band">
        <h2 className="display-md" style={{ textWrap: "balance" }}>
          Building a sukuk or RWA protocol?
        </h2>
        <p className="body-md mx-auto mt-3 max-w-[48ch]" style={{ color: "var(--muted)" }}>
          The collateral gate is four Move functions. The integration guide maps
          them onto an ijarah SPV end to end.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <a className="btn-primary" href={LINKS.integration}>
            Integration guide
          </a>
          <a className="btn-secondary" href={LINKS.github} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="footer-dark mt-8">
      <div className="mx-auto max-w-[1200px] px-6 py-14">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div className="title-sm" style={{ color: "var(--on-dark)" }}>
            Valis.protocol — Dubai pilot
          </div>
          <div className="flex gap-6">
            <a href={LINKS.github} target="_blank" rel="noreferrer">GitHub</a>
            <a href={LINKS.integration}>Integration</a>
          </div>
        </div>
        <p className="body-sm mt-8" style={{ color: "var(--on-dark-soft)" }}>
          Valuation Estimates, not appraisals. Sui Testnet. Data: Dubai Land
          Department open data.
        </p>
      </div>
    </footer>
  );
}
