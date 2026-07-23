/// Minimal ijarah sukuk SPV — demo consumer of the Valis collateral gate
/// (docs/07-sukuk-integration.md §3). Shows the full issuance flow:
///
///   1. create_spv  — the SPV is created ONLY if the underlying asset passes
///      the Valis gate (fresh attestation, confidence ≥ scholar floor) and
///      target_raise ≤ max_issuance (LTV-bounded). Over-issuance beyond
///      verified asset value — an asset-backing violation — cannot happen.
///   2. subscribe   — investors take SukukCertificate objects until the
///      target is raised. Eligibility is re-checked at every subscription,
///      so a stale/degraded valuation halts further issuance automatically.
///
/// Not production sukuk: no lease flows, no maturity, no cash handling.
/// It exists to demonstrate on-chain what the integration guide specifies.
module sukuk_demo::spv {
    use sui::clock::Clock;
    use sui::event;
    use valis::collateral;
    use valis::oracle_feed::ValuationFeed;

    const E_OVER_ISSUANCE: u64 = 1;
    const E_SOLD_OUT: u64 = 2;
    const E_ZERO_AMOUNT: u64 = 3;

    /// The escrow + rule-engine shell (수쿠크 PRD: SPV = 에스크로 + 자동화 규칙).
    public struct SukukSPV has key {
        id: UID,
        /// Valis global property id backing this sukuk (sha256, 32 bytes).
        asset_global_id: vector<u8>,
        target_raise_usd_cents: u64,
        /// LTV-bounded ceiling from the Valis gate at creation time.
        max_issuance_usd_cents: u64,
        raised_usd_cents: u64,
        certificates_issued: u64,
        // scholar-approved parameters, fixed at creation
        min_confidence_bps: u16,
        max_age_ms: u64,
        ltv_bps: u16,
    }

    /// Fractional ownership certificate (사키크 소유 지분 표상).
    public struct SukukCertificate has key, store {
        id: UID,
        spv_id: ID,
        asset_global_id: vector<u8>,
        face_value_usd_cents: u64,
        serial: u64,
    }

    public struct SpvCreated has copy, drop {
        spv_id: ID,
        asset_global_id: vector<u8>,
        target_raise_usd_cents: u64,
        max_issuance_usd_cents: u64,
        ltv_bps: u16,
    }

    public struct CertificateIssued has copy, drop {
        spv_id: ID,
        certificate_id: ID,
        face_value_usd_cents: u64,
        raised_usd_cents: u64,
        serial: u64,
    }

    /// ① 자산매각 + ② 수쿠크 발행 개시 — Valis 게이트 통과 시에만 SPV 생성.
    public fun create_spv(
        feed: &ValuationFeed,
        asset_global_id: vector<u8>,
        target_raise_usd_cents: u64,
        min_confidence_bps: u16,
        max_age_ms: u64,
        ltv_bps: u16,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        // Full gate + on-chain audit event (Sharia board reconstructs from chain)
        let max = collateral::check_and_log(
            feed, asset_global_id, clock, min_confidence_bps, max_age_ms, ltv_bps,
        );
        assert!(target_raise_usd_cents > 0, E_ZERO_AMOUNT);
        assert!(target_raise_usd_cents <= max, E_OVER_ISSUANCE);

        let spv = SukukSPV {
            id: object::new(ctx),
            asset_global_id,
            target_raise_usd_cents,
            max_issuance_usd_cents: max,
            raised_usd_cents: 0,
            certificates_issued: 0,
            min_confidence_bps,
            max_age_ms,
            ltv_bps,
        };
        event::emit(SpvCreated {
            spv_id: object::id(&spv),
            asset_global_id: spv.asset_global_id,
            target_raise_usd_cents,
            max_issuance_usd_cents: max,
            ltv_bps,
        });
        transfer::share_object(spv);
    }

    /// ③ 투자자 청약 — 만기·신선도·신뢰도를 청약 시점마다 재검증.
    public fun subscribe(
        spv: &mut SukukSPV,
        feed: &ValuationFeed,
        face_value_usd_cents: u64,
        clock: &Clock,
        ctx: &mut TxContext,
    ): SukukCertificate {
        assert!(face_value_usd_cents > 0, E_ZERO_AMOUNT);
        // Valuation must still pass the gate at issuance time — a degraded or
        // stale attestation halts new subscriptions (aborts here).
        let _ = collateral::haircut_value(
            feed, spv.asset_global_id, clock, spv.min_confidence_bps, spv.max_age_ms,
        );
        assert!(
            spv.raised_usd_cents + face_value_usd_cents <= spv.target_raise_usd_cents,
            E_SOLD_OUT,
        );

        spv.raised_usd_cents = spv.raised_usd_cents + face_value_usd_cents;
        spv.certificates_issued = spv.certificates_issued + 1;
        let cert = SukukCertificate {
            id: object::new(ctx),
            spv_id: object::id(spv),
            asset_global_id: spv.asset_global_id,
            face_value_usd_cents,
            serial: spv.certificates_issued,
        };
        event::emit(CertificateIssued {
            spv_id: object::id(spv),
            certificate_id: object::id(&cert),
            face_value_usd_cents,
            raised_usd_cents: spv.raised_usd_cents,
            serial: spv.certificates_issued,
        });
        cert
    }

    /// Entry convenience: subscribe and keep the certificate.
    entry fun subscribe_and_keep(
        spv: &mut SukukSPV,
        feed: &ValuationFeed,
        face_value_usd_cents: u64,
        clock: &Clock,
        ctx: &mut TxContext,
    ) {
        let cert = subscribe(spv, feed, face_value_usd_cents, clock, ctx);
        transfer::public_transfer(cert, ctx.sender());
    }

    // === Queries ===
    public fun raised(spv: &SukukSPV): u64 { spv.raised_usd_cents }
    public fun target(spv: &SukukSPV): u64 { spv.target_raise_usd_cents }
    public fun max_issuance(spv: &SukukSPV): u64 { spv.max_issuance_usd_cents }
    public fun certificates_issued(spv: &SukukSPV): u64 { spv.certificates_issued }
    public fun face_value(cert: &SukukCertificate): u64 { cert.face_value_usd_cents }
}
