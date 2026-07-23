# 07 — Sukuk SPV × Valis Protocol Integration

**Consumer:** ijarah sukuk SPV protocol (Sui Move) — see partner PRD (`PRD-2.md`)
**Provider:** Valis `oracle_feed` + `collateral` modules (testnet, live)
**Status:** collateral gate implemented · integration guide for the sukuk codebase

---

## 1. Why this integration works

Sukuk structures are **asset-backed by religious requirement** — every stage of
the ijarah flow is a real-asset transaction. That makes the asset's *verified
value* the protocol's single most load-bearing external input, and exactly the
oracle problem the sukuk PRD flags as "진짜 어려운 지점".

Valis decomposes that oracle risk honestly:

| Oracle need in sukuk | Covered by Valis? |
|---|---|
| Valuation at issuance (발행 규모 산정) | ✅ attestation with 95% CI + confidence |
| Ongoing collateral health (분기 리스료 시점) | ✅ 90-day expiry forces revaluation |
| Maturity repurchase reference (⑧ 재매각) | ✅ current attestation as market anchor |
| Physical condition (훼손·화재) | ❌ stays off-chain (insurance/inspection) |
| Legal title (등기·압류) | ⚠️ roadmap (registry API, docs/02 §2.3.G) |

### The Sharia argument: quantified gharar

Gharar 금지는 "과도한 불확실성" 금지다. 전통 감정서는 점추정 하나를 주고
불확실성의 크기는 침묵한다. Valis attestation은 불확실성을 **명시적으로
계약 조건화**한다:

- **95% 신뢰구간** — 홀드아웃 실측 커버리지 93%로 캘리브레이션된, 정직한
  불확실성 구간이 온체인에 기록된다.
- **신뢰도 티어** — 불확실성이 과도한 물건(REFUSE, 전체의 ~18%)은 담보
  부적격으로 발행 자체가 차단된다. *Excessive* uncertainty is refused, not
  priced.
- **report sha256 앵커** — Sharia board가 산정 근거 문서 전체를 검증할 수
  있다. 판단(principle)은 학자의 몫, 집행(parameter)은 코드의 몫 — 수쿠크
  PRD가 결론 내린 하이브리드 모델 그대로다.

Scholar-approved parameters (min confidence, LTV, max age)를 게이트 상수로
넘기면, 컨트랙트는 그 범위 안에서만 작동한다.

---

## 2. On-chain interface (live on testnet)

Package (v3, upgraded): includes `valis::collateral`

```move
use valis::collateral;

// 적격성: 피드 존재 + 미만료 + 신선도 + 신뢰도 하한
collateral::eligible(feed, global_id, clock, min_conf_bps, max_age_ms): bool

// 보수적 담보가치 = value × confidence / 10000
// (서울 홀드아웃에서 conformal CI 하한과 ~1% 이내로 일치하는 프록시)
collateral::haircut_value(feed, global_id, clock, min_conf_bps, max_age_ms): u64

// 최대 발행 한도 = haircut_value × ltv_bps / 10000
collateral::max_issuance(feed, global_id, clock, min_conf_bps, max_age_ms, ltv_bps): u64

// 전체 게이트 수행 + CollateralChecked 이벤트 (Sharia 감사 로그)
collateral::check_and_log(feed, global_id, clock, min_conf_bps, max_age_ms, ltv_bps): u64
```

Defaults: `min_confidence = 8500 bps` (Valis AUTO_ISSUE tier),
`max_age = 90d`. Every check emits `CollateralChecked` so the Sharia board can
reconstruct all gate decisions from events alone (수쿠크 CLAUDE.md 원칙 5와 동일
철학).

---

## 3. Integration points in the sukuk codebase

### 3.1 `asset.move` — link the physical asset to its Valis identity

```move
public struct Asset has key, store {
    // ... existing fields ...
    /// sha256(country:canonical_id) — Valis global property identity.
    /// Some(id) for real-estate kinds; None for aircraft/vessel until
    /// those Valis adapters exist.
    valis_global_id: Option<vector<u8>>,
}
```

`register`에 `valis_global_id: Option<vector<u8>>` 파라미터 추가. real_estate
kind이면 필수로 요구하는 정책도 가능 (Sharia board 결정 사항 — PRD §8에 기록
권장).

### 3.2 `spv.move::create_spv` — issuance gate (① 자산매각 / ② 수쿠크 발행)

```move
use valis::collateral;
use valis::oracle_feed::ValuationFeed;

public fun create_spv<S>(
    asset: Asset,
    valis_feed: &ValuationFeed,          // NEW
    sharia: &ShariaParams,               // carries scholar-approved bounds
    target_raise: u64,
    /* ... */
    clock: &Clock,
    ctx: &mut TxContext,
) {
    // 실물 부동산 담보라면 발행 한도를 검증가치에 묶는다
    if (asset.valis_global_id.is_some()) {
        let gid = *asset.valis_global_id.borrow();
        let max = collateral::check_and_log(
            valis_feed, gid, clock,
            sharia.min_confidence_bps,   // scholar-approved
            sharia.max_valuation_age_ms,
            sharia.max_ltv_bps,
        );
        assert!(target_raise <= max, EOverIssuance);
    };
    // ... existing flow ...
}
```

과대발행(자산 가치를 넘는 모금)은 asset-backed 원칙 위반이자 gharar — 이
assert 한 줄이 그 클래스 전체를 차단한다.

### 3.3 `spv.move::pay_lease` — periodic health check (⑥ 리스료)

리스료 주기(분기)와 Valis 유효기간(90일)이 맞물린다:

```move
public fun pay_lease<S>(spv: &mut SukukSPV<S>, valis_feed: &ValuationFeed, ...) {
    // 납부 시점마다 담보 건전성 이벤트를 남긴다 (abort하지 않음 — 공시 목적)
    if (spv.valis_global_id.is_some()) {
        collateral::check_and_log(valis_feed, gid, clock,
            spv.sharia.min_confidence_bps, spv.sharia.max_valuation_age_ms,
            spv.sharia.max_ltv_bps);
    };
    // ... existing lease flow ...
}
```

가치 하락으로 LTV가 악화되면 `CollateralChecked.eligible=false` 이벤트가
누적된다 — 인덱서가 이를 조기 경보로 소비 (수쿠크 Phase 5 모니터링과 연결).

### 3.4 `repurchase` — maturity disclosure (⑧ 만기 재매각)

Ijarah에서 사전 약정가 재매입은 인정되지만, **약정가와 시가의 괴리 공시**는
실질(substance) 심사에 유용한 자료다:

```move
// 약정 재매입가와 현재 attestation 가치를 함께 이벤트로 방출
event::emit(RepurchaseDisclosure {
    agreed_price, current_valuation: collateral::haircut_value(...), gap_bps
});
```

강제(assert)가 아니라 공시(event) — 판단은 Sharia board 몫.

### 3.5 Off-chain (frontend / indexer)

- REST: `GET /v1/properties/{global_id}/attestations` — 대시보드에 감정
  이력·CI 표시
- `GET /v1/stats` — 프로토콜 지표
- attestation의 `report_uri`/`report_hash` — Sharia 인증 UI에서 근거 문서
  링크 + 해시 검증

---

## 4. Live objects (testnet)

| Object | ID |
|---|---|
| Valis package (v3, with `collateral`) | `0x7f8400996b4712aaf2b8a386415f0b6e1389dcc4b14aa182e841756d1d6ebdc0` |
| ValuationFeed (shared) | `0xe76f7031e20c49971819158dc7ccf4086353533be32af950b15ad0e2db6e3454` |
| Active feed entries | 61 (Seoul apartments) |

### Live demo transactions (both paths exercised on-chain)

**Pass — AUTO_ISSUE tier collateral** (성북구 아파트, 전용 59.79㎡, 1998년):
tx `DUF2TRzWgoDWjK1h2iKuSFZyQXQX46c2JmUH5BsrsAei`

| Field | Value |
|---|---|
| value | $457,043.96 |
| confidence | 94.57% (≥ 85% floor) |
| haircut value | $432,226.47 (= value × 0.9457) |
| max issuance @ LTV 60% | **$259,335.88** |
| eligible | ✅ true |

**Refuse — below confidence floor** (도봉구 아파트, 전용 59.25㎡, 2005년):
tx `goUApYkgLkgavzkE8dmdvaMCEfxNPAGx1Dx1JQxKi2j`

| Field | Value |
|---|---|
| value | $409,191.08 |
| confidence | 83.84% (< 85% floor) |
| haircut value / max issuance | **$0 / $0** |
| eligible | ❌ false — excessive uncertainty is refused, not priced |

Both decisions are on-chain `CollateralChecked` events — the Sharia audit
trail works exactly as designed.

---

## 5. What Valis does NOT solve (state honestly in the sukuk docs)

1. 물리적 상태·보험 — 오프체인 검증 유지
2. 법적 권원 — 등기 연동 전까지 법무 실사 병행
3. 비부동산 자산 (항공기·선박·상품) — Valis 어댑터 부재; `valis_global_id 
   = None` 경로로 기존 수동 감정 유지
4. 서울 아파트 외 커버리지 — 두바이 확장(docs/06)이 곧 UAE 수쿠크 시장과
   직결되는 이유

## 6. Open questions for the Sharia board (수쿠크 PRD §8에 추가 권장)

1. `min_confidence_bps` 하한 — 8500(권장) vs 더 보수적?
2. `max_ltv_bps` — 자산 유형별 차등?
3. AVM 기반 가치평가의 Sharia 적격성 자체에 대한 명시적 승인
   (AAOIFI 표준 매핑 문서 필요)
4. 재매각가-시가 괴리가 임계 초과 시 공시만 할지, 재협상 트리거로 할지
