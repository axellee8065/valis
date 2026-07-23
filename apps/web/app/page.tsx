import {
  Attestation,
  fmtInt,
  fmtUsd,
  getAttestations,
  getStats,
  shortHex,
} from "@/lib/api";

const LINKS = {
  github: "https://github.com/axellee8065/valis",
  api: "https://valis-api-production.up.railway.app",
  whitepaper:
    "https://github.com/axellee8065/valis/blob/main/docs/whitepaper_v1_draft.md",
  suiscan:
    "https://suiscan.xyz/testnet/object/0x71fa1119d5cfdf3bf2faf8419c89ef3361f3d2ae35ac02e765f3e6aec37b4d74",
};

const CHAIN = {
  packageId:
    "0x71fa1119d5cfdf3bf2faf8419c89ef3361f3d2ae35ac02e765f3e6aec37b4d74",
  feed: "0xe76f7031e20c49971819158dc7ccf4086353533be32af950b15ad0e2db6e3454",
  index: "0x596e8701b9c9db1c6673a8cbaf1c543f904df3dd8f05b6d24c0e0f3830463f8d",
  registry: "0x3c33ea7a4c7e5ac7bcafcd887d179290044063da5fa7bbc7dc7d70dc923f842e",
};

export default async function Home() {
  const [{ stats, live }, attestations] = await Promise.all([
    getStats(),
    getAttestations(),
  ]);

  return (
    <div className="min-h-screen">
      <Nav />
      <main>
        <Hero live={live} featured={attestations[0]} />
        <Metrics stats={stats} />
        <HowItWorks />
        <Tiers />
        <OnChain attestations={attestations} />
        <Integration />
        <CtaBand />
      </main>
      <Footer stats={stats} />
    </div>
  );
}

/* ─────────────────────────── nav ─────────────────────────── */

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
        </a>
        <div className="hidden items-center gap-7 md:flex">
          <a className="nav-link" href="#how">프로토콜</a>
          <a className="nav-link" href="#tiers">검증 성능</a>
          <a className="nav-link" href="#onchain">온체인</a>
          <a className="nav-link" href="#integrate">개발자</a>
          <a className="nav-link" href={LINKS.whitepaper}>백서</a>
        </div>
        <div className="flex items-center gap-4">
          <a
            className="text-link body-sm hidden sm:block"
            href={LINKS.github}
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>
          <a className="btn-primary" href={LINKS.whitepaper}>
            백서 읽기
          </a>
        </div>
      </div>
    </nav>
  );
}

/* ─────────────────────────── hero ────────────────────────── */

function Hero({ live, featured }: { live: boolean; featured?: Attestation }) {
  return (
    <section className="mx-auto max-w-[1200px] px-6 pb-24 pt-24">
      <div className="grid items-center gap-14 lg:grid-cols-[7fr_5fr]">
        <div>
          <span className="badge-pill">
            <span className="dot" />
            Sui Testnet 가동 중 · attestation 발행 중
          </span>
          <h1 className="display-xl mt-6" style={{ textWrap: "balance" }}>
            부동산 가치를 검증하는
            <br />
            더 나은 방법
          </h1>
          <p className="body-md mt-6 max-w-[52ch]" style={{ color: "var(--muted)" }}>
            Valis는 정부 실거래 데이터와 AVM을 결합해 감정 결과를
            신뢰구간·신뢰도와 함께 온체인에 발행합니다. 밀봉 홀드아웃으로
            검증하고, 근거 리포트를 해시로 앵커링합니다 — RWA 프로토콜이
            바로 읽어가는 하나의 공유 피드로.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <a className="btn-primary" href={LINKS.whitepaper}>
              백테스트 백서 읽기
            </a>
            <a
              className="btn-secondary"
              href={LINKS.github}
              target="_blank"
              rel="noreferrer"
            >
              GitHub에서 코드 보기
            </a>
          </div>
          <p className="caption mt-6" style={{ color: "var(--muted-soft)" }}>
            오픈소스 · 재현 가능한 백테스트 · 법정 감정평가가 아닌 참고용 가치
            추정
          </p>
        </div>

        <AttestationWidget live={live} att={featured} />
      </div>
    </section>
  );
}

/** The hero product artifact — real attestation chrome, Cal.com-style. */
function AttestationWidget({ live, att }: { live: boolean; att?: Attestation }) {
  const value = att ? fmtUsd(att.value_usd_cents) : "$409,191";
  const lo = att ? fmtUsd(att.ci_lower_usd_cents) : "$346,512";
  const hi = att ? fmtUsd(att.ci_upper_usd_cents) : "$469,618";
  const conf = att ? (att.confidence_score_bps / 100).toFixed(1) : "83.8";
  const where = att
    ? `${att.admin_level_2 ?? "서울"} ${att.complex_name ?? "아파트"}`
    : "도봉구 래미안도봉";
  const area = att?.net_area_sqm
    ? `${Number(att.net_area_sqm).toFixed(0)}㎡`
    : "59㎡";
  const uid =
    att?.attestation_uid ??
    "0x458cea533fe3cf98ca174f70950c3d8573e06e5af1996c6cbaa1869ec925b0f0";

  return (
    <div className="hero-mockup-card">
      <div className="flex items-center justify-between">
        <span className="caption" style={{ color: "var(--muted)" }}>
          Attestation
        </span>
        <span
          className="caption inline-flex items-center gap-1.5"
          style={{ color: live ? "var(--success)" : "var(--muted-soft)" }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: live ? "var(--success)" : "var(--muted-soft)" }}
          />
          {live ? "라이브" : "캐시됨"}
        </span>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <span
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-[13px] font-semibold"
          style={{ background: "var(--badge-emerald)", color: "#065f46" }}
        >
          {(att?.admin_level_2 ?? "도봉구").slice(0, 1)}
        </span>
        <div>
          <p className="title-sm">{where}</p>
          <p className="caption" style={{ color: "var(--muted)" }}>
            전용 {area} · 아파트
          </p>
        </div>
      </div>

      <p className="display-md tnum mt-5">{value}</p>

      <div
        className="mt-5 grid grid-cols-2 gap-3 border-t pt-5"
        style={{ borderColor: "var(--hairline-soft)" }}
      >
        <div
          className="rounded-lg p-3"
          style={{ background: "var(--surface-soft)" }}
        >
          <p className="caption" style={{ color: "var(--muted)" }}>
            95% 신뢰구간
          </p>
          <p className="body-sm tnum mt-0.5 font-medium" style={{ color: "var(--ink)" }}>
            {lo} – {hi}
          </p>
        </div>
        <div
          className="rounded-lg p-3"
          style={{ background: "var(--surface-soft)" }}
        >
          <p className="caption" style={{ color: "var(--muted)" }}>
            신뢰도
          </p>
          <p className="body-sm tnum mt-0.5 font-medium" style={{ color: "var(--ink)" }}>
            {conf}% · 자동 발행
          </p>
        </div>
      </div>

      <div className="mt-4">
        <p className="caption" style={{ color: "var(--muted)" }}>
          Object ID
        </p>
        <p className="mono addr caption mt-0.5" style={{ color: "var(--body)" }}>
          {shortHex(uid, 18, 12)}
        </p>
      </div>

      <div
        className="mt-5 flex items-center justify-between border-t pt-4"
        style={{ borderColor: "var(--hairline-soft)" }}
      >
        <span className="caption" style={{ color: "var(--muted-soft)" }}>
          유효기간 90일 · 리포트 sha256 앵커
        </span>
        <a
          className="caption font-semibold"
          style={{ color: "var(--ink)" }}
          href={LINKS.suiscan}
          target="_blank"
          rel="noreferrer"
        >
          체인에서 확인 →
        </a>
      </div>
    </div>
  );
}

/* ───────────────────────── metrics ───────────────────────── */

function Metrics({ stats }: { stats: Awaited<ReturnType<typeof getStats>>["stats"] }) {
  const items = [
    { v: fmtInt(stats.transactions), k: "정부 등록 실거래", d: "서울 25개 구" },
    { v: fmtInt(stats.properties), k: "등록 세대", d: `${fmtInt(stats.complexes)}개 단지` },
    { v: "5.4%", k: "자동발행 티어 MdAPE", d: "밀봉 홀드아웃 실측" },
    { v: fmtInt(stats.active_attestations), k: "활성 attestation", d: "Sui Testnet" },
  ];
  return (
    <section className="mx-auto max-w-[1200px] px-6 pb-24">
      <div className="grid grid-cols-2 gap-6 lg:grid-cols-4">
        {items.map((it) => (
          <div key={it.k} className="feature-card">
            <p className="display-sm tnum">{it.v}</p>
            <p className="title-sm mt-2">{it.k}</p>
            <p className="body-sm mt-1" style={{ color: "var(--muted)" }}>
              {it.d}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ──────────────────────── how it works ───────────────────── */

function HowItWorks() {
  const steps = [
    {
      icon: "⇅",
      t: "수집하고 정규화합니다",
      d: "국토부 실거래가·공시가격·건축물대장·환율을 매일 수집합니다. 취소 거래를 플래그하고 원본을 불변 스냅샷으로 보존한 뒤, 국제 표준 스키마로 정규화합니다.",
    },
    {
      icon: "≈",
      t: "추정하고 검증합니다",
      d: "지역별 반복매매지수로 시장 수준을 분리한 AVM이 가치를 추정하고, conformal 예측이 95% 신뢰구간을 계산합니다. 신뢰도가 낮으면 발행하지 않습니다.",
    },
    {
      icon: "⛓",
      t: "온체인에 발행합니다",
      d: "감정가·신뢰구간·신뢰도·모델 ID·리포트 해시가 한 트랜잭션으로 발행되어 공유 피드에 게시됩니다. 파트너는 피드를 읽기만 하면 됩니다.",
    },
  ];
  return (
    <section id="how" className="mx-auto max-w-[1200px] px-6 pb-24">
      <div className="max-w-[62ch]">
        <h2 className="display-lg" style={{ textWrap: "balance" }}>
          실거래에서 attestation까지
        </h2>
        <p className="body-md mt-4" style={{ color: "var(--muted)" }}>
          모든 단계가 오픈소스이고, 모든 결과가 재현 가능합니다.
        </p>
      </div>
      <div className="mt-12 grid gap-6 md:grid-cols-3">
        {steps.map((s, i) => (
          <div key={s.t} className="feature-card">
            <div
              className="grid h-10 w-10 place-items-center rounded-lg text-[18px]"
              style={{ background: "var(--canvas)", color: "var(--ink)" }}
            >
              {s.icon}
            </div>
            <p className="caption mt-5" style={{ color: "var(--muted)" }}>
              단계 {i + 1}
            </p>
            <h3 className="title-md mt-1">{s.t}</h3>
            <p className="body-sm mt-3" style={{ color: "var(--muted)" }}>
              {s.d}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ─────────────────── tiers (pricing pattern) ─────────────── */

function Tiers() {
  return (
    <section id="tiers" className="mx-auto max-w-[1200px] px-6 pb-24">
      <div className="max-w-[62ch]">
        <h2 className="display-lg" style={{ textWrap: "balance" }}>
          숫자는 밀봉 홀드아웃에서 왔습니다
        </h2>
        <p className="body-md mt-4" style={{ color: "var(--muted)" }}>
          12개월 홀드아웃(2025-07 ~ 2026-06, 거래 69,301건)은 학습·튜닝에 단 한
          번도 노출되지 않았습니다. 프로토콜은 신뢰도 최상위 티어만 자동
          발행합니다 — 아래는 티어별 실측 성능입니다.
        </p>
      </div>

      <div className="mt-12 grid gap-6 md:grid-cols-3">
        {/* featured tier — the only dark card on the page body */}
        <div className="tier-card-featured">
          <p className="title-lg">자동 발행</p>
          <p className="caption mt-1" style={{ color: "var(--on-dark-soft)" }}>
            신뢰도 ≥ 0.85 · 전체의 21.5%
          </p>
          <p className="display-sm tnum mt-6">MdAPE 5.4%</p>
          <ul className="body-sm mt-6 space-y-2.5">
            {[
              "PPE10 78.9% — ±10% 이내 예측",
              "95% CI 실측 커버리지 93.0%",
              "즉시 온체인 발행",
            ].map((t) => (
              <li key={t} className="flex gap-2.5">
                <span style={{ color: "var(--badge-emerald)" }}>✓</span>
                {t}
              </li>
            ))}
          </ul>
        </div>

        <div className="tier-card">
          <p className="title-lg">검토 권고</p>
          <p className="caption mt-1" style={{ color: "var(--muted)" }}>
            신뢰도 0.60–0.85 · 전체의 60.8%
          </p>
          <p className="display-sm tnum mt-6">MdAPE 8.0%</p>
          <ul className="body-sm mt-6 space-y-2.5" style={{ color: "var(--body)" }}>
            {[
              "PPE10 60.1%",
              "발행하되 검토 플래그 부착",
              "CI 커버리지 91.7%",
            ].map((t) => (
              <li key={t} className="flex gap-2.5">
                <span style={{ color: "var(--muted)" }}>—</span>
                {t}
              </li>
            ))}
          </ul>
        </div>

        <div className="tier-card">
          <p className="title-lg">발행 거부</p>
          <p className="caption mt-1" style={{ color: "var(--muted)" }}>
            신뢰도 &lt; 0.60 · 전체의 17.7%
          </p>
          <p className="display-sm tnum mt-6">MdAPE 8.1%</p>
          <ul className="body-sm mt-6 space-y-2.5" style={{ color: "var(--body)" }}>
            {[
              "저유동성·고분산 케이스",
              "attestation 미발행",
              "최악 구간을 정확히 격리",
            ].map((t) => (
              <li key={t} className="flex gap-2.5">
                <span style={{ color: "var(--muted)" }}>—</span>
                {t}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="body-sm mt-8 max-w-[74ch]" style={{ color: "var(--muted)" }}>
        한계도 공개합니다 — 최신 분기의 반복매매지수 끝점 랙(-6%)은 백서
        Limitations 절에 기록되어 있으며, 신뢰도 티어가 해당 리스크 일부를 검토
        경로로 보냅니다.
      </p>
    </section>
  );
}

/* ─────────────────────── on-chain ────────────────────────── */

function OnChain({ attestations }: { attestations: Attestation[] }) {
  const rows = attestations.slice(0, 6);
  return (
    <section id="onchain" className="mx-auto max-w-[1200px] px-6 pb-24">
      <div className="max-w-[62ch]">
        <h2 className="display-lg">Sui 위의 감정 원장</h2>
        <p className="body-md mt-4" style={{ color: "var(--muted)" }}>
          모든 attestation은 검증 가능한 온체인 오브젝트입니다. 파트너
          프로토콜은 공유 ValuationFeed에서 소유 없이 읽습니다.
        </p>
      </div>

      <div className="mt-12 grid gap-6 lg:grid-cols-[5fr_7fr]">
        <div className="mockup-card">
          <p className="title-sm">배포 오브젝트</p>
          <dl className="mt-5 space-y-4">
            {[
              ["Package", CHAIN.packageId],
              ["ValuationFeed · shared", CHAIN.feed],
              ["PropertyIndex · shared", CHAIN.index],
              ["AdapterRegistry · shared", CHAIN.registry],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="caption" style={{ color: "var(--muted)" }}>
                  {k}
                </dt>
                <dd className="mono addr body-sm mt-0.5" style={{ color: "var(--body)" }}>
                  {shortHex(v, 20, 12)}
                </dd>
              </div>
            ))}
          </dl>
          <a
            className="body-sm mt-6 inline-block font-semibold text-link"
            href={LINKS.suiscan}
            target="_blank"
            rel="noreferrer"
          >
            Suiscan에서 보기 →
          </a>
        </div>

        <div className="mockup-card overflow-x-auto">
          <div className="flex items-center justify-between">
            <p className="title-sm">최근 attestation</p>
            <span className="badge-pill">
              <span className="dot" />
              라이브 피드
            </span>
          </div>
          <table className="ledger mt-4">
            <thead>
              <tr>
                <th>물건</th>
                <th style={{ textAlign: "right" }}>감정가</th>
                <th style={{ textAlign: "right" }}>신뢰도</th>
                <th>Object</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.attestation_uid}>
                  <td>
                    <span className="font-medium" style={{ color: "var(--ink)" }}>
                      {a.admin_level_2 ?? "서울"}
                    </span>{" "}
                    <span style={{ color: "var(--muted)" }}>
                      {a.complex_name ?? ""}{" "}
                      {a.net_area_sqm ? `${Number(a.net_area_sqm).toFixed(0)}㎡` : ""}
                    </span>
                  </td>
                  <td className="tnum text-right font-medium" style={{ color: "var(--ink)" }}>
                    {fmtUsd(a.value_usd_cents)}
                  </td>
                  <td className="tnum text-right">
                    {(a.confidence_score_bps / 100).toFixed(1)}%
                  </td>
                  <td className="mono caption" style={{ color: "var(--muted)" }}>
                    {shortHex(a.attestation_uid)}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ color: "var(--muted)" }}>
                    라이브 피드 연결 대기 중입니다.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────── integration ─────────────────────── */

function Integration() {
  return (
    <section id="integrate" className="mx-auto max-w-[1200px] px-6 pb-24">
      <div className="grid items-start gap-12 lg:grid-cols-[5fr_7fr]">
        <div>
          <h2 className="display-lg" style={{ textWrap: "balance" }}>
            피드 한 번 읽으면
            <br />
            통합 끝
          </h2>
          <p className="body-md mt-4 max-w-[46ch]" style={{ color: "var(--muted)" }}>
            담보 평가, 청산 임계값, NAV 산정 — 공유 피드에서 물건의 global_id로
            최신 감정값을 읽으세요. 오라클 노드를 돌릴 필요가 없습니다.
          </p>
          <ul className="body-sm mt-7 space-y-3">
            {[
              "global_id는 sha256 기반 결정론적 식별자 — 중복 등록 불가",
              "만료(90일)·폐기 여부를 온체인에서 검증",
              "REST API 병행 — 오프체인 시스템도 동일 데이터",
            ].map((t) => (
              <li key={t} className="flex gap-3">
                <span style={{ color: "var(--success)" }}>✓</span>
                <span style={{ color: "var(--body)" }}>{t}</span>
              </li>
            ))}
          </ul>
          <a
            className="btn-secondary mt-8"
            href={`${LINKS.api}/docs`}
            target="_blank"
            rel="noreferrer"
          >
            API 문서 열기
          </a>
        </div>

        <pre className="codeblock">{`
`}<span className="c">// Sui Move — 파트너 컨트랙트에서</span>{`
`}<span className="k">use</span>{` valis::oracle_feed;

`}<span className="c">// 최신 감정값 (USD cents, 신뢰도 bps, 갱신 시각)</span>{`
`}<span className="k">let</span>{` (value, confidence, updated_at) =
    oracle_feed::`}<span className="f">get</span>{`(feed, property_global_id);

`}<span className="c">// 만료 검증 포함</span>{`
`}<span className="k">let</span>{` (value, conf, ts, is_fresh) =
    oracle_feed::`}<span className="f">get_checked</span>{`(feed, global_id, clock);

`}<span className="c">// REST — 오프체인</span>{`
`}<span className="c">// GET /v1/properties/{"{global_id}"}/attestations</span>{`
`}</pre>
      </div>
    </section>
  );
}

/* ─────────────────────── CTA band ────────────────────────── */

function CtaBand() {
  return (
    <section className="mx-auto max-w-[1200px] px-6 pb-24">
      <div className="cta-band">
        <h2 className="display-sm" style={{ textWrap: "balance" }}>
          더 스마트하고 단순한 부동산 감정
        </h2>
        <p className="body-md mx-auto mt-3 max-w-[48ch]" style={{ color: "var(--muted)" }}>
          백서와 코드가 전부 공개되어 있습니다. 직접 재현해 보세요.
        </p>
        <div className="mt-7 flex justify-center gap-3">
          <a className="btn-primary" href={LINKS.whitepaper}>
            백서 읽기
          </a>
          <a className="btn-secondary" href={LINKS.github} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────── footer ──────────────────────────── */

function Footer({ stats }: { stats: Awaited<ReturnType<typeof getStats>>["stats"] }) {
  const cols: [string, [string, string][]][] = [
    [
      "프로토콜",
      [
        ["백서 (초안)", LINKS.whitepaper],
        ["GitHub", LINKS.github],
        ["Suiscan", LINKS.suiscan],
      ],
    ],
    [
      "개발자",
      [
        ["API 문서", `${LINKS.api}/docs`],
        ["헬스 체크", `${LINKS.api}/health`],
        ["통계 API", `${LINKS.api}/v1/stats`],
      ],
    ],
    [
      "데이터 출처",
      [
        ["국토부 실거래가", "https://rt.molit.go.kr"],
        ["한국은행 ECOS", "https://ecos.bok.or.kr"],
        ["국가공간정보포털", "https://www.vworld.kr"],
      ],
    ],
  ];
  return (
    <footer className="footer-dark">
      <div className="mx-auto max-w-[1200px] px-6 py-16">
        <div className="grid gap-10 md:grid-cols-[5fr_7fr]">
          <div>
            <div className="flex items-center gap-2.5">
              <span
                className="grid h-7 w-7 place-items-center rounded-full text-[13px] font-semibold"
                style={{ background: "var(--on-dark)", color: "var(--surface-dark)" }}
              >
                V
              </span>
              <span className="title-sm" style={{ color: "var(--on-dark)" }}>
                Valis<span style={{ color: "var(--on-dark-soft)" }}>.protocol</span>
              </span>
            </div>
            <p className="body-sm mt-4 max-w-[44ch]">
              온체인 부동산 감정 인프라. Valis의 attestation은 참고용 가치
              추정이며 법정 감정평가가 아닙니다.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3">
            {cols.map(([title, links]) => (
              <div key={title}>
                <p
                  className="caption mb-3 font-semibold"
                  style={{ color: "var(--on-dark)" }}
                >
                  {title}
                </p>
                <ul className="space-y-2">
                  {links.map(([label, href]) => (
                    <li key={label}>
                      <a href={href} target="_blank" rel="noreferrer">
                        {label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
        <div
          className="mt-12 flex flex-wrap items-center justify-between gap-3 border-t pt-6"
          style={{ borderColor: "var(--surface-dark-elevated)" }}
        >
          <span className="caption">© 2026 Valis Protocol</span>
          <span className="caption mono tnum">
            {stats.latest_model_id ?? "avm-kr-seoul-apt-v3"} · 데이터{" "}
            {stats.data_range.from} ~ {stats.data_range.to}
          </span>
        </div>
      </div>
    </footer>
  );
}
