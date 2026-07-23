/// Collateral gate for asset-backed issuance (docs/07-sukuk-integration.md).
///
/// Purpose-built for Sharia-compliant structures (ijarah sukuk SPVs) but
/// generic to any protocol that must bound issuance by verified asset value:
///
///   1. FRESHNESS  — the valuation must be unexpired and recently updated
///   2. CONFIDENCE — below the scholar-approved floor, the asset is simply
///                   ineligible (excessive uncertainty = gharar → refuse)
///   3. HAIRCUT    — the usable value is confidence-scaled: value × conf/10000.
///                   Empirically this tracks the conformal 95% CI lower bound
///                   (Seoul holdout: value×0.838 vs CI-lower×0.847 — ~1% apart),
///                   giving an on-chain conservative value without storing CI.
///   4. LTV        — max issuance = haircut value × ltv_bps / 10000
///
/// All checks emit events so a Sharia board can reconstruct every gate
/// decision from the chain alone.
module valis::collateral {
    use sui::clock::Clock;
    use sui::event;
    use valis::errors;
    use valis::oracle_feed::{Self, ValuationFeed};

    /// Default policy bounds — issuers pass their scholar-approved values;
    /// these constants document sane defaults.
    const DEFAULT_MIN_CONFIDENCE_BPS: u16 = 8_500; // AUTO_ISSUE tier only
    const DEFAULT_MAX_AGE_MS: u64 = 90 * 24 * 3600 * 1000; // one validity window
    const BPS: u128 = 10_000;

    // === Events (the Sharia board's audit trail) ===

    public struct CollateralChecked has copy, drop {
        global_id: vector<u8>,
        value_usd_cents: u64,
        confidence_bps: u16,
        haircut_value_usd_cents: u64,
        max_issuance_usd_cents: u64,
        ltv_bps: u16,
        checked_at: u64,
        eligible: bool,
    }

    // === Queries ===

    /// True iff the property has a live, fresh, sufficiently-confident valuation.
    public fun eligible(
        feed: &ValuationFeed,
        global_id: vector<u8>,
        clock: &Clock,
        min_confidence_bps: u16,
        max_age_ms: u64,
    ): bool {
        if (!oracle_feed::contains(feed, global_id)) return false;
        let (_, confidence, updated_at, is_fresh) =
            oracle_feed::get_checked(feed, global_id, clock);
        is_fresh
            && confidence >= min_confidence_bps
            && clock.timestamp_ms() - updated_at <= max_age_ms
    }

    /// Confidence-scaled conservative value. Aborts if ineligible —
    /// an uncertain valuation must never silently price collateral.
    public fun haircut_value(
        feed: &ValuationFeed,
        global_id: vector<u8>,
        clock: &Clock,
        min_confidence_bps: u16,
        max_age_ms: u64,
    ): u64 {
        assert!(
            eligible(feed, global_id, clock, min_confidence_bps, max_age_ms),
            errors::attestation_expired(),
        );
        let (value, confidence, _) = oracle_feed::get(feed, global_id);
        (((value as u128) * (confidence as u128)) / BPS) as u64
    }

    /// Maximum permissible issuance against this collateral.
    /// e.g. a sukuk SPV's `create_spv` asserts `target_raise <= max_issuance(...)`.
    public fun max_issuance(
        feed: &ValuationFeed,
        global_id: vector<u8>,
        clock: &Clock,
        min_confidence_bps: u16,
        max_age_ms: u64,
        ltv_bps: u16,
    ): u64 {
        assert!(ltv_bps <= 10_000, errors::invalid_valuation());
        let hv = haircut_value(feed, global_id, clock, min_confidence_bps, max_age_ms);
        (((hv as u128) * (ltv_bps as u128)) / BPS) as u64
    }

    /// Entry point that performs the full gate check and logs it on-chain.
    /// Consumer protocols may also call the pure functions above inline;
    /// this variant exists so every gate decision leaves an audit event.
    public fun check_and_log(
        feed: &ValuationFeed,
        global_id: vector<u8>,
        clock: &Clock,
        min_confidence_bps: u16,
        max_age_ms: u64,
        ltv_bps: u16,
    ): u64 {
        let ok = eligible(feed, global_id, clock, min_confidence_bps, max_age_ms);
        let (value, confidence) = if (oracle_feed::contains(feed, global_id)) {
            let (v, c, _) = oracle_feed::get(feed, global_id);
            (v, c)
        } else {
            (0, 0)
        };
        let hv = if (ok) {
            (((value as u128) * (confidence as u128)) / BPS) as u64
        } else { 0 };
        let max_iss = (((hv as u128) * (ltv_bps as u128)) / BPS) as u64;

        event::emit(CollateralChecked {
            global_id,
            value_usd_cents: value,
            confidence_bps: confidence,
            haircut_value_usd_cents: hv,
            max_issuance_usd_cents: max_iss,
            ltv_bps,
            checked_at: clock.timestamp_ms(),
            eligible: ok,
        });
        max_iss
    }

    /// Convenience wrapper with protocol defaults (AUTO_ISSUE tier, 90d, LTV arg).
    public fun max_issuance_default(
        feed: &ValuationFeed,
        global_id: vector<u8>,
        clock: &Clock,
        ltv_bps: u16,
    ): u64 {
        max_issuance(
            feed,
            global_id,
            clock,
            DEFAULT_MIN_CONFIDENCE_BPS,
            DEFAULT_MAX_AGE_MS,
            ltv_bps,
        )
    }

    public fun default_min_confidence_bps(): u16 { DEFAULT_MIN_CONFIDENCE_BPS }
    public fun default_max_age_ms(): u64 { DEFAULT_MAX_AGE_MS }
}
