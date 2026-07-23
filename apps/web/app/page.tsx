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
  const featured = attestations[0];

  return (
    <div className="min-h-screen">
      <Nav />
      <main className="mx-auto max-w-[1120px] px-6">
        <Hero live={live} featured={featured} />
        <MetricsStrip stats={stats} />
        <HowItWorks />
        <Performance />
        <OnChain attestations={attestations} />
        <Integration />
        <Roadmap />
      </main>
      <Footer stats={stats} />
    </div>
  );
}

/* ────────────────────────── nav ────────────────────────── */

function Nav() {
  return (
    <nav
      className="sticky top-0 z-20 border-b backdrop-blur-md"
      style={{ borderColor: "var(--line)", background: "rgba(12,11,9,0.82)" }}
    >
      <div className="mx-auto flex max-w-[1120px] items-center justify-between px-6 py-4">
        <a href="#" className="flex items-center gap-3">
          <span className="seal serif">V</span>
          <span className="serif text-lg tracking-wide">Valis Protocol</span>
        </a>
        <div className="hidden items-center gap-7 md:flex">
          <a className="navlink" href="#how">프로토콜</a>
          <a className="navlink" href="#performance">검증 성능</a>
          <a className="navlink" href="#onchain">온체인</a>
          <a className="navlink" href="#integrate">통합</a>
          <a className="navlink" href={LINKS.whitepaper}>백서</a>
        </div>
        <div className="flex items-center gap-3">
          <span className="badge">
            <span className="pulse" />
            Sui Testnet
          </span>
          <a
            className="navlink hidden sm:block"
            href={LINKS.github}
            target="_blank"
            rel="noreferrer"
          >
            GitHub ↗
          </a>
        </div>
      </div>
    </nav>
  );
}

/* ────────────────────────── hero ───────────────────────── */

function Hero({ live, featured }: { live: boolean; featured?: Attestation }) {
  return (
    <section className="grid items-center gap-12 pb-20 pt-20 md:grid-cols-[1.15fr_0.85fr] md:pt-28">
      <div>
        <p className="eyebrow mb-5">The trust layer for RWA real estate</p>
        <h1
          className="serif text-[40px] leading-[1.22] md:text-[54px]"
          style={{ textWrap: "balance" }}
        >
          부동산의 가치를,
          <br />
          <span style={{ color: "var(--bronze-bright)" }}>
            검증 가능한 형태
          </span>
          로 온체인에.
        </h1>
        <p
          className="mt-7 max-w-[54ch] text-[16px] leading-[1.75]"
          style={{ color: "var(--ink-2)" }}
        >
          Valis는 정부 실거래 데이터와 AVM을 결합해 부동산 감정 결과를
          신뢰구간·신뢰도·모델 계보와 함께 Sui 위에 발행합니다. 밀봉된
          홀드아웃으로 검증하고, 근거 리포트의 해시를 온체인에 앵커링합니다 —
          어떤 RWA 프로토콜이든 읽어갈 수 있는 하나의 공유 피드로.
        </p>
        <div className="mt-9 flex flex-wrap gap-3">
          <a className="btn btn-primary" href={LINKS.whitepaper}>
            백테스트 백서 읽기
          </a>
          <a
            className="btn btn-ghost"
            href={LINKS.github}
            target="_blank"
            rel="noreferrer"
          >
            GitHub에서 코드 보기
          </a>
        </div>
        <p className="mt-6 text-[12.5px]" style={{ color: "var(--muted)" }}>
          오픈소스 · 재현 가능한 백테스트 · 감정평가의 대체가 아닌{" "}
          <em>보조 신호</em>
        </p>
      </div>

      <FeaturedAttestation live={live} att={featured} />
    </section>
  );
}

function FeaturedAttestation({
  live,
  att,
}: {
  live: boolean;
  att?: Attestation;
}) {
  const value = att ? fmtUsd(att.value_usd_cents) : "$409,191";
  const lo = att ? fmtUsd(att.ci_lower_usd_cents) : "$346,512";
  const hi = att ? fmtUsd(att.ci_upper_usd_cents) : "$469,618";
  const conf = att
    ? (att.confidence_score_bps / 100).toFixed(1)
    : "83.8";
  const where = att
    ? `${att.admin_level_2 ?? "서울"} · ${att.complex_name ?? "아파트"} ${
        att.net_area_sqm ? Number(att.net_area_sqm).toFixed(0) + "㎡" : ""
      }`
    : "도봉구 · 래미안도봉 59㎡";
  const uid = att?.attestation_uid ??
    "0x458cea533fe3cf98ca174f70950c3d8573e06e5af1996c6cbaa1869ec925b0f0";

  return (
    <div className="card relative overflow-hidden p-7">
      <div
        className="absolute right-0 top-0 h-full w-[3px]"
        style={{ background: "var(--bronze)" }}
      />
      <div className="flex items-center justify-between">
        <span className="eyebrow">Latest attestation</span>
        <span
          className="text-[11px] font-semibold"
          style={{ color: live ? "var(--good)" : "var(--muted)" }}
        >
          {live ? "● LIVE" : "○ CACHED"}
        </span>
      </div>
      <p className="mt-4 text-[13px]" style={{ color: "var(--ink-2)" }}>
        {where}
      </p>
      <p className="serif tnum mt-1 text-[44px] leading-none">{value}</p>
      <div className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 text-[13px]">
        <div>
          <p style={{ color: "var(--muted)", fontSize: 11.5 }}>95% 신뢰구간</p>
          <p className="tnum">
            {lo} – {hi}
          </p>
        </div>
        <div>
          <p style={{ color: "var(--muted)", fontSize: 11.5 }}>신뢰도</p>
          <p className="tnum">{conf}%</p>
        </div>
        <div className="col-span-2">
          <p style={{ color: "var(--muted)", fontSize: 11.5 }}>Object ID</p>
          <p className="mono addr">{shortHex(uid, 16, 12)}</p>
        </div>
      </div>
      <div className="rule mt-5 pt-4 text-[11.5px]" style={{ color: "var(--muted)" }}>
        conformal 신뢰구간 · 모델 계보 및 리포트 sha256 온체인 기록
      </div>
    </div>
  );
}

/* ─────────────────────── metrics strip ─────────────────── */

function MetricsStrip({ stats }: { stats: Awaited<ReturnType<typeof getStats>>["stats"] }) {
  const items = [
    { k: "정부 등록 실거래", v: fmtInt(stats.transactions), d: "서울 25개 구 · 2020–현재" },
    { k: "등록 세대", v: fmtInt(stats.properties), d: `${fmtInt(stats.complexes)}개 단지` },
    { k: "활성 attestation", v: fmtInt(stats.active_attestations), d: "Sui Testnet" },
    { k: "자동발행 티어 MdAPE", v: "5.4%", d: "CI-95 커버리지 93.0%" },
  ];
  return (
    <section className="rule-strong grid grid-cols-2 gap-px overflow-hidden rounded-b-lg md:grid-cols-4" style={{ background: "var(--line)" }}>
      {items.map((it) => (
        <div key={it.k} className="p-6" style={{ background: "var(--plane)" }}>
          <p className="text-[11.5px]" style={{ color: "var(--muted)" }}>
            {it.k}
          </p>
          <p className="serif tnum mt-1 text-[30px] leading-tight">{it.v}</p>
          <p className="mt-1 text-[12px]" style={{ color: "var(--ink-2)" }}>
            {it.d}
          </p>
        </div>
      ))}
    </section>
  );
}

/* ─────────────────────── how it works ──────────────────── */

function HowItWorks() {
  const steps = [
    {
      n: "01",
      t: "수집 · 정규화",
      d: "국토부 실거래가, 공시가격, 건축물대장, 한국은행 환율을 매일 수집합니다. 취소·특수관계 거래를 플래그하고, 모든 원본을 불변 스냅샷으로 보존한 뒤 국제 표준 스키마(면적 ㎡ · USD cents · WGS84)로 정규화합니다.",
      tag: "MOLIT · 건축HUB · ECOS · VWorld",
    },
    {
      n: "02",
      t: "가치 추정 · 검증",
      d: "지역별 반복매매지수로 시장 수준을 분리한 LightGBM AVM이 가치를 추정하고, conformal 예측이 분포 가정 없는 95% 신뢰구간을 산출합니다. 유동성·신선도·모델 확신도가 신뢰도 점수를 만들고 — 낮으면 발행을 거부합니다.",
      tag: "AVM v3 · adaptive conformal · 신뢰도 티어",
    },
    {
      n: "03",
      t: "온체인 발행",
      d: "감정가, 신뢰구간, 신뢰도, 모델 ID, 근거 리포트의 sha256이 하나의 트랜잭션으로 발행되어 공유 ValuationFeed에 게시됩니다. 파트너 프로토콜은 attestation을 소유하지 않고도 최신 가치를 읽습니다.",
      tag: "Sui Move · 1-tx 배치 파이프라인 · 90일 만료",
    },
  ];
  return (
    <section id="how" className="pt-24">
      <p className="eyebrow">Protocol</p>
      <h2 className="serif mt-3 text-[30px]" style={{ textWrap: "balance" }}>
        실거래에서 attestation까지, 세 단계
      </h2>
      <div className="mt-10 grid gap-px overflow-hidden rounded-lg md:grid-cols-3" style={{ background: "var(--line)" }}>
        {steps.map((s) => (
          <div key={s.n} className="p-7" style={{ background: "var(--surface)" }}>
            <div className="flex items-baseline justify-between">
              <span className="serif text-[15px]" style={{ color: "var(--bronze)" }}>
                {s.n}
              </span>
            </div>
            <h3 className="mt-3 text-[17px] font-semibold">{s.t}</h3>
            <p className="mt-3 text-[13.5px] leading-[1.75]" style={{ color: "var(--ink-2)" }}>
              {s.d}
            </p>
            <p className="mono mt-5 text-[11px]" style={{ color: "var(--muted)" }}>
              {s.tag}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ─────────────────────── performance ───────────────────── */

function Performance() {
  const tiers = [
    { name: "자동 발행", color: "var(--good)", share: "21.5%", mdape: "5.4%", ppe10: "78.9%", ci: "93.0%", hl: true },
    { name: "검토 권고", color: "var(--warn)", share: "60.8%", mdape: "8.0%", ppe10: "60.1%", ci: "91.7%", hl: false },
    { name: "발행 거부", color: "var(--crit)", share: "17.7%", mdape: "8.1%", ppe10: "58.9%", ci: "—", hl: false },
  ];
  return (
    <section id="performance" className="pt-24">
      <p className="eyebrow">Verified performance</p>
      <h2 className="serif mt-3 text-[30px]" style={{ textWrap: "balance" }}>
        숫자는 밀봉 홀드아웃에서 왔습니다
      </h2>
      <p className="mt-4 max-w-[68ch] text-[14.5px] leading-[1.75]" style={{ color: "var(--ink-2)" }}>
        모든 지표는 학습·튜닝·캘리브레이션에 단 한 번도 노출되지 않은 12개월
        홀드아웃(2025-07 ~ 2026-06, 거래 69,301건)에서 산출했습니다. 랜덤
        스플릿은 방법론적으로 금지 — temporal split만 사용합니다. 프로토콜은
        신뢰도 최상위 티어만 자동 발행합니다.
      </p>

      <div className="mt-10 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="grid grid-cols-2 gap-4">
          <BigStat v="7.24%" k="전체 홀드아웃 MdAPE" d="커버리지 100%" />
          <BigStat v="92.8%" k="PPE20" d="±20% 이내 예측 비율" />
          <BigStat v="5.4%" k="자동발행 티어 MdAPE" d="발행 대상 상위 21.5%" />
          <BigStat v="93.0%" k="CI-95 실측 커버리지" d="목표 구간 93–97% 달성" />
        </div>
        <div className="card overflow-x-auto">
          <table className="ledger">
            <thead>
              <tr>
                <th>신뢰도 티어</th>
                <th className="text-right">비중</th>
                <th className="text-right">MdAPE</th>
                <th className="text-right">PPE10</th>
                <th className="text-right">CI-95</th>
              </tr>
            </thead>
            <tbody>
              {tiers.map((t) => (
                <tr key={t.name} style={t.hl ? { background: "var(--bronze-dim)" } : undefined}>
                  <td>
                    <span className="inline-flex items-center gap-2 font-semibold">
                      <span className="inline-block h-2 w-2 rounded-[2px]" style={{ background: t.color }} />
                      {t.name}
                    </span>
                  </td>
                  <td className="tnum text-right">{t.share}</td>
                  <td className="tnum text-right">{t.mdape}</td>
                  <td className="tnum text-right">{t.ppe10}</td>
                  <td className="tnum text-right">{t.ci}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-4 pb-4 pt-3 text-[12px]" style={{ color: "var(--muted)" }}>
            거부 티어가 최악 케이스를 정확히 걸러냅니다 — 신뢰도 점수는 장식이
            아니라 발행 정책입니다. 한계 또한 공개합니다: 최신 분기의 지수
            끝점 랙(-6%)은 백서 Limitations 절에 기록되어 있습니다.
          </p>
        </div>
      </div>
    </section>
  );
}

function BigStat({ v, k, d }: { v: string; k: string; d: string }) {
  return (
    <div className="card p-6">
      <p className="serif tnum text-[34px] leading-none" style={{ color: "var(--bronze-bright)" }}>
        {v}
      </p>
      <p className="mt-2 text-[13px] font-semibold">{k}</p>
      <p className="mt-1 text-[12px]" style={{ color: "var(--muted)" }}>
        {d}
      </p>
    </div>
  );
}

/* ─────────────────────── on-chain ──────────────────────── */

function OnChain({ attestations }: { attestations: Attestation[] }) {
  const rows = attestations.length ? attestations : [];
  return (
    <section id="onchain" className="pt-24">
      <p className="eyebrow">On-chain registry</p>
      <h2 className="serif mt-3 text-[30px]">Sui 위의 감정 원장</h2>

      <div className="mt-10 grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="card p-6">
          <h3 className="text-[15px] font-semibold">배포 오브젝트</h3>
          <dl className="mt-4 space-y-4">
            {[
              ["Package", CHAIN.packageId],
              ["ValuationFeed (shared)", CHAIN.feed],
              ["PropertyIndex (shared)", CHAIN.index],
              ["AdapterRegistry (shared)", CHAIN.registry],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-[11.5px]" style={{ color: "var(--muted)" }}>
                  {k}
                </dt>
                <dd className="mono addr mt-0.5">{v}</dd>
              </div>
            ))}
          </dl>
          <a
            className="mt-5 inline-block text-[13px] font-semibold"
            style={{ color: "var(--bronze)" }}
            href={LINKS.suiscan}
            target="_blank"
            rel="noreferrer"
          >
            Suiscan에서 보기 ↗
          </a>
        </div>

        <div className="card overflow-x-auto">
          <table className="ledger">
            <thead>
              <tr>
                <th>물건</th>
                <th className="text-right">감정가</th>
                <th className="text-right">신뢰도</th>
                <th>Attestation</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.attestation_uid}>
                  <td>
                    <span className="font-medium">{a.admin_level_2 ?? "서울"}</span>{" "}
                    <span style={{ color: "var(--ink-2)" }}>
                      {a.complex_name ?? ""}{" "}
                      {a.net_area_sqm ? `${Number(a.net_area_sqm).toFixed(0)}㎡` : ""}
                    </span>
                  </td>
                  <td className="tnum text-right font-semibold">
                    {fmtUsd(a.value_usd_cents)}
                  </td>
                  <td className="tnum text-right">
                    {(a.confidence_score_bps / 100).toFixed(1)}%
                  </td>
                  <td className="mono" style={{ color: "var(--muted)", fontSize: 11.5 }}>
                    {shortHex(a.attestation_uid)}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ color: "var(--muted)" }}>
                    라이브 피드 연결 대기 중 — API에서 최근 attestation을
                    불러옵니다.
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

/* ─────────────────────── integration ───────────────────── */

function Integration() {
  return (
    <section id="integrate" className="pt-24">
      <p className="eyebrow">Integrate</p>
      <h2 className="serif mt-3 text-[30px]">피드 한 번 읽으면 끝</h2>
      <div className="mt-10 grid gap-4 lg:grid-cols-2">
        <div>
          <p className="max-w-[52ch] text-[14.5px] leading-[1.8]" style={{ color: "var(--ink-2)" }}>
            담보 평가, 청산 임계값, NAV 산정 — 어디에 쓰든 방식은 같습니다.
            공유 <span className="mono text-[13px]">ValuationFeed</span>에서
            물건의 <span className="mono text-[13px]">global_id</span>로 최신
            감정값을 읽으세요. attestation을 소유할 필요도, 오라클 노드를 돌릴
            필요도 없습니다.
          </p>
          <ul className="mt-6 space-y-3 text-[13.5px]" style={{ color: "var(--ink-2)" }}>
            {[
              "global_id = sha256(국가코드:정규화 물건ID) — 결정론적, 중복 불가",
              "만료(90일)·폐기 여부가 온체인에서 검증됨",
              "REST API 병행 제공 — 오프체인 시스템도 동일 데이터",
            ].map((t) => (
              <li key={t} className="flex gap-3">
                <span style={{ color: "var(--bronze)" }}>—</span>
                {t}
              </li>
            ))}
          </ul>
        </div>
        <pre className="codeblock mono">{`// Sui Move — 파트너 컨트랙트에서
`}<span className="k">use</span>{` valis::oracle_feed;

`}<span className="c">// 최신 감정값 (USD cents, 신뢰도 bps, 갱신 시각)</span>{`
`}<span className="k">let</span>{` (value, confidence, updated_at) =
    oracle_feed::`}<span className="f">get</span>{`(feed, property_global_id);

`}<span className="c">// 만료 검증 포함 조회</span>{`
`}<span className="k">let</span>{` (value, conf, ts, is_fresh) =
    oracle_feed::`}<span className="f">get_checked</span>{`(feed, global_id, clock);

`}<span className="c">// REST — 오프체인</span>{`
`}<span className="c">{`// GET ${"https://valis-api-production.up.railway.app"}`}</span>{`
`}<span className="c">//     /v1/properties/{`{global_id}`}/attestations</span>
        </pre>
      </div>
    </section>
  );
}

/* ─────────────────────── roadmap ───────────────────────── */

function Roadmap() {
  const items = [
    { when: "지금", what: "서울 아파트 MVP — 백테스트 공개, Testnet 발행 가동", state: "live" },
    { when: "다음", what: "10,000건 발행 · KB시세 대조 · 감정법인 dual-check", state: "next" },
    { when: "확장", what: "두바이(DLD) 어댑터 — 스키마·레지스트리는 이미 다국가 지원", state: "later" },
    { when: "그 후", what: "외부 감사 후 Mainnet · 파트너 프로토콜 온보딩", state: "later" },
  ];
  return (
    <section className="pt-24">
      <p className="eyebrow">Roadmap</p>
      <div className="mt-8 grid gap-px overflow-hidden rounded-lg md:grid-cols-4" style={{ background: "var(--line)" }}>
        {items.map((it) => (
          <div key={it.what} className="p-6" style={{ background: "var(--plane)" }}>
            <p
              className="text-[11.5px] font-bold uppercase tracking-[0.14em]"
              style={{ color: it.state === "live" ? "var(--good)" : "var(--muted)" }}
            >
              {it.when}
            </p>
            <p className="mt-2 text-[13.5px] leading-[1.65]" style={{ color: "var(--ink-2)" }}>
              {it.what}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ─────────────────────── footer ────────────────────────── */

function Footer({ stats }: { stats: Awaited<ReturnType<typeof getStats>>["stats"] }) {
  return (
    <footer className="mt-24 border-t" style={{ borderColor: "var(--line)" }}>
      <div className="mx-auto max-w-[1120px] px-6 py-12">
        <div className="flex flex-wrap items-start justify-between gap-8">
          <div>
            <div className="flex items-center gap-3">
              <span className="seal serif">V</span>
              <span className="serif text-lg">Valis Protocol</span>
            </div>
            <p className="mt-3 max-w-[46ch] text-[12.5px] leading-[1.7]" style={{ color: "var(--muted)" }}>
              Valis의 attestation은 참고용 가치 추정(reference value)이며 법정
              감정평가가 아닙니다. 데이터: 국토교통부 실거래가 공개시스템,
              한국은행 ECOS, 국가공간정보포털, 건축HUB, 서울열린데이터광장.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-x-14 gap-y-2 text-[13px]">
            <a className="navlink" href={LINKS.github} target="_blank" rel="noreferrer">GitHub</a>
            <a className="navlink" href={LINKS.whitepaper}>백서 (초안)</a>
            <a className="navlink" href={`${LINKS.api}/docs`} target="_blank" rel="noreferrer">API 문서</a>
            <a className="navlink" href={LINKS.suiscan} target="_blank" rel="noreferrer">Suiscan</a>
          </div>
        </div>
        <div className="rule mt-10 flex flex-wrap items-center justify-between gap-2 pt-5 text-[11.5px]" style={{ color: "var(--muted)" }}>
          <span>
            © 2026 Valis Protocol · 모델{" "}
            <span className="mono">{stats.latest_model_id ?? "avm-kr-seoul-apt-v3"}</span>
          </span>
          <span className="tnum">
            데이터 {stats.data_range.from} ~ {stats.data_range.to}
          </span>
        </div>
      </div>
    </footer>
  );
}
