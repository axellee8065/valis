/// Shared valuation feed — partners read the latest attestation per property
/// without holding the attestation object (docs/05 §3.5).
module valis::oracle_feed {
    use sui::clock::Clock;
    use sui::event;
    use sui::table::{Self, Table};
    use valis::attestation::{Self, AppraisalAttestation};
    use valis::errors;

    public struct ValuationFeed has key {
        id: UID,
        entries: Table<vector<u8>, FeedEntry>, // global_id (32B) => entry
    }

    public struct FeedEntry has store, drop {
        attestation_id: ID,
        value_usd_cents: u64,
        confidence_bps: u16,
        updated_at: u64,
        expires_at: u64,
    }

    public struct FeedUpdated has copy, drop {
        global_id: vector<u8>,
        attestation_id: ID,
        value_usd_cents: u64,
    }

    fun init(ctx: &mut TxContext) {
        let feed = ValuationFeed {
            id: object::new(ctx),
            entries: table::new(ctx),
        };
        transfer::share_object(feed);
    }

    /// The attestation holder publishes it to the feed.
    /// The feed keeps only the latest attestation per property.
    public entry fun publish(
        feed: &mut ValuationFeed,
        att: &AppraisalAttestation,
        clock: &Clock,
    ) {
        assert!(attestation::is_valid(att, clock), errors::attestation_expired());

        let global_id = *attestation::property_global_id(att);
        let entry = FeedEntry {
            attestation_id: object::id(att),
            value_usd_cents: attestation::value_usd_cents(att),
            confidence_bps: attestation::confidence_bps(att),
            updated_at: clock.timestamp_ms(),
            expires_at: attestation::expires_at(att),
        };

        if (feed.entries.contains(global_id)) {
            feed.entries.remove(global_id);
        };
        feed.entries.add(global_id, entry);

        event::emit(FeedUpdated {
            global_id,
            attestation_id: entry.attestation_id,
            value_usd_cents: entry.value_usd_cents,
        });
    }

    // === Queries ===
    public fun contains(feed: &ValuationFeed, global_id: vector<u8>): bool {
        feed.entries.contains(global_id)
    }

    /// Returns (value_usd_cents, confidence_bps, updated_at).
    public fun get(feed: &ValuationFeed, global_id: vector<u8>): (u64, u16, u64) {
        assert!(feed.entries.contains(global_id), errors::property_not_found());
        let entry = feed.entries.borrow(global_id);
        (entry.value_usd_cents, entry.confidence_bps, entry.updated_at)
    }

    /// Validity-aware read: also returns whether the entry is unexpired.
    public fun get_checked(
        feed: &ValuationFeed,
        global_id: vector<u8>,
        clock: &Clock,
    ): (u64, u16, u64, bool) {
        let (value, conf, updated) = get(feed, global_id);
        let entry = feed.entries.borrow(global_id);
        (value, conf, updated, clock.timestamp_ms() < entry.expires_at)
    }
}
